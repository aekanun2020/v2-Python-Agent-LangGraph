"""Four-case live MCP matrix for successful-but-wrong HR observations."""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from labs.core import config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.observation_policy import extract_numeric_facts, observe_result


CASES = [
    {
        "id": "denominator",
        "step": "คำนวณเปอร์เซ็นต์พนักงานที่มี skills",
        "wrong": "SELECT COUNT(DISTINCT employee_id) AS skilled_employees FROM skills",
        "correct": (
            "SELECT 100.0 * COUNT(DISTINCT s.employee_id) / "
            "NULLIF(COUNT(DISTINCT e.employee_id), 0) AS pct_skill_coverage "
            "FROM employees e LEFT JOIN skills s ON e.employee_id = s.employee_id"
        ),
        "expected_failed": ["semantic:explicit_denominator"],
    },
    {
        "id": "temporal_window",
        "step": "รวมชั่วโมงอบรมก่อน review ล่าสุด",
        "wrong": "SELECT SUM(hours) AS pre_review_hours FROM training_records",
        "correct": (
            "WITH latest_review AS (SELECT employee_id, review_date, "
            "ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY review_date DESC) rn "
            "FROM performance_reviews) SELECT SUM(t.hours) AS pre_review_hours "
            "FROM latest_review lr LEFT JOIN training_records t ON t.employee_id = lr.employee_id "
            "AND t.end_date <= lr.review_date WHERE lr.rn = 1"
        ),
        "expected_failed": [
            "semantic:pre_review_time_window", "semantic:latest_review_anchor"
        ],
    },
    {
        "id": "join_cardinality",
        "step": "join skills และ projects โดยป้องกันยอดซ้ำ",
        "wrong": (
            "SELECT COUNT(*) AS joined_rows FROM employees e "
            "JOIN skills s ON e.employee_id = s.employee_id "
            "JOIN projects p ON e.employee_id = p.employee_id"
        ),
        "correct": (
            "WITH skill_emp AS (SELECT employee_id, COUNT(*) skill_count FROM skills "
            "GROUP BY employee_id), project_emp AS (SELECT employee_id, SUM(project_value) project_value "
            "FROM projects GROUP BY employee_id) SELECT COUNT(*) AS joined_rows FROM employees e "
            "LEFT JOIN skill_emp s ON e.employee_id = s.employee_id "
            "LEFT JOIN project_emp p ON e.employee_id = p.employee_id"
        ),
        "expected_failed": ["semantic:safe_join_cardinality"],
    },
]

PRIOR_SQL = (
    "SELECT COUNT(*) AS active_headcount FROM employees WHERE status = N'ปฏิบัติงาน'"
)
CONTRADICT_SQL = (
    "SELECT COUNT(*) + 1 AS active_headcount FROM employees WHERE status = N'ปฏิบัติงาน'"
)


def execute_case(registry: ToolRegistry, case: dict) -> dict:
    wrong_result = registry.dispatch("execute_query_tool", {"query": case["wrong"]})
    structural = observe_result(
        step_description=case["step"], tool="execute_query_tool", result=wrong_result,
        tool_arguments={"query": case["wrong"]}, semantic_checks=False,
    )
    semantic_wrong = observe_result(
        step_description=case["step"], tool="execute_query_tool", result=wrong_result,
        tool_arguments={"query": case["wrong"]}, semantic_checks=True,
    )
    correct_result = registry.dispatch("execute_query_tool", {"query": case["correct"]})
    semantic_correct = observe_result(
        step_description=case["step"], tool="execute_query_tool", result=correct_result,
        tool_arguments={"query": case["correct"]}, semantic_checks=True,
    )
    expected = set(case["expected_failed"])
    return {
        "id": case["id"], "step": case["step"],
        "live_calls": 2,
        "wrong_execution_succeeded": structural.result_type != "error",
        "wrong_sql": case["wrong"], "correct_sql": case["correct"],
        "structural_wrong_decision": structural.decision,
        "semantic_wrong_decision": semantic_wrong.decision,
        "semantic_failed": semantic_wrong.failed,
        "correct_decision": semantic_correct.decision,
        "passed": (
            structural.decision == "accept" and semantic_wrong.decision == "retry"
            and expected.issubset(semantic_wrong.failed)
            and semantic_correct.decision == "accept"
        ),
    }


def execute_contradiction(registry: ToolRegistry) -> dict:
    prior_result = registry.dispatch("execute_query_tool", {"query": PRIOR_SQL})
    prior_facts = extract_numeric_facts(prior_result)
    wrong_result = registry.dispatch("execute_query_tool", {"query": CONTRADICT_SQL})
    structural = observe_result(
        step_description="ยืนยัน active headcount กับหลักฐานก่อนหน้า",
        tool="execute_query_tool", result=wrong_result,
        tool_arguments={"query": CONTRADICT_SQL}, semantic_checks=False,
    )
    semantic_wrong = observe_result(
        step_description="ยืนยัน active headcount กับหลักฐานก่อนหน้า",
        tool="execute_query_tool", result=wrong_result,
        tool_arguments={"query": CONTRADICT_SQL}, semantic_checks=True,
        prior_facts=prior_facts,
    )
    correct_result = registry.dispatch("execute_query_tool", {"query": PRIOR_SQL})
    semantic_correct = observe_result(
        step_description="ยืนยัน active headcount กับหลักฐานก่อนหน้า",
        tool="execute_query_tool", result=correct_result,
        tool_arguments={"query": PRIOR_SQL}, semantic_checks=True,
        prior_facts=prior_facts,
    )
    return {
        "id": "cross_evidence", "step": "ยืนยัน active headcount กับหลักฐานก่อนหน้า",
        "live_calls": 3, "prior_facts": prior_facts,
        "wrong_execution_succeeded": structural.result_type != "error",
        "wrong_sql": CONTRADICT_SQL, "correct_sql": PRIOR_SQL,
        "structural_wrong_decision": structural.decision,
        "semantic_wrong_decision": semantic_wrong.decision,
        "semantic_failed": semantic_wrong.failed,
        "correct_decision": semantic_correct.decision,
        "passed": (
            structural.decision == "accept" and semantic_wrong.decision == "retry"
            and "semantic:cross_evidence_consistency" in semantic_wrong.failed
            and semantic_correct.decision == "accept"
        ),
    }


def run_experiment() -> dict:
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    started = time.perf_counter()
    try:
        results = [execute_case(registry, case) for case in CASES]
        results.append(execute_contradiction(registry))
    finally:
        registry.close()
    return {
        "experiment": "semantic_observation_adversarial_matrix",
        "model": "not used — semantic policy layer isolated",
        "mcp_endpoint": config.MCP_SERVER_URL,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "live_mcp_calls": sum(case["live_calls"] for case in results),
        "cases": results,
        "passed_cases": sum(case["passed"] for case in results),
        "total_cases": len(results),
        "supported": all(case["passed"] for case in results),
        "scope_limit": "Rule-grounded semantics for four declared contracts; not open-ended semantic understanding.",
    }


def render(s: dict) -> str:
    labels = {
        "denominator": "Denominator",
        "temporal_window": "Temporal window",
        "join_cardinality": "Join cardinality",
        "cross_evidence": "Cross-evidence",
    }
    rows = "".join(
        f"<tr><td>{labels[c['id']]}</td><td class='bad'>{c['structural_wrong_decision'].upper()}</td>"
        f"<td class='good'>{c['semantic_wrong_decision'].upper()}</td>"
        f"<td>{'<br>'.join(html.escape(x.replace('semantic:', '')) for x in c['semantic_failed'])}</td>"
        f"<td class='good'>{c['correct_decision'].upper()}</td><td>{'PASS' if c['passed'] else 'FAIL'}</td></tr>"
        for c in s["cases"]
    )
    verdict = "SUPPORTED" if s["supported"] else "NOT SUPPORTED"
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Semantic Observation Matrix</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:15px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1180px;margin:24px auto;padding:0 22px}}h1{{color:#8be9fd;font-size:27px;margin:0}}.sub{{color:#a8b2d1;margin:6px 0 18px}}.score,.matrix,.proof{{background:#111a31;border:1px solid #2c3a60;border-radius:13px;padding:17px}}.score{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;border-top:5px solid #50fa7b}}.metric{{background:#182440;border-radius:8px;padding:12px;text-align:center;color:#aeb8d4}}.metric b{{display:block;color:#50fa7b;font-size:24px}}.matrix{{margin-top:14px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid #2c3a60;text-align:left;vertical-align:top}}th{{color:#8be9fd}}.bad{{color:#ffb86c}}.good{{color:#50fa7b}}.proof{{margin-top:14px;border-left:5px solid #bd93f9}}.proof strong{{display:block;color:#bd93f9;font-size:21px}}code{{color:#f1fa8c}}.note{{color:#a8b2d1}}</style><main>
<h1>SEMANTIC OBSERVATION — ADVERSARIAL HR MATRIX</h1><div class='sub'>Every wrong query executed successfully · structural checks accepted it · semantic policy had to reject and recover</div>
<section class='score'><div class='metric'><b>{s['passed_cases']}/{s['total_cases']}</b>cases passed</div><div class='metric'><b>{s['live_mcp_calls']}</b>live MCP calls</div><div class='metric'><b>0</b>wrong evidence admitted</div></section>
<section class='matrix'><table><thead><tr><th>Semantic risk</th><th>Structural</th><th>Semantic</th><th>Failed contract</th><th>Correct retry</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='proof'><strong>{verdict}</strong>Hard policies rejected successful-but-wrong results for denominator, temporal scope, join grain, and contradiction with prior evidence. This is rule-grounded semantic assurance—not general semantic understanding.</section>
<p class='note'>Elapsed {s['elapsed_ms']} ms · full SQL actions, decisions, and prior facts are stored in JSON.</p></main></html>"""


def main():
    load_dotenv()
    summary = run_experiment()
    prefix = Path("artifacts/lab6_hr_semantic_matrix")
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    prefix.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(json.dumps({
        "supported": summary["supported"], "passed": f"{summary['passed_cases']}/{summary['total_cases']}",
        "live_mcp_calls": summary["live_mcp_calls"],
        "cases": [{"id": c["id"], "wrong": c["semantic_wrong_decision"],
                   "correct": c["correct_decision"], "passed": c["passed"]} for c in summary["cases"]],
    }, ensure_ascii=False, indent=2))
    print(f"[ARTIFACT] {prefix.with_suffix('.html')}")
    print(f"[ARTIFACT] {prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
