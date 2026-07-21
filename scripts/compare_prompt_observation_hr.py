"""Compare hard rules, Qwen prompt reviewer, and hybrid Observation gate."""

from __future__ import annotations

import html
import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from labs.core import config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.observation_policy import extract_numeric_facts, observe_result
from labs.lab6_todo.semantic_reviewer import hybrid_decision, review_observation
from scripts.compare_semantic_matrix_hr import CASES, CONTRADICT_SQL, PRIOR_SQL

TOOL = "execute_query_tool"


def _observe(step, sql, result, prior_facts=None):
    return observe_result(
        step_description=step, tool=TOOL, result=result,
        tool_arguments={"query": sql}, semantic_checks=True, prior_facts=prior_facts,
    )


def _review(step, sql, result, prior_facts=None):
    return review_observation(
        goal=step,
        active_step=step,
        analytical_contract=(
            "Derive requirements only from the goal/step. A completed step must be "
            "supported by the SQL semantics and returned evidence."
        ),
        tool=TOOL, tool_arguments={"query": sql}, result=result,
        prior_facts=prior_facts,
    )


def _item(case_id, variant, expected, step, sql, result, prior_facts=None):
    hard_started = time.perf_counter()
    hard = _observe(step, sql, result, prior_facts)
    hard_ms = int((time.perf_counter() - hard_started) * 1000)
    review = _review(step, sql, result, prior_facts)
    hybrid = hybrid_decision(hard, review)
    return {
        "case": case_id, "variant": variant, "expected": expected,
        "step": step, "sql": sql, "result_chars": len(result),
        "hard": {"decision": hard.decision, "elapsed_ms": hard_ms,
                 "failed": hard.failed, "correct": hard.decision == expected},
        "prompt": {**review.as_dict(), "correct": review.decision == expected},
        "hybrid": {"decision": hybrid, "correct": hybrid == expected,
                   "reviewer_required_in_routed_runtime": hard.decision == "accept"},
    }


def run_experiment() -> dict:
    registry = ToolRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    items = []
    started = time.perf_counter()
    try:
        for case in CASES:
            wrong_result = registry.dispatch(TOOL, {"query": case["wrong"]})
            correct_result = registry.dispatch(TOOL, {"query": case["correct"]})
            items.append(_item(case["id"], "wrong", "retry", case["step"],
                               case["wrong"], wrong_result))
            items.append(_item(case["id"], "correct", "accept", case["step"],
                               case["correct"], correct_result))

        step = "ยืนยัน active headcount กับหลักฐานก่อนหน้า"
        prior_result = registry.dispatch(TOOL, {"query": PRIOR_SQL})
        prior_facts = extract_numeric_facts(prior_result)
        wrong_result = registry.dispatch(TOOL, {"query": CONTRADICT_SQL})
        correct_result = registry.dispatch(TOOL, {"query": PRIOR_SQL})
        items.append(_item("cross_evidence", "wrong", "retry", step,
                           CONTRADICT_SQL, wrong_result, prior_facts))
        items.append(_item("cross_evidence", "correct", "accept", step,
                           PRIOR_SQL, correct_result, prior_facts))
    finally:
        registry.close()

    def metrics(layer: str) -> dict:
        decisions = [item[layer]["decision"] for item in items]
        wrong = [item for item in items if item["variant"] == "wrong"]
        correct = [item for item in items if item["variant"] == "correct"]
        return {
            "exact_accuracy": sum(item[layer]["correct"] for item in items),
            "admission_accuracy": len(items) - (
                sum(item[layer]["decision"] == "accept" for item in wrong)
                + sum(item[layer]["decision"] != "accept" for item in correct)
            ),
            "total": len(items),
            "false_accepts": sum(item[layer]["decision"] == "accept" for item in wrong),
            "false_rejects": sum(item[layer]["decision"] != "accept" for item in correct),
            "decisions": decisions,
        }

    hard_metrics, prompt_metrics, hybrid_metrics = (
        metrics("hard"), metrics("prompt"), metrics("hybrid")
    )
    prompt_metrics.update({
        "reviewer_calls": len(items),
        "elapsed_ms": sum(item["prompt"]["elapsed_ms"] for item in items),
        "prompt_tokens": sum(item["prompt"]["prompt_tokens"] or 0 for item in items),
        "completion_tokens": sum(item["prompt"]["completion_tokens"] or 0 for item in items),
    })
    hard_metrics.update({
        "reviewer_calls": 0,
        "elapsed_ms": sum(item["hard"]["elapsed_ms"] for item in items),
    })
    hybrid_metrics.update({
        "reviewer_calls": sum(item["hybrid"]["reviewer_required_in_routed_runtime"] for item in items),
        "estimated_reviewer_elapsed_ms": sum(
            item["prompt"]["elapsed_ms"] for item in items
            if item["hybrid"]["reviewer_required_in_routed_runtime"]
        ),
    })
    return {
        "experiment": "hard_rules_vs_prompt_reviewer_vs_hybrid",
        "model": os.environ.get("OPENROUTER_MODEL", config.OPENROUTER_MODEL),
        "mcp_endpoint": config.MCP_SERVER_URL,
        "live_mcp_calls": 9,
        "observations": len(items),
        "wall_elapsed_ms": int((time.perf_counter() - started) * 1000),
        "metrics": {"hard_rules": hard_metrics, "prompt_reviewer": prompt_metrics,
                    "hybrid": hybrid_metrics},
        "items": items,
        "scope_limit": "One run on four declared HR semantic risks; prompt results are model/sample dependent.",
    }


def render(s: dict) -> str:
    m = s["metrics"]
    cards = "".join(
        f"<section class='card {css}'><h2>{title}</h2><div class='metrics'>"
        f"<div><b>{data['admission_accuracy']}/{data['total']}</b>admission accuracy</div>"
        f"<div><b>{data['false_accepts']}</b>false accepts</div>"
        f"<div><b>{data['false_rejects']}</b>false rejects</div>"
        f"<div><b>{data['reviewer_calls']}</b>reviewer calls</div></div></section>"
        for title, css, data in (
            ("Hard rules", "rules", m["hard_rules"]),
            ("Qwen prompt reviewer", "prompt", m["prompt_reviewer"]),
            ("Hybrid routed gate", "hybrid", m["hybrid"]),
        )
    )
    labels = {"denominator": "Denominator", "temporal_window": "Temporal",
              "join_cardinality": "Join grain", "cross_evidence": "Contradiction"}
    wrong_rows = [item for item in s["items"] if item["variant"] == "wrong"]
    rows = "".join(
        f"<tr><td>{labels[item['case']]}</td><td>{item['hard']['decision'].upper()}</td>"
        f"<td>{item['prompt']['decision'].upper()}</td><td>{item['hybrid']['decision'].upper()}</td>"
        f"<td>{item['prompt']['confidence']:.2f}</td></tr>" for item in wrong_rows
    )
    prompt = m["prompt_reviewer"]
    conclusion = (
        "Hybrid preserved the hard safety floor while adding a context-derived reviewer."
        if m["hybrid"]["false_accepts"] == 0 else
        "Hybrid admitted at least one wrong result; the safety hypothesis was not supported."
    )
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Prompt Semantic Reviewer Comparison</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:14px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1220px;margin:20px auto;padding:0 20px}}h1{{color:#8be9fd;font-size:25px;margin:0}}.sub{{color:#a8b2d1;margin:5px 0 14px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card,.table,.proof{{background:#111a31;border:1px solid #2c3a60;border-radius:12px;padding:14px}}.rules{{border-top:4px solid #ffb86c}}.prompt{{border-top:4px solid #8be9fd}}.hybrid{{border-top:4px solid #50fa7b}}h2{{font-size:17px;margin:0 0 9px}}.metrics{{display:grid;grid-template-columns:1fr 1fr;gap:7px}}.metrics div{{background:#182440;border-radius:7px;padding:8px;text-align:center;color:#aeb8d4}}.metrics b{{display:block;color:#f1fa8c;font-size:20px}}.table{{margin-top:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid #2c3a60;text-align:left}}th{{color:#8be9fd}}.proof{{margin-top:12px;border-left:5px solid #bd93f9}}.proof strong{{color:#bd93f9}}code{{color:#f1fa8c}}.note{{color:#a8b2d1}}</style><main>
<h1>HARD RULES vs QWEN PROMPT REVIEWER vs HYBRID</h1><div class='sub'>8 labeled observations · 4 successful-but-wrong + 4 corrected · model <code>{html.escape(s['model'])}</code> · same live MCP results</div>
<div class='grid'>{cards}</div><section class='table'><table><thead><tr><th>Wrong-result risk</th><th>Rules</th><th>Prompt</th><th>Hybrid</th><th>Qwen confidence</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='proof'><strong>{html.escape(conclusion)}</strong><br>Prompt exact decision calibration: {prompt['exact_accuracy']}/{prompt['total']}; admission accuracy: {prompt['admission_accuracy']}/{prompt['total']}. Reviewer cost: {prompt['elapsed_ms']/1000:.1f}s, {prompt['prompt_tokens']} input + {prompt['completion_tokens']} output tokens. Routed hybrid would call it {m['hybrid']['reviewer_calls']} times instead of {prompt['reviewer_calls']}.</section>
<p class='note'>9 live MCP calls · one model run per observation · exact JSON decisions and derived requirements are stored in the adjacent artifact.</p></main></html>"""


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    prefix = Path("artifacts/lab6_hr_prompt_reviewer_comparison")
    if args.render_only:
        summary = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
        for layer in ("hard_rules", "prompt_reviewer", "hybrid"):
            metric = summary["metrics"][layer]
            metric["admission_accuracy"] = metric["total"] - metric["false_accepts"] - metric["false_rejects"]
    else:
        summary = run_experiment()
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    prefix.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(json.dumps({"model": summary["model"], "metrics": summary["metrics"]},
                     ensure_ascii=False, indent=2))
    print(f"[ARTIFACT] {prefix.with_suffix('.html')}")
    print(f"[ARTIFACT] {prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
