"""Lab 6 enhanced — evidence-driven planner in a plain Python agent loop.

No LangGraph is used. Python owns plan state, evidence capture, transitions and
the answer gate; the model only proposes actions through tools.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import config, llm
from labs.core.registry import ToolRegistry
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState
from labs.lab6_todo.observation_policy import extract_numeric_facts, observe_result

SYSTEM = """คุณคือ HR data agent ที่ทำงานตามแผนและหลักฐานจริง
ก่อนเรียก MCP ต้องใช้ plan_write แล้ว plan_start ทีละขั้น
ทุก plan step ต้องเป็นขั้นค้น/ตรวจข้อมูลด้วย MCP อย่าสร้างขั้น "สรุปคำตอบ" แยกต่างหาก
ผล MCP จะถูก runtime ผูกเป็น evidence ของขั้นที่ in_progress โดยอัตโนมัติ
หลังได้หลักฐานให้เรียก plan_complete; ถ้าหลักฐานทำให้แผนเดิมไม่พอให้ plan_revise
ตอบสุดท้ายได้เมื่อทุกขั้น completed เท่านั้น ใช้ T-SQL TOP ไม่ใช้ LIMIT"""

NON_EVIDENCE_STEP_WORDS = (
    "สรุป", "นำเสนอ", "รายงาน", "ข้อเสนอแนะ", "วิเคราะห์ผล", "ตีความ", "ข้อจำกัด",
    "summary", "summarize", "synthesis", "synthesize", "final", "answer", "report",
    "insight", "recommend", "interpret", "evaluate", "assess", "limitation",
)


def validate_plan_descriptions(descriptions: list[str]) -> None:
    invalid = [text for text in descriptions if any(word in text.lower() for word in NON_EVIDENCE_STEP_WORDS)]
    if invalid:
        raise ValueError(
            "plan steps must be MCP-verifiable; final synthesis is not a plan step: "
            + " | ".join(invalid)
        )


def planner_tools() -> list[dict]:
    def tool(name, description, properties, required):
        return {"type": "function", "function": {"name": name, "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required}}}
    return [
        tool("plan_write", "Create only MCP-verifiable data/schema/query steps. Never include summary, analysis, report, recommendation, final-answer, or presentation steps.", {
            "goal": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
        }, ["goal", "steps"]),
        tool("plan_start", "เลือกขั้นเดียวที่จะเริ่มทำ", {
            "step_id": {"type": "integer"},
        }, ["step_id"]),
        tool("plan_complete", "ขอปิดขั้น; runtime จะปฏิเสธถ้าไม่มี tool evidence", {
            "step_id": {"type": "integer"},
        }, ["step_id"]),
        tool("plan_revise", "Revise only MCP-verifiable steps; never add synthesis, summary, report, recommendation, or final-answer steps.", {
            "reason": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "integer"}, "description": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"]},
            }, "required": ["id", "description", "status"]}},
        }, ["reason", "steps"]),
    ]


def run(question: str, registry: ToolRegistry, max_steps: int = 60, tool_validator=None,
        dynamic_observation: bool = False):
    plan: PlannerState | None = None
    trace: list[dict] = []
    accepted_facts: dict[str, float] = {}
    tools = planner_tools() + registry.openai_tools
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]

    for turn in range(1, max_steps + 1):
        response = llm.chat(messages=messages, tools=tools)
        message = response.choices[0].message
        if not message.tool_calls:
            if plan is None:
                feedback = "Answer gate rejected: ยังไม่มี plan_write"
            else:
                try:
                    plan.approve_answer()
                    print(f"[ANSWER APPROVED] revision={plan.revision} tool_calls={len(trace)}")
                    print(message.content)
                    return {"answer": message.content, "planner": plan, "tool_trace": trace}
                except ValueError as exc:
                    feedback = str(exc)
            print(f"[ANSWER REJECTED] {feedback}")
            messages.append({"role": "assistant", "content": message.content or ""})
            messages.append({"role": "user", "content": f"[RUNTIME GATE] {feedback}. ทำงานต่อและเรียก tool ที่จำเป็น"})
            continue

        messages.append({"role": "assistant", "content": message.content or "",
                         "tool_calls": [call.model_dump() for call in message.tool_calls]})
        for call in message.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            try:
                if name == "plan_write":
                    validate_plan_descriptions(args["steps"])
                    plan = PlannerState(args["goal"], [PlanStep(i + 1, text) for i, text in enumerate(args["steps"])])
                    result = plan.render()
                elif plan is None:
                    raise ValueError("ต้องเรียก plan_write ก่อน tool อื่น")
                elif name == "plan_start":
                    plan.start(args["step_id"]); result = plan.render()
                elif name == "plan_complete":
                    plan.complete(args["step_id"]); result = plan.render()
                elif name == "plan_revise":
                    validate_plan_descriptions([item["description"] for item in args["steps"]])
                    revised = [PlanStep(item["id"], item["description"], item["status"]) for item in args["steps"]]
                    plan.revise(revised, args["reason"]); result = plan.render()
                else:
                    active = [step for step in plan.steps if step.status == "in_progress"]
                    if len(active) != 1:
                        raise ValueError("ต้องมี plan step ที่ in_progress หนึ่งขั้นก่อนเรียก MCP")
                    rejection = tool_validator(name, args) if tool_validator else None
                    if rejection:
                        revised = [
                            PlanStep(step.id, step.description, step.status, list(step.evidence))
                            for step in plan.steps
                        ]
                        plan.revise(revised, f"analytical contract rejected tool call: {rejection}")
                        raise ValueError(f"ANALYTICAL CONTRACT: {rejection}; revise the query")
                    result = registry.dispatch(name, args)
                    call_id = call.id or str(uuid.uuid4())
                    observation = None
                    if dynamic_observation:
                        observation = observe_result(
                            step_description=active[0].description, tool=name, result=result,
                            tool_arguments=args, semantic_checks=True,
                            prior_facts=accepted_facts or None,
                        )
                        trace.append({"step_id": active[0].id, "tool": name,
                                      "tool_call_id": call_id, "observation": observation.as_dict()})
                        print(f"[OBSERVATION] step={active[0].id} type={observation.result_type} "
                              f"decision={observation.decision} reason={observation.reason}")
                        if observation.decision != "accept":
                            result += "\n\n[OBSERVATION POLICY]\n" + json.dumps(
                                observation.as_dict(), ensure_ascii=False
                            ) + "\nผลนี้ยังไม่ถูกบันทึกเป็น evidence; retry/query_more/replan ตาม decision"
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                            continue
                    plan.observe(active[0].id, tool=name, tool_call_id=call_id, result=result,
                                 observation=observation.as_dict() if observation else None)
                    if dynamic_observation:
                        accepted_facts.update(extract_numeric_facts(result))
                    if not dynamic_observation:
                        trace.append({"step_id": active[0].id, "tool": name, "tool_call_id": call_id})
                    print(f"[EVIDENCE] step={active[0].id} tool={name} id={call_id}")
            except (KeyError, TypeError, ValueError) as exc:
                result = f"[RUNTIME REJECTED] {exc}"
                print(result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    raise RuntimeError(f"planner exceeded max_steps={max_steps}")


def main():
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    question = sys.argv[1] if len(sys.argv) > 1 else (
        "สร้าง workforce risk matrix รายแผนกจาก skills, training, performance และ projects "
        "โดยตรวจ schema และป้องกันการ join ที่ทำให้ยอดซ้ำ"
    )
    try:
        run(question, registry)
    finally:
        registry.close()


if __name__ == "__main__":
    main()
