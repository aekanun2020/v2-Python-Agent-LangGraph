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


EvidenceStatus = Literal["accept", "reject"]
NextAction = Literal["continue", "retry", "query_more", "replan", "stop"]

SYSTEM = """คุณคือ agent ที่ทำงานด้วยวงจร Thought → Action → Observation

กติกา:
1. เรียก plan_write ก่อนทำงาน ใช้จำนวนขั้น MCP ที่น้อยที่สุดและแต่ละขั้นต้องพิสูจน์ได้
   อย่าแยก filter/join/aggregate เป็นคนละ step ถ้า query เดียวทำและพิสูจน์พร้อมกันได้
2. ทำ MCP action ได้ครั้งละหนึ่ง action สำหรับ step ที่ active
3. หลัง MCP คืนผล Python จะเรียก Observer LLM ด้วย fresh context โดยอัตโนมัติ
4. Observer จะตีความตามเป้าหมาย, active step, action และผลจริง:
   - action สำเร็จหรือไม่
   - result สนับสนุน step หรือไม่
   - evidence ครบหรือยัง
   - claim ใดถูกพิสูจน์หรือขัดแย้ง
   - แยก evidence_status (accept/reject) ออกจาก next_action
     (continue/retry/query_more/replan/stop)
   - คืน satisfied_requirement_ids และ missing_requirement_ids โดยใช้ ID จาก active step
5. evidence_status=accept เฉพาะเมื่อ action สำเร็จ, result สนับสนุน step,
   evidence ครบ และไม่มี missing requirement
6. ใช้ plan_revise เมื่อผลจริงทำให้แผนเดิมไม่เหมาะสม
7. ตอบสุดท้ายจาก accepted evidence เท่านั้น และบอกข้อจำกัดที่หลักฐานพิสูจน์ไม่ได้

Observation เป็น semantic judgment ของคุณ ไม่ใช่ keyword matching ของ Python
และห้ามถือว่า tool สำเร็จเท่ากับคำตอบถูกเชิงความหมาย
ถ้าเขียน T-SQL และเปรียบเทียบ Unicode text ให้ใช้ N'...' เป็น string literal
เรียก tool ครั้งละหนึ่งรายการเท่านั้น ห้ามส่ง parallel tool calls
"""

FINAL_OBSERVER_SYSTEM = """คุณคือ Final Observer อิสระ ห้ามใช้ความรู้หรือบทสนทนานอก payload
ตรวจทุก material claim, number, denominator, aggregation, NULL/absence, scope และข้อจำกัด
กับ accepted evidence และ acceptance requirements ห้ามอนุมัติเพียงเพราะคำตอบดูสมเหตุผล

กฎ canonical grounding:
- category value, status, identifier และชื่อหน่วยงานที่อ้างจาก evidence ต้องคงข้อความเดิม
- อนุญาตเปลี่ยนรูปแบบตาราง ลำดับ คำอธิบาย และการจัดตัวเลขเมื่อค่าไม่เปลี่ยน
- อนุญาตคำแปลเมื่อแสดง canonical value เดิมไว้และระบุคำแปลแยกอย่างชัดเจน
- ห้ามแปล normalize หรือเปลี่ยน canonical value แทนค่าจริง หากไม่มี evidence mapping
- ห้ามสร้าง schema facts, category examples, mappings หรือ data limitations ที่ไม่มี evidence
- methodological caveat ทั่วไปทำได้เมื่อไม่ถูกเขียนเป็นข้อเท็จจริงเฉพาะของข้อมูล

approve เมื่อครบและ grounded; rewrite เมื่อหลักฐานครบแต่ถ้อยคำ canonical label
หรือ presentation ผิด; query_more เมื่อหลักฐานหรือ calculation proof ไม่ครบ;
stop เมื่อทำต่อไม่ได้ ต้องเรียก submit_final_review หนึ่งครั้ง
"""


@dataclass
class PlanStep:
    id: int
    task: str
    acceptance_requirements: list[dict]
    status: Literal["pending", "active", "completed"] = "pending"
    evidence: list[dict] = field(default_factory=list)
    working_evidence: list[dict] = field(default_factory=list)


@dataclass
class ObservationState:
    action_succeeded: bool
    supports_step: bool
    evidence_complete: bool
    proven_claims: list[str]
    contradicted_claims: list[str]
    satisfied_requirement_ids: list[str]
    missing_requirement_ids: list[str]
    evidence_status: EvidenceStatus
    next_action: NextAction
    reason: str


@dataclass
class FinalReview:
    verdict: Literal["approve", "rewrite", "query_more", "stop"]
    supported_claims: list[str]
    unsupported_claims: list[str]
    missing_requirements: list[str]
    reason: str
    revised_answer: str = ""


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
    replan_authorized: bool = False
    final_feedback: str = ""

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
        if self.replan_authorized:
            raise ValueError("Observer สั่ง replan: ต้อง plan_revise ก่อนเรียก MCP")
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
        required = {item["id"] for item in self.active_step.acceptance_requirements}
        previously_satisfied = {
            requirement_id
            for evidence in self.active_step.working_evidence
            for requirement_id in evidence.get("satisfied_requirement_ids", [])
        }
        satisfied = previously_satisfied | set(observation.satisfied_requirement_ids)
        unresolved = required - satisfied
        if observation.evidence_status == "accept" and not (
            observation.action_succeeded
            and observation.supports_step
            and observation.evidence_complete
            and not unresolved
        ):
            raise ValueError(
                "accept ไม่ได้: action/result/evidence/requirements ยังไม่ผ่านครบ"
            )
        if observation.evidence_status == "reject" and observation.next_action == "continue":
            raise ValueError("reject แล้ว continue ไม่ได้")

        self.observations.append(observation)
        evidence_record = {
                **(self.latest_action or {}),
                "result": self.latest_result,
                "proven_claims": observation.proven_claims,
                "contradicted_claims": observation.contradicted_claims,
                "satisfied_requirement_ids": observation.satisfied_requirement_ids,
        }
        if observation.action_succeeded and observation.supports_step:
            self.active_step.working_evidence.append(evidence_record)
        if observation.evidence_status == "accept":
            self.active_step.evidence.extend(self.active_step.working_evidence)
            self.active_step.working_evidence = []
            self.active_step.status = "completed"
        self.awaiting_observation = False
        self.latest_action = None
        self.latest_result = None

        if observation.next_action == "continue":
            self.activate_next()
        elif observation.next_action in {"retry", "query_more"}:
            if observation.evidence_status == "accept":
                self.activate_next()
        elif observation.next_action == "replan":
            self.replan_authorized = True
        elif observation.next_action == "stop":
            self.stopped = True

    def revise(self, reason: str, future_steps: list[dict]) -> None:
        if not self.replan_authorized:
            raise ValueError("plan_revise ต้องได้รับ next_action=replan จาก Observer ก่อน")
        if not future_steps:
            raise ValueError("future_steps ต้องมีอย่างน้อยหนึ่งขั้น")
        completed = [step for step in self.steps if step.status == "completed"]
        start = len(completed) + 1
        self.steps = completed + [
            PlanStep(
                start + index,
                item["task"],
                item["acceptance_requirements"],
            )
            for index, item in enumerate(future_steps)
        ]
        self.revision += 1
        self.replan_authorized = False
        self.final_feedback = ""
        self.awaiting_observation = False
        self.latest_action = None
        self.latest_result = None
        self.activate_next()

    def render(self) -> str:
        marks = {"pending": "[ ]", "active": "[~]", "completed": "[x]"}
        rows = [f"Goal: {self.goal} | revision={self.revision}"]
        rows.extend(
            f"{marks[step.status]} {step.id}. {step.task} "
            f"(requirements={len(step.acceptance_requirements)}, evidence={len(step.evidence)})"
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

    step_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string"},
            "acceptance_requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "stable short ID unique within this step",
                        },
                        "description": {"type": "string"},
                    },
                    "required": ["id", "description"],
                    "additionalProperties": False,
                },
                "minItems": 1,
                "description": (
                    "รายการหลักฐานที่ต้องพิสูจน์เพื่อ complete step; "
                    "ต้องครอบคลุมสูตร denominator, scope และข้อจำกัดที่ผู้ใช้ร้องขอ"
                ),
            },
        },
        "required": ["task", "acceptance_requirements"],
        "additionalProperties": False,
    }
    return [
        tool("plan_write", "สร้างแผนเริ่มต้นที่แต่ละขั้นพิสูจน์ได้ด้วย tool", {
            "steps": {"type": "array", "items": step_schema, "minItems": 1},
        }, ["steps"]),
        tool("plan_revise", "แก้เฉพาะงานที่ยังไม่เสร็จเมื่อ Observation สั่ง replan", {
            "reason": {"type": "string"},
            "future_steps": {"type": "array", "items": step_schema, "minItems": 1},
        }, ["reason", "future_steps"]),
    ]


def observation_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_observation",
            "description": "ส่ง semantic Observation ของ MCP result ล่าสุด",
            "parameters": {
                "type": "object",
                "properties": {
            "action_succeeded": {"type": "boolean"},
            "supports_step": {"type": "boolean"},
            "evidence_complete": {"type": "boolean"},
            "proven_claims": {"type": "array", "items": {"type": "string"}},
            "contradicted_claims": {"type": "array", "items": {"type": "string"}},
            "satisfied_requirement_ids": {
                "type": "array", "items": {"type": "string"},
            },
            "missing_requirement_ids": {
                "type": "array", "items": {"type": "string"},
            },
            "evidence_status": {
                "type": "string",
                "enum": ["accept", "reject"],
            },
            "next_action": {
                "type": "string",
                "enum": ["continue", "retry", "query_more", "replan", "stop"],
            },
            "reason": {"type": "string"},
                },
                "required": [
                    "action_succeeded", "supports_step", "evidence_complete",
                    "proven_claims", "contradicted_claims",
                    "satisfied_requirement_ids", "missing_requirement_ids",
                    "evidence_status", "next_action", "reason",
                ],
                "additionalProperties": False,
            },
        },
    }


def visible_tools(state: PlannerState | None, registry: ToolRegistry) -> list[dict]:
    tools = {item["function"]["name"]: item for item in internal_tools()}
    if state is None:
        return [tools["plan_write"]]
    if state.replan_authorized:
        return [tools["plan_revise"]]
    if state.awaiting_observation:
        return []
    if state.complete or state.stopped:
        return []
    return [tools["plan_revise"], *registry.openai_tools]


def state_context(state: PlannerState | None) -> str:
    if state is None:
        return "ยังไม่มีแผน: ต้องเรียก plan_write"
    text = state.render()
    if state.final_feedback:
        text += "\n\nFinal Observer feedback:\n" + state.final_feedback
    if state.awaiting_observation:
        text += "\n\nMCP action ล่าสุด:\n" + json.dumps(
            state.latest_action, ensure_ascii=False, indent=2
        )
        text += "\nMCP result ล่าสุด:\n" + str(state.latest_result)
        text += "\nPython กำลังส่งผลนี้ให้ Observer; executor ห้ามทำ action เพิ่ม"
    return text


def observe_latest(state: PlannerState, attempts: int = 3) -> ObservationState:
    """Run a fresh-context Observer immediately after an MCP action."""
    payload = {
        "goal": state.goal,
        "active_step": asdict(state.active_step),
        "prior_candidate_evidence": state.active_step.working_evidence,
        "action": state.latest_action,
        "exact_tool_result": state.latest_result,
    }
    messages = [
        {"role": "system", "content": (
            "คุณคือ Observer อิสระในวงจร TAO ใช้เฉพาะ payload นี้ "
            "ประเมินว่า exact tool result สนับสนุน active step จริงหรือไม่ "
            "รวม prior_candidate_evidence เมื่อพิจารณาว่าหลักฐานครบหรือยัง "
            "คืน requirement IDs เฉพาะ ID ที่อยู่ใน active_step เท่านั้น "
            "evidence_status=accept ได้เมื่อทุก requirement ID satisfied และไม่มี missing "
            "แยก evidence verdict ออกจาก next action; ใช้ replan เมื่อหลักฐานปัจจุบัน "
            "ถูกต้องแต่ทำให้ future plan ต้องเปลี่ยน ต้องเรียก submit_observation หนึ่งครั้ง"
        )},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    errors = []
    for _ in range(attempts):
        response = llm.chat(messages=messages, tools=[observation_tool()])
        message = response.choices[0].message
        calls = message.tool_calls or []
        if len(calls) == 1 and calls[0].function.name == "submit_observation":
            try:
                observation = ObservationState(
                    **json.loads(calls[0].function.arguments or "{}")
                )
                required_ids = {
                    item["id"] for item in state.active_step.acceptance_requirements
                }
                prior_ids = {
                    requirement_id
                    for evidence in state.active_step.working_evidence
                    for requirement_id in evidence.get("satisfied_requirement_ids", [])
                }
                observed_ids = prior_ids | set(observation.satisfied_requirement_ids)
                invalid_accept = observation.evidence_status == "accept" and not (
                    observation.action_succeeded
                    and observation.supports_step
                    and observation.evidence_complete
                    and required_ids.issubset(observed_ids)
                )
                invalid_continue = (
                    observation.evidence_status == "reject"
                    and observation.next_action == "continue"
                )
                if invalid_accept or invalid_continue:
                    observation.evidence_status = "reject"
                    observation.next_action = "query_more"
                    observation.evidence_complete = False
                    observation.reason = (
                        "runtime downgraded inconsistent Observer verdict: "
                        + observation.reason
                    )
                state.observe(observation)
                return observation
            except (TypeError, ValueError) as error:
                errors.append(str(error))
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [calls[0].model_dump()],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": calls[0].id,
                    "content": f"[RUNTIME REJECTED] {error}",
                })
                messages.append({"role": "user", "content": (
                    "แก้ structured observation จาก error โดยใช้ requirement IDs "
                    "ใน active_step ให้ตรงตัว"
                )})
                continue
        errors.append("Observer ไม่เรียก submit_observation หนึ่งครั้ง")
        messages.append({"role": "assistant", "content": message.content or ""})
        messages.append({"role": "user", "content": errors[-1]})
    raise RuntimeError("Observer failed closed: " + "; ".join(errors))


def final_review_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_final_review",
            "description": "ส่งผลตรวจคำตอบร่างเทียบกับ accepted evidence",
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {
                        "type": "string",
                        "enum": ["approve", "rewrite", "query_more", "stop"],
                    },
                    "supported_claims": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "unsupported_claims": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "missing_requirements": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "reason": {"type": "string"},
                    "revised_answer": {"type": "string"},
                },
                "required": [
                    "verdict", "supported_claims", "unsupported_claims",
                    "missing_requirements", "reason", "revised_answer",
                ],
                "additionalProperties": False,
            },
        },
    }


def accepted_evidence(state: PlannerState) -> list[dict]:
    return [
        {
            "step_id": step.id,
            "task": step.task,
            "acceptance_requirements": step.acceptance_requirements,
            "evidence": step.evidence,
        }
        for step in state.steps
    ]


def review_final_answer(
    question: str,
    state: PlannerState,
    draft_answer: str,
    attempts: int = 2,
) -> FinalReview:
    """Independent semantic review with a fresh context; no domain rules in Python."""
    payload = {
        "goal": question,
        "accepted_evidence": accepted_evidence(state),
        "draft_answer": draft_answer,
    }
    messages = [
        {"role": "system", "content": FINAL_OBSERVER_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    for _ in range(attempts):
        response = llm.chat(messages=messages, tools=[final_review_tool()])
        message = response.choices[0].message
        calls = message.tool_calls or []
        if len(calls) == 1 and calls[0].function.name == "submit_final_review":
            review = FinalReview(**json.loads(calls[0].function.arguments or "{}"))
            if review.verdict in {"approve", "rewrite"} and (
                review.unsupported_claims or review.missing_requirements
            ):
                review.verdict = "query_more"
                review.reason = (
                    "runtime fail-closed: reviewer reported unsupported or missing evidence; "
                    + review.reason
                )
            if review.verdict == "rewrite" and not review.revised_answer.strip():
                review.verdict = "query_more"
                review.reason = "runtime fail-closed: rewrite verdict has no revised answer"
            return review
        messages.append({"role": "assistant", "content": message.content or ""})
        messages.append({"role": "user", "content": (
            "ต้องเรียก submit_final_review หนึ่งครั้ง ห้ามตอบเป็นข้อความธรรมดา"
        )})
    raise RuntimeError("Final Observer ไม่คืน structured review")


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
            review = review_final_answer(question, state, message.content or "")
            print(
                f"\n[FINAL OBSERVATION] verdict={review.verdict} "
                f"reason={review.reason}"
            )
            if review.verdict == "query_more":
                state.replan_authorized = True
                state.final_feedback = review.reason
                messages.append({"role": "assistant", "content": message.content or ""})
                messages.append({"role": "user", "content": (
                    "Final Observer ปฏิเสธคำตอบ: " + review.reason
                    + "\nใช้ plan_revise เพิ่มขั้นที่พิสูจน์ missing requirements"
                )})
                continue
            if review.verdict == "stop":
                state.stopped = True
                raise RuntimeError("Final Observer สั่ง stop: " + review.reason)
            answer = (
                review.revised_answer
                if review.verdict == "rewrite"
                else (message.content or "")
            )
            print(f"\n[ANSWER]\n{answer}")
            details = {
                "answer": answer,
                "planner": asdict(state),
                "final_review": asdict(review),
                "turns": turn,
            }
            return details if return_details else answer

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
            allowed_names = {item["function"]["name"] for item in tools}
            if name not in allowed_names:
                result = (
                    f"[RUNTIME REJECTED] tool '{name}' ไม่เปิดใน phase นี้; "
                    f"allowed={sorted(allowed_names)}"
                )
                print(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })
                continue
            try:
                if name == "plan_write":
                    if state is not None:
                        raise ValueError("plan_write ใช้ได้ครั้งเดียว; ใช้ plan_revise")
                    state = PlannerState(
                        goal=question,
                        steps=[
                            PlanStep(
                                index + 1,
                                item["task"],
                                item["acceptance_requirements"],
                            )
                            for index, item in enumerate(arguments["steps"])
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
                else:
                    if state is None:
                        raise ValueError("ต้องสร้างแผนก่อนเรียก MCP")
                    result = registry.dispatch(name, arguments)
                    state.record_action(name, arguments, result, call.id)
                    print(
                        f"\n[ACTION] step={state.latest_action['step_id']} "
                        f"tool={name}\n[RESULT] {result[:500]}"
                    )
                    observation = observe_latest(state)
                    print(
                        f"\n[OBSERVATION] evidence={observation.evidence_status} "
                        f"next={observation.next_action} "
                        f"reason={observation.reason}\n{state.render()}"
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
