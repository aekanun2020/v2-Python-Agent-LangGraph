"""Live HR proof for successful but semantically wrong tool results."""

from __future__ import annotations

import html
import json
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

from labs.core import config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.observation_policy import observe_result
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState

STEP = "นับพนักงานที่ปฏิบัติงานแยกแผนก"
WRONG_SQL = "SELECT COUNT(*) AS headcount FROM employees"
CORRECT_SQL = (
    "SELECT department, COUNT(*) AS headcount FROM employees "
    "WHERE status = N'ปฏิบัติงาน' GROUP BY department"
)


def new_plan() -> PlannerState:
    plan = PlannerState("ทดสอบ semantic observation", [PlanStep(1, STEP)])
    plan.start(1)
    return plan


def run_experiment() -> dict:
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    started = time.perf_counter()
    try:
        wrong_result = registry.dispatch("execute_query_tool", {"query": WRONG_SQL})
        structural = observe_result(
            step_description=STEP, tool="execute_query_tool", result=wrong_result,
            tool_arguments={"query": WRONG_SQL}, semantic_checks=False,
        )
        structural_plan = new_plan()
        if structural.decision == "accept":
            structural_plan.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                                    result=wrong_result, observation=structural.as_dict())
            structural_plan.complete(1)
            structural_plan.approve_answer()

        semantic_plan = new_plan()
        rejected = observe_result(
            step_description=STEP, tool="execute_query_tool", result=wrong_result,
            tool_arguments={"query": WRONG_SQL}, semantic_checks=True,
        )
        if rejected.decision == "accept":
            semantic_plan.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                                  result=wrong_result, observation=rejected.as_dict())

        correct_result = registry.dispatch("execute_query_tool", {"query": CORRECT_SQL})
        accepted = observe_result(
            step_description=STEP, tool="execute_query_tool", result=correct_result,
            tool_arguments={"query": CORRECT_SQL}, semantic_checks=True,
        )
        if accepted.decision == "accept":
            semantic_plan.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                                  result=correct_result, observation=accepted.as_dict())
            semantic_plan.complete(1)
            semantic_plan.approve_answer()
    finally:
        registry.close()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "experiment": "successful_but_semantically_wrong_hr_result",
        "step": STEP,
        "model": "not used — semantic observation layer isolated",
        "mcp_endpoint": config.MCP_SERVER_URL,
        "elapsed_ms": elapsed_ms,
        "live_mcp_calls": [
            {"query": WRONG_SQL, "execution_succeeded": structural.result_type != "error",
             "result_chars": len(wrong_result)},
            {"query": CORRECT_SQL, "execution_succeeded": accepted.result_type != "error",
             "result_chars": len(correct_result)},
        ],
        "structural_observation_only": {
            "decision": structural.decision,
            "approved": structural_plan.answer_approved,
            "wrong_evidence_accepted": len(structural_plan.step(1).evidence),
            "observation": structural.as_dict(),
        },
        "semantic_observation": {
            "wrong_query_decision": rejected.decision,
            "wrong_query_failed_checks": rejected.failed,
            "wrong_evidence_accepted": 0 if rejected.decision != "accept" else 1,
            "correct_query_decision": accepted.decision,
            "correct_query_passed_checks": accepted.passed,
            "correct_query_observation": accepted.as_dict(),
            "approved": semantic_plan.answer_approved,
            "evidence_count": len(semantic_plan.step(1).evidence),
        },
        "supported": (
            structural.decision == "accept" and structural_plan.answer_approved
            and rejected.decision == "retry"
            and "semantic:active_employee_population" in rejected.failed
            and "semantic:department_grain" in rejected.failed
            and accepted.decision == "accept" and semantic_plan.answer_approved
        ),
        "scope_limit": "Proves two explicit step semantics only: active population and department grain.",
    }


def render(s: dict) -> str:
    old, new = s["structural_observation_only"], s["semantic_observation"]
    verdict = "SUPPORTED" if s["supported"] else "NOT SUPPORTED"
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Semantic Observation HR Proof</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:15px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1100px;margin:24px auto;padding:0 22px}}h1{{color:#8be9fd;font-size:27px;margin:0}}.sub{{color:#a8b2d1;margin:6px 0 18px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.card,.proof,.queries{{background:#111a31;border:1px solid #2c3a60;border-radius:13px;padding:17px}}.old{{border-top:5px solid #ffb86c}}.new{{border-top:5px solid #50fa7b}}h2{{font-size:19px;margin:0 0 12px}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.metric{{background:#182440;border-radius:8px;padding:11px;text-align:center;color:#aeb8d4}}.metric b{{display:block;font-size:22px}}.old b{{color:#ffb86c}}.new b{{color:#50fa7b}}.proof{{margin-top:14px;border-left:5px solid #bd93f9}}.proof strong{{display:block;color:#bd93f9;font-size:22px}}.queries{{margin-top:14px}}code{{color:#f1fa8c}}.bad{{color:#ffb86c}}.good{{color:#50fa7b}}.note{{color:#a8b2d1}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}</style>
<main><h1>SUCCESSFUL BUT SEMANTICALLY WRONG — HR PROOF</h1><div class='sub'>Step: <code>{html.escape(s['step'])}</code> · both SQL calls succeeded on live MCP</div>
<div class='grid'><section class='card old'><h2>Structural Observation only</h2><div class='metrics'><div class='metric'><b>{old['decision'].upper()}</b>wrong query</div><div class='metric'><b>{old['wrong_evidence_accepted']}</b>wrong evidence</div><div class='metric'><b>0</b>semantic checks</div><div class='metric'><b>{'YES' if old['approved'] else 'NO'}</b>answer gate</div></div><p>Payload has valid rows, so execution/presence/alignment checks all pass—even though it answers total employees, not active employees by department.</p></section>
<section class='card new'><h2>Semantic Observation Policy</h2><div class='metrics'><div class='metric'><b>{new['wrong_query_decision'].upper()}</b>wrong query</div><div class='metric'><b>{new['wrong_evidence_accepted']}</b>wrong evidence</div><div class='metric'><b>2 FAILED</b>semantic checks</div><div class='metric'><b>{new['correct_query_decision'].upper()}</b>correct retry</div></div><p>Dynamic requirements detect missing <code>active_employee_population</code> and <code>department_grain</code>; corrected SQL passes and becomes the sole evidence.</p></section></div>
<section class='proof'><strong>{verdict}</strong>A successful tool call is not automatically valid evidence. Meaning must match the active step's population and analytical grain before completion.</section>
<section class='queries'><h2>Controlled decision path</h2><p class='bad'>SUCCESS + WRONG: <code>{html.escape(WRONG_SQL)}</code> → structural ACCEPT → semantic RETRY</p><p class='good'>SUCCESS + CORRECT: <code>{html.escape(CORRECT_SQL)}</code> → semantic ACCEPT</p><p class='note'>2 live MCP calls · {s['elapsed_ms']} ms · machine-readable checks are stored in JSON.</p></section></main></html>"""


def main():
    load_dotenv()
    summary = run_experiment()
    prefix = Path("artifacts/lab6_hr_semantic_observation")
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    prefix.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(json.dumps({
        "supported": summary["supported"],
        "live_mcp_calls": len(summary["live_mcp_calls"]),
        "structural_wrong_decision": summary["structural_observation_only"]["decision"],
        "semantic_wrong_decision": summary["semantic_observation"]["wrong_query_decision"],
        "semantic_failed": summary["semantic_observation"]["wrong_query_failed_checks"],
        "correct_retry_decision": summary["semantic_observation"]["correct_query_decision"],
        "correct_retry_reason": summary["semantic_observation"]["correct_query_observation"]["reason"],
    }, ensure_ascii=False, indent=2))
    print(f"[ARTIFACT] {prefix.with_suffix('.html')}")
    print(f"[ARTIFACT] {prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
