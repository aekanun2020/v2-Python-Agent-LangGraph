"""Replay the captured Qwen comparison through rules/shadow/enforce routing modes."""

from __future__ import annotations

import html
import json
from pathlib import Path

from labs.lab6_todo.observation_policy import observe_result
from labs.lab6_todo.observation_router import assess_observation_risk, routed_decision
from labs.lab6_todo.semantic_reviewer import SemanticReview

SOURCE = Path("artifacts/lab6_hr_prompt_reviewer_comparison.json")
PREFIX = Path("artifacts/lab6_hr_shadow_router_comparison")


def replay() -> dict:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = []
    for item in source["items"]:
        prior = {"active_headcount": 25.0} if item["case"] == "cross_evidence" else None
        hard = observe_result(
            step_description=item["step"], tool="execute_query_tool",
            tool_arguments={"query": item["sql"]},
            result='{"active_headcount":25}' if prior else '[{"metric":1}]',
            semantic_checks=True, prior_facts=prior,
        )
        hard.decision = item["hard"]["decision"]
        review = SemanticReview(
            decision=item["prompt"]["decision"],
            confidence=item["prompt"]["confidence"],
            reason=item["prompt"]["reason"],
            elapsed_ms=item["prompt"]["elapsed_ms"],
            prompt_tokens=item["prompt"]["prompt_tokens"],
            completion_tokens=item["prompt"]["completion_tokens"],
        )
        risk = assess_observation_risk(
            hard=hard, step_description=item["step"], tool="execute_query_tool",
            tool_arguments={"query": item["sql"]},
        )
        shadow = routed_decision("shadow", hard, review if risk.reviewer_required else None)
        enforce = routed_decision("enforce", hard, review if risk.reviewer_required else None)
        rows.append({
            "case": item["case"], "variant": item["variant"], "expected": item["expected"],
            "hard_decision": hard.decision, "risk": risk.as_dict(),
            "review_called": risk.reviewer_required,
            "review_decision": review.decision if risk.reviewer_required else None,
            "shadow_decision": shadow, "enforce_decision": enforce,
            "shadow_regression": shadow != hard.decision,
            "review_disagreement": risk.reviewer_required and review.decision != hard.decision,
        })

    def metrics(mode_key: str) -> dict:
        wrong = [row for row in rows if row["variant"] == "wrong"]
        correct = [row for row in rows if row["variant"] == "correct"]
        return {
            "admission_accuracy": sum(row[mode_key] == row["expected"] for row in rows),
            "false_accepts": sum(row[mode_key] == "accept" for row in wrong),
            "false_rejects": sum(row[mode_key] != "accept" for row in correct),
        }

    high_rows = [row for row in rows if row["case"] != "denominator"]
    review_rows = [row for row in rows if row["review_called"]]
    return {
        "experiment": "shadow_risk_router_replay",
        "source_artifact": str(SOURCE),
        "model": source["model"],
        "source_live_mcp_calls": source["live_mcp_calls"],
        "source_reviewer_calls": source["observations"],
        "rows": rows,
        "metrics": {
            "rules": metrics("hard_decision"),
            "shadow": metrics("shadow_decision"),
            "enforce": metrics("enforce_decision"),
            "router": {
                "high_risk_recall": sum(row["risk"]["level"] == "high" for row in high_rows),
                "high_risk_total": len(high_rows),
                "reviewer_calls": len(review_rows),
                "call_reduction_pct": round(100 * (1 - len(review_rows) / len(rows)), 1),
                "shadow_behavior_regressions": sum(row["shadow_regression"] for row in rows),
                "reviewer_disagreements": sum(row["review_disagreement"] for row in rows),
                "replayed_reviewer_elapsed_ms": sum(
                    source_item["prompt"]["elapsed_ms"] for source_item in source["items"]
                    if next(row for row in rows if row["case"] == source_item["case"]
                            and row["variant"] == source_item["variant"])["review_called"]
                ),
            },
        },
        "supported": (
            all(not row["shadow_regression"] for row in rows)
            and all(row["risk"]["level"] == "high" for row in high_rows)
            and len(review_rows) < len(rows)
        ),
        "scope_limit": "Deterministic replay of one captured Qwen run; shadow mode does not prove future reviewer stability.",
    }


def render(s: dict) -> str:
    m, router = s["metrics"], s["metrics"]["router"]
    cards = "".join(
        f"<section class='card {css}'><h2>{name}</h2><div class='metric'><b>{data['admission_accuracy']}/8</b>admission accuracy</div>"
        f"<div class='pair'><span><b>{data['false_accepts']}</b>false accepts</span><span><b>{data['false_rejects']}</b>false rejects</span></div></section>"
        for name, css, data in (("Rules", "rules", m["rules"]),
                                ("Shadow", "shadow", m["shadow"]),
                                ("Enforce", "enforce", m["enforce"]))
    )
    risk_rows = [row for row in s["rows"] if row["variant"] == "correct"]
    labels = {"denominator": "Denominator", "temporal_window": "Temporal",
              "join_cardinality": "Join grain", "cross_evidence": "Contradiction"}
    rows = "".join(
        f"<tr><td>{labels[row['case']]}</td><td>{row['risk']['level'].upper()}</td>"
        f"<td>{'YES' if row['review_called'] else 'NO'}</td>"
        f"<td>{(row['review_decision'] or '—').upper()}</td>"
        f"<td>{row['shadow_decision'].upper()}</td><td>{row['enforce_decision'].upper()}</td></tr>"
        for row in risk_rows
    )
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Shadow Risk Router Comparison</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:14px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1200px;margin:20px auto;padding:0 20px}}h1{{color:#8be9fd;font-size:25px;margin:0}}.sub{{color:#a8b2d1;margin:5px 0 14px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card,.table,.proof{{background:#111a31;border:1px solid #2c3a60;border-radius:12px;padding:14px}}.rules{{border-top:4px solid #ffb86c}}.shadow{{border-top:4px solid #8be9fd}}.enforce{{border-top:4px solid #50fa7b}}h2{{font-size:17px;margin:0 0 8px}}.metric,.pair span{{background:#182440;border-radius:7px;padding:9px;text-align:center;color:#aeb8d4}}.metric b,.pair b{{display:block;color:#f1fa8c;font-size:20px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:7px}}.table{{margin-top:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:7px;border-bottom:1px solid #2c3a60;text-align:left}}th{{color:#8be9fd}}.proof{{margin-top:12px;border-left:5px solid #bd93f9}}.proof strong{{color:#bd93f9}}code{{color:#f1fa8c}}.note{{color:#a8b2d1}}</style><main>
<h1>RULES vs SHADOW ROUTER vs ENFORCE</h1><div class='sub'>Replay of the same 8 Qwen-reviewed observations · shadow records disagreement but cannot change evidence admission</div><div class='grid'>{cards}</div>
<section class='table'><table><thead><tr><th>Correct-result risk</th><th>Risk</th><th>Review?</th><th>Qwen</th><th>Shadow final</th><th>Enforce final</th></tr></thead><tbody>{rows}</tbody></table></section>
<section class='proof'><strong>NO SHADOW REGRESSION: {router['shadow_behavior_regressions']}</strong><br>High-risk recall {router['high_risk_recall']}/{router['high_risk_total']} · reviewer calls {router['reviewer_calls']}/8 ({router['call_reduction_pct']}% reduction) · disagreements recorded {router['reviewer_disagreements']} · shadow keeps rules at 8/8 while enforce exposes the known false reject.</section>
<p class='note'>This report replays the captured Qwen run; it makes no new MCP or model calls. Source trace remains linked in JSON.</p></main></html>"""


def main():
    summary = replay()
    PREFIX.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    PREFIX.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(json.dumps({"supported": summary["supported"], "metrics": summary["metrics"]},
                     ensure_ascii=False, indent=2))
    print(f"[ARTIFACT] {PREFIX.with_suffix('.html')}")
    print(f"[ARTIFACT] {PREFIX.with_suffix('.json')}")


if __name__ == "__main__":
    main()
