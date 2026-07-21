"""Lab 6 enhanced — evidence-driven planner in a plain Python agent loop.

No LangGraph is used. Python owns plan state, evidence capture, transitions and
the answer gate; the model only proposes actions through tools.
"""

from __future__ import annotations

import json
import argparse
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import config, llm
from labs.core.registry import ToolRegistry
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState
from labs.lab6_todo.observation_policy import extract_numeric_facts, observe_result
from labs.lab6_todo.semantic_reviewer import review_final_answer, review_observation
from labs.lab6_todo.observation_router import (
    assess_observation_risk, routed_decision, validate_routing_mode,
)

SYSTEM = """คุณคือ data agent ที่ทำงานตามแผน, schema และหลักฐานจริงจาก MCP
รักษาความหมายของ dimension และ metric จากคำถามเดิม ห้ามแทนคำที่คล้ายกันเอง
หากข้อมูลมีเพียง proxy ให้ระบุ proxy และข้อจำกัด ห้ามอ้างเหตุและผลจาก association
loan_status เช่น Current/Fully Paid/Charged Off คือผลหลังปล่อยกู้ ไม่ใช่ผลการอนุมัติ
ห้ามระบุสกุลเงินถ้า schema หรือ evidence ไม่ได้บอกหน่วย และห้ามกล่าวว่า field ไม่มีโดยไม่ตรวจ schema
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


def normalize_plan_descriptions(raw_steps) -> list[str]:
    """Tolerate a common model deviation: [{"description": "..."}] vs ["..."]."""
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan_write.steps must be a non-empty array")
    descriptions: list[str] = []
    for index, item in enumerate(raw_steps, start=1):
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("description") or item.get("text") or item.get("title")
        else:
            text = None
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"plan_write.steps[{index}] must be a string or object with description"
            )
        descriptions.append(text.strip())
    return descriptions


def require_final_answer(content) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "final answer is empty; return a non-empty user-facing synthesis from accepted evidence"
        )
    return content.strip()


def validate_final_semantics(question: str, answer: str) -> None:
    """Reject known claim-level category errors that SQL validation cannot see."""
    goal = question.lower()
    text = answer.lower()
    approval_amount_goal = any(token in goal for token in (
        "อนุมัติวงเงิน", "approved amount", "approval amount"
    ))
    failures: list[str] = []
    if approval_amount_goal:
        if any(token in text for token in ("อัตราการอนุมัติ", "approval rate")):
            failures.append(
                "ห้ามตีความ loan_status (เช่น Current/Fully Paid) เป็นการอนุมัติ"
            )
        if any(token in text for token in ("บาท", " thb", " usd", "$")):
            failures.append("ห้ามระบุสกุลเงินเมื่อ evidence ไม่มี currency metadata")
        missing_claim = re.search(
            r"(?:ไม่มีข้อมูล|ไม่มี\s*(?:field|ฟิลด์))[^.\n]{0,120}"
            r"(?:annual_inc|\bdti\b|home_ownership)",
            text,
        )
        if missing_claim:
            failures.append(
                "ห้ามอ้างว่า annual_inc/dti/home_ownership ไม่มี เพราะ MCP schema มี field เหล่านี้"
            )
    if failures:
        raise ValueError("final semantic gate rejected: " + "; ".join(failures))


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
        dynamic_observation: bool = False, prompt_semantic_review: bool = False,
        observation_routing_mode: str = "rules"):
    plan: PlannerState | None = None
    trace: list[dict] = []
    accepted_evidence: list[dict] = []
    accepted_facts: dict[str, float] = {}
    routing_mode = validate_routing_mode(
        "enforce" if prompt_semantic_review else observation_routing_mode
    )
    tools = planner_tools() + registry.openai_tools
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]

    for turn in range(1, max_steps + 1):
        response = llm.chat(messages=messages, tools=tools)
        message = response.choices[0].message
        if not message.tool_calls:
            final_review_decision = None
            if plan is None:
                feedback = "Answer gate rejected: ยังไม่มี plan_write"
            else:
                try:
                    final_answer = require_final_answer(message.content)
                    validate_final_semantics(question, final_answer)
                    if routing_mode in ("shadow", "enforce"):
                        final_review = review_final_answer(
                            goal=question,
                            answer=final_answer,
                            accepted_evidence=accepted_evidence,
                        )
                        final_decision = (
                            final_review.decision if routing_mode == "enforce" else "accept"
                        )
                        final_review_decision = final_review.decision
                        print(
                            f"[FINAL SEMANTIC REVIEW] review={final_review.decision} "
                            f"mode={routing_mode} final={final_decision} "
                            f"reason={final_review.reason}"
                        )
                        if final_decision != "accept":
                            raise ValueError(
                                "final semantic reviewer rejected: "
                                f"decision={final_review.decision}; {final_review.reason}; "
                                f"next={final_review.suggested_next_action}"
                            )
                    plan.approve_answer()
                    print(f"[ANSWER APPROVED] revision={plan.revision} tool_calls={len(trace)}")
                    print(final_answer)
                    return {"answer": final_answer, "planner": plan, "tool_trace": trace}
                except ValueError as exc:
                    feedback = str(exc)
            print(f"[ANSWER REJECTED] {feedback}")
            messages.append({"role": "assistant", "content": message.content or ""})
            if final_review_decision == "query_more":
                instruction = (
                    "หลักฐานยังไม่พอสำหรับข้อกล่าวอ้างใน final answer; เรียก plan_revise "
                    "เพื่อเพิ่ม MCP-verifiable step แล้ว query เพิ่มตาม reviewer"
                )
            elif plan is not None and all(step.status == "completed" for step in plan.steps):
                instruction = (
                    "ทุกขั้น completed แล้ว ห้ามเรียก tool เพิ่ม; เขียน final answer ที่ไม่ว่าง "
                    "โดยสรุปจาก accepted evidence ให้ผู้ใช้อ่านได้ทันที"
                )
            else:
                instruction = "ทำงานต่อและเรียก tool ที่จำเป็น"
            messages.append({"role": "user", "content": f"[RUNTIME GATE] {feedback}. {instruction}"})
            continue

        messages.append({"role": "assistant", "content": message.content or "",
                         "tool_calls": [call.model_dump() for call in message.tool_calls]})
        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                if name == "plan_write":
                    descriptions = normalize_plan_descriptions(args["steps"])
                    validate_plan_descriptions(descriptions)
                    plan = PlannerState(
                        args["goal"],
                        [PlanStep(i + 1, text) for i, text in enumerate(descriptions)],
                    )
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
                            goal_description=question,
                        )
                        trace.append({"step_id": active[0].id, "tool": name,
                                      "tool_call_id": call_id, "observation": observation.as_dict()})
                        risk = assess_observation_risk(
                            hard=observation, step_description=active[0].description,
                            tool=name, tool_arguments=args,
                        )
                        trace[-1]["risk"] = risk.as_dict()
                        print(f"[OBSERVATION] step={active[0].id} type={observation.result_type} "
                              f"decision={observation.decision} reason={observation.reason}")
                        if observation.decision != "accept":
                            result += "\n\n[OBSERVATION POLICY]\n" + json.dumps(
                                observation.as_dict(), ensure_ascii=False
                            ) + "\nผลนี้ยังไม่ถูกบันทึกเป็น evidence; retry/query_more/replan ตาม decision"
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                            continue
                        if routing_mode in ("shadow", "enforce") and risk.reviewer_required:
                            semantic_review = review_observation(
                                goal=plan.goal, active_step=active[0].description,
                                analytical_contract=question, tool=name, tool_arguments=args,
                                result=result, prior_facts=accepted_facts or None,
                            )
                            final_observation_decision = routed_decision(
                                routing_mode, observation, semantic_review
                            )
                            trace[-1]["semantic_review"] = semantic_review.as_dict()
                            trace[-1]["routed_decision"] = final_observation_decision
                            trace[-1]["routing_mode"] = routing_mode
                            print(f"[SEMANTIC REVIEW] step={active[0].id} "
                                  f"risk={risk.level} review={semantic_review.decision} "
                                  f"mode={routing_mode} final={final_observation_decision}")
                            if final_observation_decision != "accept":
                                result += "\n\n[PROMPT SEMANTIC REVIEW]\n" + json.dumps(
                                    semantic_review.as_dict(), ensure_ascii=False
                                ) + "\nผลนี้ยังไม่ถูกบันทึกเป็น evidence"
                                messages.append({"role": "tool", "tool_call_id": call.id,
                                                 "content": result})
                                continue
                    plan.observe(active[0].id, tool=name, tool_call_id=call_id, result=result,
                                 observation=observation.as_dict() if observation else None)
                    accepted_evidence.append({
                        "step_id": active[0].id,
                        "step_description": active[0].description,
                        "tool": name,
                        "tool_arguments": args,
                        "result": result,
                    })
                    if dynamic_observation:
                        accepted_facts.update(extract_numeric_facts(result))
                    if not dynamic_observation:
                        trace.append({"step_id": active[0].id, "tool": name, "tool_call_id": call_id})
                    print(f"[EVIDENCE] step={active[0].id} tool={name} id={call_id}")
            except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                result = f"[RUNTIME REJECTED] {exc}"
                print(result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    raise RuntimeError(f"planner exceeded max_steps={max_steps}")


def main():
    default_question = (
        "สร้าง workforce risk matrix รายแผนกจาก skills, training, performance และ projects "
        "โดยตรวจ schema และป้องกันการ join ที่ทำให้ยอดซ้ำ"
    )
    parser = argparse.ArgumentParser(description="Pure Python evidence-driven HR agent")
    parser.add_argument("question", nargs="?", default=default_question,
                        help="คำถาม HR; ถ้าไม่ระบุจะใช้ workforce-risk example")
    parser.add_argument(
        "--routing-mode", choices=("rules", "shadow", "enforce"),
        default=os.environ.get("OBSERVATION_ROUTING_MODE", "rules"),
        help="rules=ไม่เรียก reviewer, shadow=review แต่ไม่ block, enforce=review และ block",
    )
    args = parser.parse_args()
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    try:
        prompt_review = os.environ.get("PROMPT_SEMANTIC_REVIEW", "0").lower() in (
            "1", "true", "yes"
        )
        run(args.question, registry, dynamic_observation=True,
            prompt_semantic_review=prompt_review,
            observation_routing_mode=args.routing_mode)
    finally:
        registry.close()


if __name__ == "__main__":
    main()
