"""Compare Lab 6 TodoWrite with the Pure Python Planner on one HR challenge."""

from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from labs.core import config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.agent_planner import run as run_planner
from labs.lab6_todo.agent_todo import run as run_todo
from scripts.hr_challenges import HR_CHALLENGES
from scripts.hr_analytical_contract import contract_for, validate_sql


class CountingRegistry(ToolRegistry):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def dispatch(self, name: str, arguments: dict) -> str:
        self.calls.append(name)
        return super().dispatch(name, arguments)


def execute(label: str, runner, question: str) -> tuple[dict, int, int]:
    registry = CountingRegistry()
    registry.add_server(config.MCP_SERVER_URL)
    started = time.perf_counter()
    try:
        result = runner(question, registry)
    finally:
        registry.close()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"[{label}] mcp_calls={len(registry.calls)} elapsed_ms={elapsed_ms}")
    return result, len(registry.calls), elapsed_ms


def render(summary: dict) -> str:
    old, new = summary["todo_write"], summary["pure_planner"]
    approved = "APPROVED" if new["approved"] else "REJECTED"
    adversarial = ""
    if summary.get("adversarial_fault_injection"):
        status = "TRIGGERED → RECOVERED" if summary.get("fault_injection_triggered") and new["approved"] else "NOT RECOVERED"
        adversarial = f"<section class='proof'><b>ADVERSARIAL REPLAN PROOF</b>Late grain audit fault: {status} · final revision {new['revision']} · rejected query was not sent to MCP.</section>"
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Lab 6 HR Comparison</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:16px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1180px;margin:28px auto;padding:0 24px}}h1{{color:#8be9fd;font-size:30px;margin:0;overflow-wrap:anywhere}}.sub{{color:#9ca8c7;margin:7px 0 22px}}.grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}}.card,.proof{{min-width:0;background:#111a31;border:1px solid #2c3a60;border-radius:14px;padding:20px}}.old{{border-top:5px solid #ffb86c}}.new{{border-top:5px solid #50fa7b}}h2{{margin:0 0 15px;font-size:21px}}.metrics{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.metric{{background:#182440;border-radius:9px;padding:14px;text-align:center;color:#aeb8d4}}.metric b{{display:block;font-size:25px;color:#50fa7b}}.old .metric b{{color:#ffb86c}}.proof{{margin-top:16px;border-left:5px solid #bd93f9}}.proof b{{display:block;color:#bd93f9}}code{{color:#f1fa8c}}</style><main>
<h1>LAB 6: TODOWRITE vs PURE PYTHON PLANNER</h1><div class='sub'>Same HR challenge · same model: <code>{html.escape(summary['model'])}</code> · same live MCP</div>
<div class='grid'><section class='card old'><h2>ORIGINAL — TodoWrite</h2><div class='metrics'><div class='metric'><b>{old['mcp_calls']}</b>MCP calls</div><div class='metric'><b>{old['elapsed_ms']/1000:.1f}s</b>elapsed</div><div class='metric'><b>{old['done_items']}/{old['total_items']}</b>todos done</div><div class='metric'><b>NONE</b>evidence gate</div></div><p>LLM owns todo status and decides when work is done.</p></section>
<section class='card new'><h2>ENHANCED — Runtime-owned plan</h2><div class='metrics'><div class='metric'><b>{new['mcp_calls']}</b>MCP calls</div><div class='metric'><b>{new['elapsed_ms']/1000:.1f}s</b>elapsed</div><div class='metric'><b>{new['revision']}</b>plan revision</div><div class='metric'><b>{approved}</b>answer gate</div></div><p>Python validates transitions and binds MCP evidence to active steps.</p></section></div>
<section class='proof'><b>WHAT THIS COMPARISON TESTS</b>Can the agent prove each completed step with an observed MCP result, and can Python reject an unsupported final answer without LangGraph?</section>
<section class='proof'><b>SCHEMA-GROUNDED HR CHALLENGE</b>{len(summary['required_fields'])} required MCP fields validated before this run · result describes one run, not a universal benchmark.</section>
{adversarial}
</main></html>"""


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", choices=HR_CHALLENGES, default="skills_project_risk")
    parser.add_argument("--adversarial", action="store_true", help="inject one late fan-out audit rejection")
    args = parser.parse_args()
    challenge = HR_CHALLENGES[args.challenge]
    question = challenge["question"] + "\n\n" + contract_for(args.challenge)

    todo, todo_calls, todo_ms = execute(
        "TODO ORIGINAL", lambda q, r: run_todo(q, r, return_details=True), question
    )
    injected = {"done": False}

    def planner_validator(name: str, arguments: dict):
        natural_rejection = validate_sql(args.challenge, name, arguments)
        if natural_rejection:
            return natural_rejection
        sql = str(arguments.get("query", "")).lower()
        if args.adversarial and not injected["done"] and name == "execute_query_tool" and sql.count(" join ") >= 3:
            injected["done"] = True
            return "fault injection: late grain audit requires query reconstruction before execution"
        return None

    planner, planner_calls, planner_ms = execute(
        "PURE PLANNER",
        lambda q, r: run_planner(q, r, tool_validator=planner_validator),
        question,
    )
    state = planner["planner"]
    summary = {
        "challenge_id": args.challenge,
        "question": question,
        "analytical_contract": contract_for(args.challenge),
        "adversarial_fault_injection": args.adversarial,
        "fault_injection_triggered": injected["done"],
        "model": os.environ.get("OPENROUTER_MODEL", config.OPENROUTER_MODEL),
        "mcp_endpoint": config.MCP_SERVER_URL,
        "required_fields": challenge["required_fields"],
        "todo_write": {"mcp_calls": todo_calls, "elapsed_ms": todo_ms,
                       "total_items": len(todo["todo_items"]),
                       "done_items": sum(item["status"] == "done" for item in todo["todo_items"]),
                       "answer": todo["answer"]},
        "pure_planner": {"mcp_calls": planner_calls, "elapsed_ms": planner_ms,
                         "revision": state.revision, "approved": state.answer_approved,
                         "completed_steps": sum(step.status == "completed" for step in state.steps),
                         "total_steps": len(state.steps), "answer": planner["answer"],
                         "tool_trace": planner["tool_trace"]},
    }
    label = "lab6_hr_adversarial" if args.adversarial else "lab6_hr_comparison"
    prefix = Path(f"artifacts/{label}_{args.challenge}")
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    prefix.with_suffix(".html").write_text(render(summary), encoding="utf-8")
    print(f"[ARTIFACT] {prefix.with_suffix('.html')}")
    print(f"[ARTIFACT] {prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
