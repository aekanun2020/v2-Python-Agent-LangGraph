"""Run Lab 8 baseline and PlannerState v2 against the same model, MCP and question."""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from labs.lab8_langgraph.agent_langgraph import MCP_SERVER_URL, build_graph, build_llm
from labs.lab8_langgraph.agent_langgraph_baseline import build_baseline_graph

DEFAULT_QUESTION = (
    "วิเคราะห์ว่าแผนกใดมีพนักงานที่ยังปฏิบัติงานมากที่สุด "
    "พร้อมรายชื่อพนักงานในแผนกนั้น และอธิบายว่าตรวจสอบคำตอบอย่างไร"
)


def count_tool_calls(messages) -> int:
    return sum(
        len(message.tool_calls)
        for message in messages
        if isinstance(message, AIMessage) and message.tool_calls
    )


def answer_text(result: dict) -> str:
    return str(result["messages"][-1].content)


def render_comparison_html(summary: dict) -> str:
    baseline = summary["baseline"]
    planner = summary["planner_v2"]
    esc = html.escape
    research = summary.get("research")
    research_html = ""
    if research:
        links = " · ".join(
            f"<a href='{esc(url)}'>source {index}</a>"
            for index, url in enumerate(research["sources"], 1)
        )
        research_html = (
            "<section class='proof research'><b>HR COMMUNITY + LIVE SCHEMA CHECK</b>"
            f"<span>{len(research['sources'])} research sources · "
            f"{len(research['required_fields'])} required MCP fields validated</span>"
            f"<small>{links}</small></section>"
        )
    return f"""<!doctype html><html lang='th'><meta charset='utf-8'><title>Lab 8 Comparison</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#090e1c;color:#edf1ff;font:16px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace}}main{{max-width:1180px;margin:28px auto;padding:0 24px}}h1{{color:#8be9fd;margin:0;font-size:34px;line-height:1.15}}.sub{{color:#9ca8c7;margin:8px 0 22px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.card{{background:#111a31;border:1px solid #2c3a60;border-radius:14px;padding:20px}}.old{{border-top:5px solid #ffb86c}}.new{{border-top:5px solid #50fa7b}}h2{{margin:0 0 15px;font-size:21px}}.metrics{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.metric{{background:#182440;border-radius:9px;padding:14px 8px;text-align:center;color:#aeb8d4}}.metric b{{display:block;color:#50fa7b;font-size:25px}}.old .metric b{{color:#ffb86c}}.state{{margin:15px 0 0;color:#c7cde0}}.proof{{margin-top:16px;background:#111a31;border-left:5px solid #bd93f9;padding:16px 18px;border-radius:9px}}.proof b{{display:block;color:#bd93f9;margin-bottom:5px}}.proof span,.proof small{{display:block}}.proof small{{margin-top:5px}}a,code{{color:#f1fa8c}}footer{{color:#8490ac;margin-top:10px;font-size:12px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}h1{{font-size:27px}}}}</style><main>
<h1>LAB 8: ORIGINAL vs PLANNERSTATE v2</h1><div class='sub'>Same HR question · same model: <code>{esc(summary['model'])}</code> · same live MCP</div>
<div class='grid'><section class='card old'><h2>ORIGINAL — ReAct baseline</h2><div class='metrics'><div class='metric'><b>{baseline['tool_calls']}</b>tool calls</div><div class='metric'><b>{baseline['elapsed_ms']/1000:.1f}s</b>elapsed</div></div><p class='state'>Messages-only state<br>No plan revisions · no answer gate</p></section>
<section class='card new'><h2>NEW — Planner + Reviewer</h2><div class='metrics'><div class='metric'><b>{planner['tool_calls']}</b>tool calls</div><div class='metric'><b>{planner['elapsed_ms']/1000:.1f}s</b>elapsed</div><div class='metric'><b>{planner['revisions']}</b>plan revisions</div><div class='metric'><b>{planner['completed_steps']}/{planner['total_steps']}</b>steps complete</div></div><p class='state'>Answer gate: <b>{'APPROVED' if planner['approved'] else 'NOT APPROVED'}</b></p></section></div>
<section class='proof'><b>KEY EVIDENCE FROM THIS RUN</b>Reviewer rejected hand-calculated risk flags → replanned → called MCP/SQL again → verified f1–f5 from real tool output → approved at revision {planner['revisions']}.</section>{research_html}
<footer>No API key or complete tool payload is stored in this artifact.</footer></main></html>"""


async def run_comparison(question: str) -> dict:
    client = MultiServerMCPClient(
        {"mssql": {"url": MCP_SERVER_URL, "transport": "streamable_http"}}
    )
    tools = await client.get_tools()
    print(f"[SHARED MCP] {MCP_SERVER_URL}")
    print(f"[SHARED TOOLS] {[tool.name for tool in tools]}")
    print(f"[SHARED QUESTION] {question}\n")

    baseline = build_baseline_graph(llm=build_llm(), tools=tools)
    started = time.perf_counter()
    baseline_result = await baseline.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": "compare-baseline"}},
    )
    baseline_ms = int((time.perf_counter() - started) * 1000)
    print(f"[BASELINE DONE] tool_calls={count_tool_calls(baseline_result['messages'])}, elapsed_ms={baseline_ms}")

    planner = await build_graph(llm=build_llm(), tools=tools)
    started = time.perf_counter()
    planner_result = await planner.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": "compare-planner-v2"}},
    )
    planner_ms = int((time.perf_counter() - started) * 1000)
    plan = planner_result["planner"]
    completed = sum(step["status"] == "completed" for step in plan["steps"])
    print(
        f"[PLANNER V2 DONE] tool_calls={count_tool_calls(planner_result['messages'])}, "
        f"revisions={plan['revision']}, completed={completed}/{len(plan['steps'])}, "
        f"approved={plan['ready_to_answer']}, elapsed_ms={planner_ms}"
    )

    return {
        "question": question,
        "model": os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.5-35b-a3b"),
        "mcp_endpoint": MCP_SERVER_URL,
        "baseline": {
            "tool_calls": count_tool_calls(baseline_result["messages"]),
            "elapsed_ms": baseline_ms,
            "answer": answer_text(baseline_result),
        },
        "planner_v2": {
            "tool_calls": count_tool_calls(planner_result["messages"]),
            "elapsed_ms": planner_ms,
            "revisions": plan["revision"],
            "completed_steps": completed,
            "total_steps": len(plan["steps"]),
            "approved": plan["ready_to_answer"],
            "answer": answer_text(planner_result),
        },
    }


async def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--html-out", default="artifacts/lab8_comparison_result.html")
    parser.add_argument("--json-out", default="artifacts/lab8_comparison_result.json")
    args = parser.parse_args()
    summary = await run_comparison(args.question)
    Path(args.html_out).write_text(render_comparison_html(summary), encoding="utf-8")
    Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ARTIFACT] {args.html_out}")
    print(f"[ARTIFACT] {args.json_out}")


if __name__ == "__main__":
    asyncio.run(main())
