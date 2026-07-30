"""
Lab 6 — เพิ่ม TodoWrite ให้ Agent และทดสอบกับ multi-step task
อ้างอิง outline: บทที่ 2.2 / แบบฝึกหัดที่ 6

เพิ่ม internal tool 2 ตัวที่เก็บ todo list ใน state ของ agent:
  - todo_write(items)          : สร้าง todo list ก่อนเริ่มงานหลายขั้น
  - todo_update(index, status) : อัปเดตสถานะแต่ละข้อระหว่างทำงาน

รวมกับ MCP tools (จาก Lab 4) เพื่อให้ todo มี "งานจริง" ให้วางแผน เช่น
ดึงข้อมูลจาก MSSQL หลายขั้นแล้วสรุป

รัน:  python labs/lab6_todo/agent_todo.py
"""
import argparse
import sys, os, json, time
import httpx
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import llm, config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.context_state import (
    ActionKind,
    AgentPhase,
    ContextState,
)
from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    SemanticVerdict,
)
from labs.lab6_todo.claim_ledger import ClaimLedger
from labs.lab6_todo.claim_gate import verify_then_emit
from labs.lab6_todo.evidence_contract import (
    ContractDecision,
    validate_evidence_contract,
)
from labs.lab6_todo.dynamic_observer import (
    NextAction,
    build_claim_ledger,
    observe_tool_result,
)
from labs.lab6_todo.risk_router import (
    DeterministicDecision,
    final_semantic_risk,
    observe_deterministically,
)
from labs.lab6_todo.semantic_observer import (
    apply_bounded_rewrite,
    enforce_claim_alignment,
    review_final_answer,
)
from labs.lab6_todo.phase2_runtime import (
    Phase2Budget,
    RuntimeBudgetExhausted,
    hard_deadline,
)

SYSTEM = (
    "คุณคือ agent ที่ทำงานเป็นขั้นตอน ตอบเป็นภาษาไทย\n"
    "กฎ: ถ้างานมี 3 ขั้นขึ้นไป ให้เรียก todo_write เขียนแผนก่อนเริ่มลงมือ "
    "แล้วทำทีละข้อ เรียก todo_update เปลี่ยนสถานะเป็น 'doing' ก่อนทำ และ 'done' เมื่อเสร็จ\n"
    "index ของ todo_update ให้ใช้เลขข้อแบบ 1-based ตามที่แสดงใน list (ข้อแรก = 1)\n"
    "เมื่อทำครบทุกข้อแล้ว (todo เป็น done หมด) ให้สรุปข้อค้นพบเชิงธุรกิจเป็นข้อความสุดท้าย โดยไม่ต้องเรียก tool อีก\n"
    "ใช้ MCP tools ของฐานข้อมูล (เรียก get_database_context ก่อนเขียน T-SQL ใช้ TOP ไม่ใช่ LIMIT)"
)


class TodoState:
    """เก็บ todo list ไว้ใน state ของ agent (in-memory)."""
    def __init__(self):
        self.items: list[dict] = []

    def write(self, items: list[str]) -> str:
        self.items = [{"index": i + 1, "task": t, "status": "todo"} for i, t in enumerate(items)]
        return self.render()

    def resolve_index(self, index: int) -> int | None:
        if not isinstance(index, int):
            return None
        # normalize: รองรับ index ทั้ง 1-based (ตามที่ render แสดง) และ 0-based (ที่ LLM บางครั้งส่งมา)
        # ถ้า index ตรงกับเลขข้อ 1-based ที่มีอยู่ → ใช้เลย; ไม่งั้นจึงลองตีความเป็น 0-based (index+1)
        valid = {it["index"] for it in self.items}
        if index in valid:
            return index
        if (index + 1) in valid:
            return index + 1
        return None

    def update(self, index: int, status: str) -> str:
        target = self.resolve_index(index)
        if target is None:
            return self.render()  # index ไม่ถูกต้อง — ไม่แก้ไขอะไร
        for it in self.items:
            if it["index"] == target:
                it["status"] = status
                break
        return self.render()

    def render(self) -> str:
        mark = {"todo": "[ ]", "doing": "[~]", "done": "[x]"}
        return "\n".join(f"{mark.get(i['status'],'[ ]')} {i['index']}. {i['task']}" for i in self.items)


def build_tools(registry: ToolRegistry) -> list[dict]:
    todo_tools = [
        {"type": "function", "function": {
            "name": "todo_write", "description": "เขียน todo list ก่อนเริ่มงานหลายขั้น",
            "parameters": {"type": "object", "properties": {
                "items": {"type": "array", "items": {"type": "string"},
                          "description": "รายการขั้นตอนงาน"}}, "required": ["items"]}}},
        {"type": "function", "function": {
            "name": "todo_update", "description": "อัปเดตสถานะของ todo ทีละข้อ",
            "parameters": {"type": "object", "properties": {
                "index": {"type": "integer"},
                "status": {"type": "string", "enum": ["todo", "doing", "done"]}},
                "required": ["index", "status"]}}},
    ]
    return todo_tools + registry.openai_tools


def _print_final(content: str, todo: TodoState, context: ContextState) -> str:
    print("-" * 60)
    print(f"[answer]\n{content}")
    print("-" * 60)
    print(f"[todo สุดท้าย]\n{todo.render()}")
    print(f"[context budget] {context.budgets}")
    return content


def dispatch_with_retry(
    registry: ToolRegistry,
    name: str,
    arguments: dict,
    max_transport_retries: int = 2,
) -> str:
    """Retry transient transport/status failures; never retry business payloads."""
    for attempt in range(max_transport_retries + 1):
        try:
            return registry.dispatch(name, arguments)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            transient = status == 429 or 500 <= status <= 599
            if not transient or attempt >= max_transport_retries:
                raise
            delay = 0.5 * (2 ** attempt)
            print(
                f"[MCP RETRY] tool={name} status={status} "
                f"attempt={attempt + 1} delay={delay:.1f}s"
            )
            time.sleep(delay)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            if attempt >= max_transport_retries:
                raise
            delay = 0.5 * (2 ** attempt)
            print(
                f"[MCP RETRY] tool={name} error={type(error).__name__} "
                f"attempt={attempt + 1} delay={delay:.1f}s"
            )
            time.sleep(delay)
    raise RuntimeError("unreachable MCP retry state")


def resolve_rewrite(
    question: str,
    proposed: str,
    observation,
    evidence: EvidenceState,
    ledger: ClaimLedger,
    dynamic_observer: bool,
    budget: Phase2Budget,
    timeout: float,
) -> str:
    """Phase 2B is bounded; Phase 2A retains its historical LLM recheck."""
    if dynamic_observer:
        candidate = verify_then_emit(
            question,
            observation,
            evidence,
            proposed_answer=proposed,
        )
        print(
            "[FINAL CLAIM GATE] verify-then-emit; MCP disabled; "
            f"observer_supported={len(observation.supported_claims)}"
        )
        return candidate
    candidate = observation.revised_answer or proposed

    recheck = review_final_answer(
        question,
        candidate,
        evidence,
        ledger.render(),
        timeout=timeout,
    )
    print(
        f"[FINAL RECHECK] verdict={recheck.verdict.value} "
        f"reason={recheck.reason}"
    )
    if recheck.verdict is SemanticVerdict.APPROVE:
        return candidate
    if recheck.verdict is SemanticVerdict.REFUSE_DECISION:
        return recheck.revised_answer or candidate
    return (
        "ยังไม่สามารถให้คำตอบที่ผ่านการตรวจหลักฐานได้: "
        + recheck.reason
    )


def _run_impl(
    question: str,
    registry: ToolRegistry,
    max_steps: int = 30,
    semantic_observer: bool = True,
    max_semantic_reviews: int = 2,
    max_mcp_calls: int = 12,
    dynamic_observer: bool = True,
    max_dynamic_observations: int = 6,
    max_run_seconds: float = 240,
):
    todo = TodoState()
    context = ContextState(original_goal=question, phase=AgentPhase.ACT)
    evidence = EvidenceState()
    ledger = ClaimLedger()
    budget = Phase2Budget(
        max_seconds=max_run_seconds,
        max_agent_calls=max_steps + 1,
        max_observer_calls=max_dynamic_observations + 1,
        max_final_reviews=max_semantic_reviews,
        max_mcp_calls=max_mcp_calls,
    )
    if dynamic_observer:
        print("[ROUTING] deterministic-first; claim planner disabled")
    tools = build_tools(registry)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    force_no_tools = False
    reviewed_risk_signatures: set[tuple[str, ...]] = set()
    for step in range(1, max_steps + 1):
        try:
            budget.consume_agent()
        except RuntimeBudgetExhausted as error:
            print(f"[RUNTIME STOP] {error}; {budget.render()}")
            break
        try:
            resp = llm.chat(
                messages=messages,
                tools=None if force_no_tools else tools,
                timeout=budget.call_timeout(60),
                client_max_retries=0,
            )
        except Exception as error:
            context.observe_error(error)
            print(
                f"[AGENT LLM ERROR] {type(error).__name__}: {error}; "
                f"{budget.render()}"
            )
            break
        msg = resp.choices[0].message
        if msg.tool_calls:
            dynamic_feedback: list[str] = []
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                name = call.function.name
                try:
                    if name == "todo_write":
                        result = todo.write(args.get("items", []))
                        kind = ActionKind.PLAN
                        print(f"[step {step}] TODO_WRITE\n{result}")
                    elif name == "todo_update":
                        result = todo.update(args.get("index"), args.get("status"))
                        kind = ActionKind.STATE_UPDATE
                        target = todo.resolve_index(args.get("index"))
                        item = next(
                            (value for value in todo.items
                             if value["index"] == target),
                            None,
                        )
                        if item and args.get("status") == "doing":
                            context.start_step(item["task"])
                        elif item and args.get("status") == "done":
                            context.complete_step(item["task"])
                        print(f"[step {step}] TODO_UPDATE -> {args}\n{result}")
                    else:
                        try:
                            budget.consume_mcp()
                        except RuntimeBudgetExhausted:
                            result = (
                                "[runtime] MCP tool-call budget exhausted; "
                                "use accepted evidence and answer now"
                            )
                            kind = ActionKind.STATE_UPDATE
                            print(
                                f"[step {step}] TOOL BLOCKED {name} "
                                f"(budget={max_mcp_calls})"
                            )
                        else:
                            try:
                                result = dispatch_with_retry(
                                    registry,
                                    name,
                                    args,
                                )
                            except Exception as tool_error:
                                result = json.dumps({
                                    "status": "error",
                                    "error_type": type(tool_error).__name__,
                                    "message": str(tool_error),
                                }, ensure_ascii=False)
                                context.observe_error(tool_error)
                                print(
                                    f"[MCP ERROR] tool={name} "
                                    f"type={type(tool_error).__name__}"
                                )
                            kind = ActionKind.TOOL
                            record = EvidenceRecord.from_tool(
                                call.id, name, args, result
                            )
                            context.add_evidence_ref(call.id)
                            if not dynamic_observer:
                                evidence.accept(record)
                            if dynamic_observer:
                                deterministic = observe_deterministically(
                                    question,
                                    record,
                                )
                                contract = validate_evidence_contract(
                                    question,
                                    record,
                                )
                                contract_accepts = (
                                    contract.decision
                                    is ContractDecision.ACCEPT
                                )
                                if (
                                    deterministic.decision
                                    is DeterministicDecision.ACCEPT
                                    and contract_accepts
                                ):
                                    evidence.accept(record)
                                evidence.add_observation(deterministic)
                                print(
                                    "[PYTHON OBSERVATION] "
                                    f"evidence={call.id} "
                                    f"decision={deterministic.decision.value} "
                                    f"type={deterministic.result_kind} "
                                    f"risk={deterministic.semantic_risk} "
                                    f"reasons={list(deterministic.risk_reasons)}"
                                )
                                if not contract_accepts:
                                    print(
                                        "[EVIDENCE CONTRACT] "
                                        f"evidence={call.id} "
                                        f"decision={contract.decision.value} "
                                        f"reason={contract.reason}"
                                    )
                                    dynamic_feedback.append(
                                        f"{contract.decision.value}: "
                                        f"{contract.reason}"
                                    )
                                if deterministic.decision in {
                                    DeterministicDecision.RETRY,
                                    DeterministicDecision.QUERY_MORE,
                                }:
                                    dynamic_feedback.append(
                                        f"{deterministic.decision.value}: "
                                        f"{deterministic.reason}"
                                    )
                                risk_signature = (
                                    deterministic.risk_reasons
                                )
                                needs_llm_observer = (
                                    deterministic.semantic_risk
                                    and risk_signature
                                    not in reviewed_risk_signatures
                                )
                                if not needs_llm_observer:
                                    print(
                                        "[LLM OBSERVER SKIPPED] "
                                        "low risk or risk already reviewed"
                                    )
                                    print(f"[step {step}] TOOL {name}")
                                    report = context.observe_action(
                                        name,
                                        args,
                                        result,
                                        kind=kind,
                                    )
                                    if report.alert:
                                        print(
                                            "[CONTEXT ALERT] "
                                            + "; ".join(report.reasons)
                                        )
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": call.id,
                                        "content": result,
                                    })
                                    continue
                            if dynamic_observer:
                                reviewed_risk_signatures.add(
                                    risk_signature
                                )
                                try:
                                    budget.consume_observer()
                                    observation = observe_tool_result(
                                        question,
                                        context.active_step,
                                        ledger,
                                        record,
                                        timeout=budget.call_timeout(45),
                                    )
                                    evidence.add_observation(observation)
                                    accepted_proofs = ()
                                    if (
                                        observation.action_succeeded
                                        and observation.supports_active_step
                                        and observation.evidence_complete
                                    ):
                                        accepted_proofs = (
                                            ledger.mark_proved_if_covered(
                                                list(
                                                    observation.proved_claim_ids
                                                ),
                                                call.id,
                                                observation.grain,
                                                observation.fields,
                                            )
                                        )
                                    ledger.mark_contradicted(
                                        dict(observation.contradictions),
                                        call.id,
                                    )
                                    ledger.revise_requirements({
                                        claim_id: (grain, fields)
                                        for claim_id, grain, fields
                                        in observation.claim_updates
                                    })
                                    print(
                                        "[DYNAMIC OBSERVATION] "
                                        f"evidence={call.id} "
                                        f"supports={observation.supports_active_step} "
                                        f"complete={observation.evidence_complete} "
                                        f"proved={list(accepted_proofs)} "
                                        f"next={observation.next_action.value} "
                                        f"reason={observation.reason}"
                                    )
                                    if (
                                        observation.next_action
                                        is NextAction.ACCEPT
                                        and observation.proved_claim_ids
                                        and not accepted_proofs
                                    ):
                                        dynamic_feedback.append(
                                            "query_more: runtime rejected "
                                            "claim proof because required "
                                            "grain/fields were not covered"
                                        )
                                    if observation.next_action in {
                                        NextAction.QUERY_MORE,
                                        NextAction.REPLAN,
                                        NextAction.STOP,
                                    }:
                                        dynamic_feedback.append(
                                            f"{observation.next_action.value}: "
                                            f"{observation.reason}; "
                                            "missing="
                                            + ", ".join(
                                                item.render()
                                                for item in
                                                observation.missing_evidence
                                            )
                                        )
                                    if (
                                        observation.next_action
                                        is NextAction.STOP
                                    ):
                                        force_no_tools = True
                                except RuntimeBudgetExhausted as observer_error:
                                    print(
                                        "[DYNAMIC OBSERVER SKIPPED] "
                                        f"{observer_error}; {budget.render()}"
                                    )
                                except Exception as observer_error:
                                    print(
                                        "[DYNAMIC OBSERVER ERROR] "
                                        f"{type(observer_error).__name__}: "
                                        f"{observer_error}"
                                    )
                            print(f"[step {step}] TOOL {name}")
                except Exception as error:
                    report = context.observe_error(error)
                    if report.alert:
                        print(f"[CONTEXT ALERT] {'; '.join(report.reasons)}")
                    raise

                report = context.observe_action(name, args, result, kind=kind)
                if report.alert:
                    print(f"[CONTEXT ALERT] {'; '.join(report.reasons)}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if dynamic_feedback:
                messages.append({
                    "role": "user",
                    "content": (
                        "Dynamic Observer feedback หลัง tool call:\n- "
                        + "\n- ".join(dynamic_feedback)
                        + "\nอัปเดตวิธีทำตาม feedback โดยอย่าทำ query เดิมซ้ำ"
                    ),
                })
            continue
        context.set_phase(AgentPhase.ANSWER)
        proposed = msg.content or ""
        if semantic_observer:
            final_risks = (
                final_semantic_risk(question, proposed, evidence)
                if dynamic_observer
                else ("phase2a-always-review",)
            )
            print(f"[FINAL ROUTING] risks={list(final_risks)}")
            if not final_risks:
                return _print_final(proposed, todo, context)
            try:
                budget.consume_final_review()
            except RuntimeBudgetExhausted as error:
                proposed = (
                    "ไม่สามารถตรวจรับรองคำตอบได้ภายในงบการทำงาน: "
                    f"{error}"
                )
                return _print_final(proposed, todo, context)
            try:
                observation = review_final_answer(
                    question,
                    proposed,
                    evidence,
                    ledger.render(),
                    timeout=budget.call_timeout(60),
                )
            except Exception as error:
                proposed = (
                    "ไม่สามารถตรวจรับรองคำตอบภายใน runtime ได้: "
                    f"{type(error).__name__}"
                )
                print(
                    f"[FINAL OBSERVER ERROR] {type(error).__name__}: {error}"
                )
                return _print_final(proposed, todo, context)
            if dynamic_observer:
                observation = enforce_claim_alignment(
                    observation,
                    ledger,
                )
            print(
                f"[FINAL OBSERVATION] verdict={observation.verdict.value} "
                f"reason={observation.reason}"
            )
            if (
                dynamic_observer
                and observation.verdict is SemanticVerdict.APPROVE
            ):
                proposed = verify_then_emit(
                    question,
                    observation,
                    evidence,
                    proposed_answer=proposed,
                )
                print("[FINAL CLAIM GATE] approved allowlist composed")
            elif observation.verdict is SemanticVerdict.QUERY_MORE:
                if budget.final_reviews < max_semantic_reviews:
                    messages.append({"role": "assistant", "content": proposed})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Final observer พบว่าหลักฐานยังไม่ครบ: "
                            f"{observation.reason}\n"
                            "เรียก MCP เฉพาะข้อมูลที่ขาด แล้วตอบใหม่ "
                            "ห้ามทำซ้ำ query ที่มี evidence ครบแล้ว"
                        ),
                    })
                    context.set_phase(AgentPhase.ACT)
                    continue
                proposed = (
                    "ยังไม่สามารถตอบข้อสรุปที่ร้องขอได้จากหลักฐานที่มี: "
                    + observation.reason
                )
            elif observation.verdict in {
                SemanticVerdict.REWRITE,
                SemanticVerdict.REFUSE_DECISION,
            }:
                proposed = resolve_rewrite(
                    question,
                    proposed,
                    observation,
                    evidence,
                    ledger,
                    dynamic_observer,
                    budget,
                    budget.call_timeout(60),
                )
        return _print_final(proposed, todo, context)

    # ชนเพดาน max_steps — บังคับให้โมเดลสรุปปิดท้าย จะได้ไม่จบแบบเงียบๆ โดยไม่มีบทสรุป
    messages.append({"role": "user",
                     "content": "ถึงขีดจำกัดขั้นตอนแล้ว ห้ามเรียก tool เพิ่ม — สรุปข้อค้นพบเชิงธุรกิจจากข้อมูลที่ได้มาเป็นข้อความสุดท้าย"})
    try:
        budget.consume_agent()
        final = llm.chat(
            messages=messages,
            timeout=budget.call_timeout(60),
            client_max_retries=0,
        )
    except Exception as error:
        content = (
            "หยุดตามขีดจำกัด runtime โดยไม่สร้างข้อสรุปเกินหลักฐาน: "
            f"{error}; unresolved claims="
            + ", ".join(claim.claim_id for claim in ledger.unresolved)
        )
        context.set_phase(AgentPhase.ANSWER)
        return _print_final(content, todo, context)
    context.set_phase(AgentPhase.ANSWER)
    content = final.choices[0].message.content or ""
    if semantic_observer:
        final_risks = (
            final_semantic_risk(question, content, evidence)
            if dynamic_observer
            else ("phase2a-always-review",)
        )
        print(f"[FINAL ROUTING] risks={list(final_risks)}")
        if not final_risks:
            return _print_final(content, todo, context)
        try:
            budget.consume_final_review()
            observation = review_final_answer(
                question,
                content,
                evidence,
                ledger.render(),
                timeout=budget.call_timeout(60),
            )
            if dynamic_observer:
                observation = enforce_claim_alignment(
                    observation,
                    ledger,
                )
        except Exception as error:
            content = (
                "หยุดตามขีดจำกัด runtime โดยไม่รับรองคำตอบ: "
                f"{error}"
            )
            return _print_final(content, todo, context)
        print(
            f"[FINAL OBSERVATION] verdict={observation.verdict.value} "
            f"reason={observation.reason}"
        )
        if (
            dynamic_observer
            and observation.verdict is SemanticVerdict.APPROVE
        ):
            content = verify_then_emit(
                question,
                observation,
                evidence,
                proposed_answer=content,
            )
            print("[FINAL CLAIM GATE] approved allowlist composed")
        elif observation.verdict in {
            SemanticVerdict.REWRITE,
            SemanticVerdict.REFUSE_DECISION,
        }:
            content = resolve_rewrite(
                question,
                content,
                observation,
                evidence,
                ledger,
                dynamic_observer,
                budget,
                budget.call_timeout(60),
            )
        elif observation.verdict is SemanticVerdict.QUERY_MORE:
            content = (
                "ถึงขีดจำกัดขั้นตอนและหลักฐานยังไม่พอสำหรับตอบ: "
                + observation.reason
            )
    return _print_final(content, todo, context)


def run(
    question: str,
    registry: ToolRegistry,
    max_steps: int = 30,
    semantic_observer: bool = True,
    max_semantic_reviews: int = 2,
    max_mcp_calls: int = 12,
    dynamic_observer: bool = True,
    max_dynamic_observations: int = 6,
    max_run_seconds: float = 240,
):
    """Run under a hard wall-clock deadline, including blocking I/O calls."""
    try:
        with hard_deadline(max_run_seconds):
            return _run_impl(
                question=question,
                registry=registry,
                max_steps=max_steps,
                semantic_observer=semantic_observer,
                max_semantic_reviews=max_semantic_reviews,
                max_mcp_calls=max_mcp_calls,
                dynamic_observer=dynamic_observer,
                max_dynamic_observations=max_dynamic_observations,
                max_run_seconds=max_run_seconds,
            )
    except RuntimeBudgetExhausted as error:
        print(f"[HARD DEADLINE STOP] {error}")
        content = (
            "หยุดตามขีดจำกัดเวลารวมโดยไม่สร้างข้อสรุปเกินหลักฐาน: "
            + str(error)
        )
        print("-" * 60)
        print(f"[answer]\n{content}")
        return content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--semantic-observer",
        choices=["on", "off"],
        default="on",
        help="เปิด Phase 2 final semantic observer (default: on)",
    )
    parser.add_argument(
        "--dynamic-observer",
        choices=["on", "off"],
        default="on",
        help="เปิด Phase 2B claim ledger และ post-tool observation (default: on)",
    )
    parser.add_argument(
        "--max-run-seconds",
        type=float,
        default=240,
        help="whole-run deadline ของ Phase 2B (default: 240)",
    )
    parser.add_argument("question", nargs="?")
    args = parser.parse_args()
    registry = ToolRegistry()
    n = registry.add_server(config.MCP_SERVER_URL)
    print(f"[MCP] ค้นพบ {n} tools\n")
    q = args.question or (
        "ช่วยทำรายงาน HR: 1) นับพนักงานที่ปฏิบัติงานแยกตามแผนก "
        "2) หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก "
        "3) สรุปข้อค้นพบเชิงธุรกิจ"
    )
    print(f"[user] {q}")
    try:
        run(
            q,
            registry,
            semantic_observer=args.semantic_observer == "on",
            dynamic_observer=args.dynamic_observer == "on",
            max_run_seconds=args.max_run_seconds,
        )
    finally:
        registry.close()


if __name__ == "__main__":
    main()
