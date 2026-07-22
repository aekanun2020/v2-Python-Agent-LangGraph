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
from labs.lab6_todo.circuit_breaker import FailureCircuitBreaker
from labs.lab6_todo.contract_runtime import (
    ResolvedContract, resolve_contract, validate_final_contract,
)
from labs.lab6_todo.observation_types import ActionHint
from labs.lab6_todo.observation_types import EvidenceRequirement
from labs.lab6_todo.capabilities import (
    CAPABILITY_CATALOG, EVIDENCE_PREDICATE_CATALOG,
    validate_capability_requirements, validate_declared_capability,
    validate_evidence_predicate,
)
from labs.lab6_todo.observation_router import (
    assess_observation_risk, routed_decision, validate_routing_mode,
)

SYSTEM = """คุณคือ data agent ที่ทำงานตามแผน, schema และหลักฐานจริงจาก MCP
รักษาความหมายของ dimension และ metric จากคำถามเดิม ห้ามแทนคำที่คล้ายกันเอง
หากข้อมูลมีเพียง proxy ให้ระบุ proxy และข้อจำกัด ห้ามอ้างเหตุและผลจาก association
ห้ามระบุสกุลเงินถ้า schema หรือ evidence ไม่ได้บอกหน่วย และห้ามกล่าวว่า field ไม่มีโดยไม่ตรวจ schema
ก่อนเรียก MCP ต้องใช้ plan_write แล้ว plan_start ทีละขั้น
ทุก plan step ต้องประกาศ required_capability และ evidence_requirements แบบ typed
เลือก required_capability จาก: schema_inspection, sample_rows, query_execution, aggregation, comparison, existence_check
เลือก evidence predicate จาก: inspectable_payload, schema_inspected, rows_returned, aggregation_executed, comparison_executed, existence_checked
description ใช้อธิบายให้มนุษย์อ่านเท่านั้น runtime จะไม่เดา capability จากข้อความ
อย่าสร้างขั้น "สรุปคำตอบ" แยกต่างหาก เพราะขั้นต้องมีหลักฐานจาก MCP
ผล MCP จะถูก runtime ผูกเป็น evidence ของขั้นที่ in_progress โดยอัตโนมัติ
เมื่อ observation รับหลักฐาน runtime จะ complete ขั้นนั้นอัตโนมัติ ไม่ต้องเรียก plan_complete ซ้ำ
ถ้าหลักฐานทำให้แผนเดิมไม่พอให้ plan_revise
ตอบสุดท้ายได้เมื่อทุกขั้น completed เท่านั้น ใช้ T-SQL TOP ไม่ใช้ LIMIT"""

def normalize_typed_plan_steps(raw_steps, *, revised: bool = False) -> list[PlanStep]:
    """Parse model-declared intent without inferring semantics from description text."""
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan steps must be a non-empty array")
    steps: list[PlanStep] = []
    for index, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"steps[{index}] must be a typed object, not free text")
        description = item.get("description")
        capability = item.get("required_capability")
        raw_requirements = item.get("evidence_requirements")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"steps[{index}].description must be non-empty")
        if not isinstance(capability, str):
            raise ValueError(f"steps[{index}].required_capability is required")
        validate_declared_capability(capability)
        if not isinstance(raw_requirements, list) or not raw_requirements:
            raise ValueError(f"steps[{index}].evidence_requirements must be non-empty")
        requirements: list[EvidenceRequirement] = []
        for req_index, raw in enumerate(raw_requirements, start=1):
            if not isinstance(raw, dict):
                raise ValueError(
                    f"steps[{index}].evidence_requirements[{req_index}] must be an object"
                )
            claim_id = raw.get("claim_id")
            predicate = raw.get("predicate")
            if not isinstance(claim_id, str) or not claim_id.strip():
                raise ValueError("evidence requirement claim_id must be non-empty")
            if not isinstance(predicate, str):
                raise ValueError("evidence requirement predicate is required")
            validate_evidence_predicate(predicate)
            requirements.append(EvidenceRequirement(
                claim_id=claim_id.strip(), predicate=predicate,
                target=str(raw.get("target", "")).strip(),
            ))
        validate_capability_requirements(capability, requirements)
        status = item.get("status", "pending") if revised else "pending"
        step_id = item.get("id", index) if revised else index
        if status not in ("pending", "in_progress", "completed", "blocked"):
            raise ValueError(f"steps[{index}].status is invalid")
        if not isinstance(step_id, int):
            raise ValueError(f"steps[{index}].id must be an integer")
        steps.append(PlanStep(
            id=step_id, description=description.strip(), status=status,
            required_capability=capability, evidence_requirements=requirements,
        ))
    return steps


def require_final_answer(content) -> str:
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "final answer is empty; return a non-empty user-facing synthesis from accepted evidence"
        )
    return content.strip()


def validate_final_semantics(question: str, answer: str,
                             accepted_evidence: list[dict] | None = None,
                             contract: ResolvedContract | None = None) -> None:
    """Apply final-answer rules supplied by the resolved extension contract."""
    if contract is None:
        contract = resolve_contract(question)
    queries = " ".join(
        str(item.get("action", item.get("tool_arguments", {})).get("query", "")).lower()
        for item in (accepted_evidence or [])
    )
    failures = validate_final_contract(contract, answer, queries)
    if failures:
        raise ValueError("final semantic gate rejected: " + "; ".join(failures))


def build_goal_contract(question: str) -> str:
    contract = resolve_contract(question)
    return contract.system_context if contract else ""


def semantic_recovery_hint(failed: list[str], unsupported_claims=None) -> str:
    del failed
    return " | ".join(
        claim.basis for claim in (unsupported_claims or []) if claim.basis
    )


def planner_tools() -> list[dict]:
    def tool(name, description, properties, required):
        return {"type": "function", "function": {"name": name, "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required}}}
    evidence_requirement = {
        "type": "object",
        "properties": {
            "claim_id": {"type": "string"},
            "predicate": {"type": "string", "enum": list(EVIDENCE_PREDICATE_CATALOG)},
            "target": {"type": "string"},
        },
        "required": ["claim_id", "predicate"],
    }
    typed_step_properties = {
        "description": {"type": "string"},
        "required_capability": {"type": "string", "enum": list(CAPABILITY_CATALOG)},
        "evidence_requirements": {
            "type": "array", "minItems": 1, "items": evidence_requirement,
        },
    }
    return [
        tool("plan_write", "Create only MCP-verifiable data/schema/query steps. Never include summary, analysis, report, recommendation, final-answer, or presentation steps.", {
            "goal": {"type": "string"},
            "steps": {"type": "array", "minItems": 1, "items": {
                "type": "object", "properties": typed_step_properties,
                "required": ["description", "required_capability", "evidence_requirements"],
            }},
        }, ["goal", "steps"]),
        tool("plan_start", "เลือกขั้นเดียวที่จะเริ่มทำ", {
            "step_id": {"type": "integer"},
        }, ["step_id"]),
        tool("plan_complete", "ขอปิดขั้น; runtime จะปฏิเสธถ้าไม่มี tool evidence", {
            "step_id": {"type": "integer"},
        }, ["step_id"]),
        tool("plan_revise", "Revise only MCP-verifiable steps; never add synthesis, summary, report, recommendation, or final-answer steps.", {
            "reason": {"type": "string"},
            "steps": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {
                "id": {"type": "integer"},
                **typed_step_properties,
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"]},
            }, "required": ["id", "description", "required_capability", "evidence_requirements", "status"]}},
        }, ["reason", "steps"]),
    ]


def run(question: str, registry: ToolRegistry, max_steps: int = 60, tool_validator=None,
        dynamic_observation: bool = False, prompt_semantic_review: bool = False,
        observation_routing_mode: str = "rules"):
    plan: PlannerState | None = None
    trace: list[dict] = []
    accepted_facts: dict[str, float] = {}
    breaker = FailureCircuitBreaker()
    routing_mode = validate_routing_mode(
        "enforce" if prompt_semantic_review else observation_routing_mode
    )
    tools = planner_tools() + registry.openai_tools
    messages = [{"role": "system", "content": SYSTEM}]
    contract = resolve_contract(question)
    goal_contract = contract.system_context if contract else ""
    if goal_contract:
        messages.append({"role": "system", "content": goal_contract})
    messages.append({"role": "user", "content": question})

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
                    # Do not spend a reviewer call—or ask it for more evidence—until
                    # the deterministic planner proves every step is complete.
                    plan.approve_answer()
                    evidence_payload = [item.as_dict() for item in plan.accepted_evidence]
                    validate_final_semantics(
                        question, final_answer, evidence_payload, contract
                    )
                    if routing_mode in ("shadow", "enforce"):
                        final_review = review_final_answer(
                            goal=question,
                            answer=final_answer,
                            accepted_evidence=evidence_payload,
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
                            plan.answer_approved = False
                            raise ValueError(
                                "final semantic reviewer rejected: "
                                f"decision={final_review.decision}; {final_review.reason}; "
                                f"next={final_review.suggested_next_action}"
                            )
                    print(f"[ANSWER APPROVED] revision={plan.revision} tool_calls={len(trace)}")
                    print(final_answer)
                    return {"answer": final_answer, "planner": plan, "tool_trace": trace}
                except ValueError as exc:
                    plan.answer_approved = False
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
                    if plan is not None:
                        raise ValueError("plan_write is allowed once; use plan_revise")
                    typed_steps = normalize_typed_plan_steps(args["steps"])
                    plan = PlannerState(args["goal"], typed_steps)
                    result = plan.render()
                elif plan is None:
                    raise ValueError("ต้องเรียก plan_write ก่อน tool อื่น")
                elif name == "plan_start":
                    plan.start(args["step_id"]); result = plan.render()
                elif name == "plan_complete":
                    plan.complete(args["step_id"]); result = plan.render()
                elif name == "plan_revise":
                    revised = normalize_typed_plan_steps(args["steps"], revised=True)
                    plan.revise(revised, args["reason"]); result = plan.render()
                else:
                    active = [step for step in plan.steps if step.status == "in_progress"]
                    if len(active) != 1:
                        raise ValueError("ต้องมี plan step ที่ in_progress หนึ่งขั้นก่อนเรียก MCP")
                    rejection = tool_validator(name, args) if tool_validator else None
                    if rejection:
                        revised = [
                            PlanStep(
                                id=step.id, description=step.description,
                                status=step.status, evidence=list(step.evidence),
                                required_capability=step.required_capability,
                                evidence_requirements=list(step.evidence_requirements),
                            )
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
                            contract=contract,
                            required_capability=active[0].required_capability,
                            evidence_requirements=active[0].evidence_requirements,
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
                            recovery = semantic_recovery_hint(
                                observation.failed, observation.unsupported_claims
                            )
                            failure_count, escalation = breaker.record(
                                step_id=active[0].id, tool=name,
                                decision=observation.decision, failed=observation.failed,
                            )
                            result += "\n\n[OBSERVATION POLICY]\n" + json.dumps(
                                observation.as_dict(), ensure_ascii=False
                            ) + "\nผลนี้ยังไม่ถูกบันทึกเป็น evidence; retry/query_more/replan ตาม decision"
                            if recovery:
                                result += "\n[ACTIONABLE FIX] " + recovery
                            if escalation == "replan":
                                observation.decision = "replan"
                                observation.suggested_action = ActionHint(
                                    "replan", "Repeated failure requires a different action capability"
                                )
                                trace[-1]["observation"] = observation.as_dict()
                                result += (
                                    f"\n[CIRCUIT BREAKER] repeated failure={failure_count}; "
                                    "ต้อง plan_revise และเปลี่ยน action capability"
                                )
                            elif escalation == "stop":
                                observation.decision = "stop"
                                observation.suggested_action = ActionHint(
                                    "stop", "Repeated identical failure reached the fail-fast limit"
                                )
                                trace[-1]["observation"] = observation.as_dict()
                                raise RuntimeError(
                                    f"circuit breaker stopped repeated failure after {failure_count} attempts"
                                )
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
                                 observation=observation.as_dict() if observation else None,
                                 action=args,
                                 proven_claim_ids=[
                                     claim.id for claim in observation.proven_claims
                                 ] if observation else [])
                    if dynamic_observation:
                        plan.complete(active[0].id)
                    breaker.clear_step(active[0].id)
                    result += (
                        "\n\n[RUNTIME STATE]\n" + plan.render()
                        + "\nหลักฐานถูกรับและ step completed อัตโนมัติ; "
                        "next transition: plan_start(step_id ของ pending step ถัดไป) "
                        "หรือเขียน final answer เมื่อทุก step completed"
                    )
                    if dynamic_observation:
                        accepted_facts.update(extract_numeric_facts(result))
                    if not dynamic_observation:
                        trace.append({"step_id": active[0].id, "tool": name, "tool_call_id": call_id})
                    print(f"[EVIDENCE] step={active[0].id} tool={name} id={call_id}")
            except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                result = f"[RUNTIME REJECTED] {exc}"
                if plan is not None:
                    result += "\n[CURRENT PLAN]\n" + plan.render()
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
