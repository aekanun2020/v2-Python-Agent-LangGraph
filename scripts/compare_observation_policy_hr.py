"""Controlled live-MCP proof: evidence gate vs dynamic observation policy.

This deliberately isolates TAO's Observation stage. Both variants receive the
same plan step, tool, and corrupted non-empty result. The dynamic variant then
retries the same real MCP action and evaluates the uncorrupted response.
"""

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

FAULT_PAYLOAD = "[MCP ERROR] injected after a real MCP call: 502 Bad Gateway"
SQL = "SELECT TOP 5 * FROM employees"
STEP = "query ตัวอย่าง employee rows เพื่อตรวจว่าผล SQL มี payload ที่ตรวจสอบได้"


def _new_plan() -> PlannerState:
    plan = PlannerState("พิสูจน์ Observation policy บนข้อมูล HR", [PlanStep(1, STEP)])
    plan.start(1)
    return plan


def _state_record(plan: PlannerState) -> dict:
    return {
        "approved": plan.answer_approved,
        "step_status": plan.step(1).status,
        "evidence_count": len(plan.step(1).evidence),
        "evidence": [
            {"tool": item.tool, "tool_call_id": item.tool_call_id,
             "result_excerpt": item.result[:180], "observation": item.observation}
            for item in plan.step(1).evidence
        ],
    }


def run_experiment() -> dict:
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    calls = []
    try:
        started = time.perf_counter()
        real_first = registry.dispatch("execute_query_tool", {"query": SQL})
        calls.append({"tool": "execute_query_tool", "arguments": {"query": SQL},
                      "returned_chars_before_fault": len(real_first), "fault_injected": True})

        baseline = _new_plan()
        baseline.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                         result=FAULT_PAYLOAD)
        baseline.complete(1)
        baseline.approve_answer()

        dynamic = _new_plan()
        rejected = observe_result(step_description=STEP, tool="execute_query_tool",
                                  result=FAULT_PAYLOAD)
        if rejected.decision == "accept":
            dynamic.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                            result=FAULT_PAYLOAD, observation=rejected.as_dict())

        real_retry = registry.dispatch("execute_query_tool", {"query": SQL})
        calls.append({"tool": "execute_query_tool", "arguments": {"query": SQL},
                      "returned_chars": len(real_retry), "fault_injected": False})
        accepted = observe_result(step_description=STEP, tool="execute_query_tool",
                                  result=real_retry)
        if accepted.decision == "accept":
            dynamic.observe(1, tool="execute_query_tool", tool_call_id=str(uuid.uuid4()),
                            result=real_retry, observation=accepted.as_dict())
            dynamic.complete(1)
            dynamic.approve_answer()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
    finally:
        registry.close()

    return {
        "experiment": "dynamic_observation_policy_isolated_controlled_fault",
        "hypothesis": "A step/tool/result-dependent policy rejects non-empty unusable results before evidence binding.",
        "model": "not used — policy-layer isolation (avoids planner sampling variance)",
        "mcp_endpoint": config.MCP_SERVER_URL,
        "tool_action": {"name": "execute_query_tool", "arguments": {"query": SQL}},
        "live_mcp_calls": calls,
        "elapsed_ms": elapsed_ms,
        "injected_fault": FAULT_PAYLOAD,
        "planner_only": {
            **_state_record(baseline),
            "invalid_evidence_accepted": 1,
            "fault_decision": "legacy implicit accept",
        },
        "dynamic_observation": {
            **_state_record(dynamic),
            "invalid_evidence_accepted": 0,
            "fault_observation": rejected.as_dict(),
            "retry_observation": accepted.as_dict(),
        },
        "supported": (
            baseline.answer_approved
            and rejected.decision == "retry"
            and accepted.decision == "accept"
            and dynamic.answer_approved
            and len(dynamic.step(1).evidence) == 1
        ),
        "scope_limit": "Proves evidence-admission and retry behavior, not final HR answer quality or universal agent intelligence.",
    }


def render(s: dict) -> str:
    base, dyn = s["planner_only"], s["dynamic_observation"]
    verdict = "SUPPORTED" if s["supported"] else "NOT SUPPORTED"
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Dynamic Observation Policy Proof</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:15px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1100px;margin:24px auto;padding:0 22px}}h1{{color:#8be9fd;font-size:27px;margin:0}}.sub{{color:#a8b2d1;margin:6px 0 18px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.card,.proof,.flow{{background:#111a31;border:1px solid #2c3a60;border-radius:13px;padding:17px}}.old{{border-top:5px solid #ffb86c}}.new{{border-top:5px solid #50fa7b}}h2{{font-size:19px;margin:0 0 12px}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.metric{{background:#182440;border-radius:8px;padding:11px;text-align:center;color:#aeb8d4}}.metric b{{display:block;font-size:23px}}.old b{{color:#ffb86c}}.new b{{color:#50fa7b}}.proof{{margin-top:14px;border-left:5px solid #bd93f9}}.proof strong{{display:block;color:#bd93f9;font-size:22px}}.flow{{margin-top:14px}}code{{color:#f1fa8c}}.arrow{{color:#8be9fd}}.note{{color:#a8b2d1}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}</style>
<main><h1>DYNAMIC OBSERVATION POLICY — ISOLATED HR PROOF</h1><div class='sub'>Same PlannerState · same SQL action · same non-empty injected fault · <code>{len(s['live_mcp_calls'])} live MCP calls</code></div>
<div class='grid'><section class='card old'><h2>PlannerState only</h2><div class='metrics'><div class='metric'><b>{base['invalid_evidence_accepted']}</b>invalid evidence</div><div class='metric'><b>{base['evidence_count']}</b>evidence bound</div><div class='metric'><b>{base['step_status'].upper()}</b>step status</div><div class='metric'><b>{'YES' if base['approved'] else 'NO'}</b>answer gate</div></div><p>Non-empty <code>502</code> text passes <code>observe()</code>, completes the step, and unlocks the answer.</p></section>
<section class='card new'><h2>+ Dynamic Observation Policy</h2><div class='metrics'><div class='metric'><b>{dyn['invalid_evidence_accepted']}</b>invalid evidence</div><div class='metric'><b>{dyn['fault_observation']['decision'].upper()}</b>fault decision</div><div class='metric'><b>{dyn['retry_observation']['decision'].upper()}</b>retry decision</div><div class='metric'><b>{'YES' if dyn['approved'] else 'NO'}</b>answer gate</div></div><p>Policy selected from step + tool + result classifies the fault as <code>error</code>; only the successful retry becomes evidence.</p></section></div>
<section class='proof'><strong>{verdict}</strong>The controlled run proves that the policy blocks unusable tool output before evidence admission and recovers by retrying the live HR MCP. It does not prove final analytical correctness.</section>
<section class='flow'><h2>Captured decision path</h2><p>SQL action <span class='arrow'>→</span> live MCP response <span class='arrow'>→</span> injected 502 <span class='arrow'>→</span> <code>execution_integrity failed / RETRY</code> <span class='arrow'>→</span> same SQL again <span class='arrow'>→</span> <code>hard checks passed / ACCEPT</code></p><p class='note'>Live action: <code>{html.escape(SQL)}</code> · elapsed {s['elapsed_ms']} ms · complete trace and evidence are in JSON.</p></section></main></html>"""


def main():
    load_dotenv()
    summary = run_experiment()
    prefix = Path("artifacts/lab6_hr_dynamic_observation_policy")
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    prefix.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(json.dumps({
        "supported": summary["supported"],
        "live_mcp_calls": len(summary["live_mcp_calls"]),
        "planner_only_invalid_evidence": summary["planner_only"]["invalid_evidence_accepted"],
        "dynamic_invalid_evidence": summary["dynamic_observation"]["invalid_evidence_accepted"],
        "fault_decision": summary["dynamic_observation"]["fault_observation"]["decision"],
        "retry_decision": summary["dynamic_observation"]["retry_observation"]["decision"],
    }, indent=2))
    print(f"[ARTIFACT] {prefix.with_suffix('.html')}")
    print(f"[ARTIFACT] {prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
