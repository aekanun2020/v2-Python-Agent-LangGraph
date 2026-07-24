"""Lab 6 — Pure Python Planner + Dynamic Observation.

โค้ดตั้งใจให้เห็น agent loop ทั้งหมดในไฟล์เดียว ไม่ใช้ LangGraph และไม่มีกฎเฉพาะโดเมน

รัน:
    python labs/lab6_todo/agent_planner.py "คำถามของคุณ"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Literal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import config, llm
from labs.core.registry import ToolRegistry


Decision = Literal["accept", "retry", "query_more", "replan", "stop"]

SYSTEM = """คุณคือ agent ที่ทำงานด้วยวงจร Thought → Action → Observation

กติกา:
1. เรียก plan_write ก่อนทำงาน ใช้จำนวนขั้น MCP ที่น้อยที่สุดและแต่ละขั้นต้องพิสูจน์ได้
   อย่าแยก filter/join/aggregate เป็นคนละ step ถ้า query เดียวทำและพิสูจน์พร้อมกันได้
2. ทำ MCP action ได้ครั้งละหนึ่ง action สำหรับ step ที่ active
3. หลัง MCP คืนผล ต้องเรียก observe ก่อน action ถัดไปเสมอ
4. Observation ต้องตีความตามเป้าหมาย, active step, action และผลจริง:
   - action สำเร็จหรือไม่
   - result สนับสนุน step หรือไม่
   - evidence ครบหรือยัง
   - claim ใดถูกพิสูจน์หรือขัดแย้ง
   - ตัดสิน accept / retry / query_more / replan / stop
5. accept เฉพาะเมื่อ action สำเร็จ, result สนับสนุน step และ evidence ครบ
6. ใช้ plan_revise เมื่อผลจริงทำให้แผนเดิมไม่เหมาะสม
7. ตอบสุดท้ายจาก accepted evidence เท่านั้น และบอกข้อจำกัดที่หลักฐานพิสูจน์ไม่ได้

Observation เป็น semantic judgment ของคุณ ไม่ใช่ keyword matching ของ Python
และห้ามถือว่า tool สำเร็จเท่ากับคำตอบถูกเชิงความหมาย
ถ้าเขียน T-SQL และเปรียบเทียบ Unicode text ให้ใช้ N'...' เป็น string literal
เรียก tool ครั้งละหนึ่งรายการเท่านั้น ห้ามส่ง parallel tool calls
"""


@dataclass
class PlanStep:
    id: int
    task: str
    status: Literal["pending", "active", "completed"] = "pending"
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ObservationState:
    action_succeeded: bool
    supports_step: bool
    evidence_complete: bool
    proven_claims: list[str]
    contradicted_claims: list[str]
    decision: Decision
    reason: str


@dataclass
class PlannerState:
    goal: str
    steps: list[PlanStep]
    revision: int = 1
    awaiting_observation: bool = False
    latest_action: dict | None = None
    latest_result: str | None = None
    observations: list[ObservationState] = field(default_factory=list)
    stopped: bool = False

    @property
    def active_step(self) -> PlanStep | None:
        return next((step for step in self.steps if step.status == "active"), None)

    @property
    def complete(self) -> bool:
        return bool(self.steps) and all(step.status == "completed" for step in self.steps)

    def activate_next(self) -> None:
        if self.active_step is None:
            next_step = next((step for step in self.steps if step.status == "pending"), None)
            if next_step:
                next_step.status = "active"

    def record_action(self, name: str, arguments: dict, result: str, call_id: str) -> None:
        if self.awaiting_observation:
            raise ValueError("ต้อง observe ผล action ก่อนเรียก MCP อีกครั้ง")
        self.activate_next()
        if self.active_step is None:
            raise ValueError("ไม่มี active plan step สำหรับ MCP action")
        self.latest_action = {
            "step_id": self.active_step.id,
            "tool": name,
            "arguments": arguments,
            "tool_call_id": call_id,
        }
        self.latest_result = result
        self.awaiting_observation = True

    def observe(self, observation: ObservationState) -> None:
        if not self.awaiting_observation or self.active_step is None:
            raise ValueError("ไม่มี MCP result ที่รอ Observation")
        if observation.decision == "accept" and not (
            observation.action_succeeded
            and observation.supports_step
            and observation.evidence_complete
        ):
            raise ValueError("accept ไม่ได้: action/result/evidence ยังไม่ผ่านครบ")

        self.observations.append(observation)
        if observation.decision == "accept":
            self.active_step.evidence.append({
                **(self.latest_action or {}),
                "result": self.latest_result,
                "proven_claims": observation.proven_claims,
                "contradicted_claims": observation.contradicted_claims,
            })
            self.active_step.status = "completed"
            self.awaiting_observation = False
            self.latest_action = None
            self.latest_result = None
            self.activate_next()
        elif observation.decision in {"retry", "query_more"}:
            self.awaiting_observation = False
            self.latest_action = None
            self.latest_result = None
        elif observation.decision == "replan":
            self.awaiting_observation = False
        elif observation.decision == "stop":
            self.awaiting_observation = False
            self.stopped = True

    def revise(self, reason: str, future_steps: list[str]) -> None:
        if self.awaiting_observation:
            last = self.observations[-1] if self.observations else None
            if not last or last.decision != "replan":
                raise ValueError("ต้อง observe ด้วย decision=replan ก่อนแก้แผน")
        completed = [step for step in self.steps if step.status == "completed"]
        start = len(completed) + 1
        self.steps = completed + [
            PlanStep(start + index, task) for index, task in enumerate(future_steps)
        ]
        self.revision += 1
        self.awaiting_observation = False
        self.latest_action = None
        self.latest_result = None
        self.activate_next()

    def render(self) -> str:
        marks = {"pending": "[ ]", "active": "[~]", "completed": "[x]"}
        rows = [f"Goal: {self.goal} | revision={self.revision}"]
        rows.extend(
            f"{marks[step.status]} {step.id}. {step.task} (evidence={len(step.evidence)})"
            for step in self.steps
        )
        return "\n".join(rows)


def internal_tools() -> list[dict]:
    def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }}

    return [
        tool("plan_write", "สร้างแผนเริ่มต้นที่แต่ละขั้นพิสูจน์ได้ด้วย tool", {
            "steps": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        }, ["steps"]),
        tool("plan_revise", "แก้เฉพาะงานที่ยังไม่เสร็จเมื่อ Observation สั่ง replan", {
            "reason": {"type": "string"},
            "future_steps": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        }, ["reason", "future_steps"]),
        tool("observe", "ตีความ MCP result ล่าสุดเทียบกับ active plan step", {
            "action_succeeded": {"type": "boolean"},
            "supports_step": {"type": "boolean"},
            "evidence_complete": {"type": "boolean"},
            "proven_claims": {"type": "array", "items": {"type": "string"}},
            "contradicted_claims": {"type": "array", "items": {"type": "string"}},
            "decision": {
                "type": "string",
                "enum": ["accept", "retry", "query_more", "replan", "stop"],
            },
            "reason": {"type": "string"},
        }, [
            "action_succeeded", "supports_step", "evidence_complete",
            "proven_claims", "contradicted_claims", "decision", "reason",
        ]),
    ]


def visible_tools(state: PlannerState | None, registry: ToolRegistry) -> list[dict]:
    tools = {item["function"]["name"]: item for item in internal_tools()}
    if state is None:
        return [tools["plan_write"]]
    if state.awaiting_observation:
        last = state.observations[-1] if state.observations else None
        return [tools["plan_revise"]] if last and last.decision == "replan" else [tools["observe"]]
    if state.complete or state.stopped:
        return []
    return [tools["plan_revise"], *registry.openai_tools]


def state_context(state: PlannerState | None) -> str:
    if state is None:
        return "ยังไม่มีแผน: ต้องเรียก plan_write"
    text = state.render()
    if state.awaiting_observation:
        text += "\n\nMCP action ล่าสุด:\n" + json.dumps(
            state.latest_action, ensure_ascii=False, indent=2
        )
        text += "\nMCP result ล่าสุด:\n" + str(state.latest_result)
        text += "\nต้องเรียก observe เท่านั้น"
    return text


def run(
    question: str,
    registry: ToolRegistry,
    max_turns: int = 30,
    return_details: bool = False,
):
    state: PlannerState | None = None
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]

    for turn in range(1, max_turns + 1):
        messages.append({"role": "system", "content": state_context(state)})
        tools = visible_tools(state, registry)
        response = llm.chat(messages=messages, tools=tools)
        message = response.choices[0].message

        if not message.tool_calls:
            if state is None or (not state.complete and not state.stopped):
                messages.append({"role": "assistant", "content": message.content or ""})
                messages.append({"role": "user", "content": (
                    "ยังจบไม่ได้: ทำตาม state และเรียก tool ที่เปิดให้ใช้"
                )})
                continue
            print(f"\n[ANSWER]\n{message.content}")
            details = {
                "answer": message.content,
                "planner": asdict(state),
                "turns": turn,
            }
            return details if return_details else message.content

        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [call.model_dump() for call in message.tool_calls],
        })

        if len(message.tool_calls) != 1:
            rejection = (
                "[RUNTIME REJECTED] เรียกได้ครั้งละหนึ่ง tool เท่านั้น "
                "เพื่อรักษาลำดับ Action → Observation"
            )
            print(rejection)
            for call in message.tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": rejection,
                })
            continue

        for call in message.tool_calls:
            name = call.function.name
            arguments = json.loads(call.function.arguments or "{}")
            try:
                if name == "plan_write":
                    if state is not None:
                        raise ValueError("plan_write ใช้ได้ครั้งเดียว; ใช้ plan_revise")
                    state = PlannerState(
                        goal=question,
                        steps=[
                            PlanStep(index + 1, task)
                            for index, task in enumerate(arguments["steps"])
                        ],
                    )
                    state.activate_next()
                    result = state.render()
                    print(f"\n[PLAN]\n{result}")
                elif name == "plan_revise":
                    if state is None:
                        raise ValueError("ยังไม่มีแผน")
                    state.revise(arguments["reason"], arguments["future_steps"])
                    result = state.render()
                    print(f"\n[REPLAN]\n{result}")
                elif name == "observe":
                    if state is None:
                        raise ValueError("ยังไม่มีแผน")
                    observation = ObservationState(**arguments)
                    state.observe(observation)
                    result = state.render()
                    print(
                        f"\n[OBSERVATION] decision={observation.decision} "
                        f"reason={observation.reason}\n{result}"
                    )
                else:
                    if state is None:
                        raise ValueError("ต้องสร้างแผนก่อนเรียก MCP")
                    result = registry.dispatch(name, arguments)
                    state.record_action(name, arguments, result, call.id)
                    print(
                        f"\n[ACTION] step={state.latest_action['step_id']} "
                        f"tool={name}\n[RESULT] {result[:500]}"
                    )
            except (KeyError, TypeError, ValueError) as error:
                result = f"[RUNTIME REJECTED] {error}"
                print(result)

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    raise RuntimeError(f"agent เกิน max_turns={max_turns} โดยยังทำงานไม่จบ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure Python Planner + Observation")
    parser.add_argument("question", nargs="?", default=(
        "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก และสรุปจากหลักฐาน"
    ))
    parser.add_argument("--max-turns", type=int, default=30)
    args = parser.parse_args()

    registry = ToolRegistry()
    count = registry.add_server(config.MCP_SERVER_URL)
    print(f"[MCP] discovered={count} tools={registry.tool_names}")
    print(f"[USER] {args.question}")
    try:
        run(args.question, registry, max_turns=args.max_turns)
    finally:
        registry.close()


if __name__ == "__main__":
    main()
