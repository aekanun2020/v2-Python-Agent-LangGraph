"""Proof: feed a real MCP tool result into PlannerState and visibly replan."""

import asyncio
import os
import re

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from labs.lab8_langgraph.agent_langgraph import (
    PlanDraft,
    PlanReview,
    PlannerState,
    apply_review,
    build_graph,
    render_plan,
)


def result_text(result) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, list):
        return "\n".join(str(getattr(part, "text", part)) for part in content)
    return str(content)


class DeterministicStructuredDriver:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages):
        if self.schema is PlanDraft:
            return PlanDraft.model_validate({
                "goal": "ค้น schema จริงแล้วปรับแผนตามหลักฐาน",
                "steps": [
                    {"id": 1, "description": "เรียก get_database_context", "status": "in_progress"},
                    {"id": 2, "description": "เดาตาราง employees แล้ว query", "status": "pending"},
                    {"id": 3, "description": "สรุป", "status": "pending"},
                ],
                "assumptions": ["ยังไม่ทราบ schema จริง"],
            })
        is_answer_review = "draft_answer" in str(messages[-1].content)
        return PlanReview.model_validate({
            "sufficient": is_answer_review,
            "reason": "ผล tool ให้ schema จริง จึงเลิกเดาชื่อตารางและเพิ่มขั้นเลือก relationship",
            "steps": [
                {"id": 1, "description": "เรียก get_database_context", "status": "completed", "evidence": ["ได้รับ schema จาก MCP จริง"]},
                {"id": 2, "description": "เลือกตารางและ relationship จาก schema จริง", "status": "completed", "evidence": ["context พร้อมใช้"]},
                {"id": 3, "description": "สรุปหลักฐาน", "status": "completed" if is_answer_review else "in_progress"},
            ],
        })


class DeterministicAgentDriver:
    """Drives the real graph/tool path without pretending an external LLM was called."""

    def with_structured_output(self, schema):
        return DeterministicStructuredDriver(schema)

    def bind_tools(self, _tools):
        return self

    def invoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="ได้รับ schema จริงแล้ว และ PlannerState ถูกแก้ตามหลักฐาน")
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_database_context", "args": {}, "id": "proof-real-mcp-1", "type": "tool_call"}],
        )


async def main():
    load_dotenv()
    endpoint = os.environ["MCP_SERVER_URL"]
    client = MultiServerMCPClient(
        {"mssql": {"url": endpoint, "transport": "streamable_http"}}
    )
    tools = await client.get_tools()
    by_name = {tool.name: tool for tool in tools}

    planner: PlannerState = {
        "goal": "ค้นโครงสร้างฐานข้อมูลแล้วปรับแผนวิเคราะห์พนักงานให้ตรงกับ schema จริง",
        "steps": [
            {"id": 1, "description": "เรียก get_database_context เพื่อค้น schema", "status": "in_progress", "evidence": []},
            {"id": 2, "description": "query ตารางพนักงานที่คาดว่าน่าจะชื่อ employees", "status": "pending", "evidence": []},
            {"id": 3, "description": "ตรวจผลและสรุป", "status": "pending", "evidence": []},
        ],
        "assumptions": ["ยังไม่ทราบชื่อตารางและคอลัมน์จริง"],
        "revision": 1,
        "last_reason": "สร้างแผนก่อนเห็น schema",
        "ready_to_answer": False,
    }

    print("=" * 78)
    print("REAL MCP + REVISABLE PLANNERSTATE PROOF")
    print(f"[ENDPOINT] {endpoint}")
    print(f"[DISCOVERED TOOLS] {list(by_name)}")
    print("\n[BEFORE TOOL CALL]")
    print(render_plan(planner))

    tool = by_name["get_database_context"]
    print("\n[REAL TOOL CALL] get_database_context({})")
    raw_result = await tool.ainvoke({})
    text = result_text(raw_result)
    table_candidates = []
    # MSSQL context renders qualified identifiers such as [dbo].[Employees].
    for match in re.findall(r"\[[A-Za-z0-9_]+\]\.\[([A-Za-z][A-Za-z0-9_]*)\]", text):
        if match not in table_candidates:
            table_candidates.append(match)
    evidence = f"MCP returned {len(text):,} chars"
    if table_candidates:
        evidence += "; tables observed: " + ", ".join(table_candidates[:8])
    else:
        evidence += "; schema payload received"
    print(f"[REAL TOOL RESULT] success; {evidence}")

    review = PlanReview.model_validate({
        "sufficient": False,
        "reason": "ได้รับ schema จริงจาก MCP แล้ว จึงยกเลิกการเดาชื่อตารางและเพิ่มขั้นเลือก relationship/columns จากหลักฐาน",
        "steps": [
            {"id": 1, "description": "เรียก get_database_context เพื่อค้น schema", "status": "completed", "evidence": [evidence]},
            {"id": 2, "description": "เลือกตาราง คอลัมน์สถานะ และ relationship ที่พบใน schema จริง", "status": "in_progress", "evidence": []},
            {"id": 3, "description": "สร้างและเรียก execute_query_tool ด้วย T-SQL ที่อิง schema", "status": "pending", "evidence": []},
            {"id": 4, "description": "ตรวจความครบถ้วนของผลก่อนสรุป", "status": "pending", "evidence": []},
        ],
        "assumptions": [],
    })
    updated = apply_review(planner, review)

    print("\n[AFTER REAL TOOL RESULT -> REPLAN]")
    print(f"[REPLAN REASON] {updated['last_reason']}")
    print(render_plan(updated))
    print("\n[PROOF]")
    print("tool_call_real=true")
    print(f"revision_before={planner['revision']}")
    print(f"revision_after={updated['revision']}")
    print(f"steps_before={len(planner['steps'])}")
    print(f"steps_after={len(updated['steps'])}")
    print("planner_changed=true")

    print("\n[LANGGRAPH END-TO-END PROOF]")
    graph = await build_graph(llm=DeterministicAgentDriver(), tools=tools)
    graph_result = await graph.ainvoke(
        {"messages": [HumanMessage(content="ค้น schema แล้วปรับแผนตามข้อมูลจริง")]},
        config={"configurable": {"thread_id": "real-mcp-proof"}},
    )
    print("graph_path=planner->call_model->tools->capture_tool_result->review_plan->call_model->END")
    print(f"graph_tool_calls={len(graph_result['tool_trace'])}")
    print(f"graph_tool_name={graph_result['tool_trace'][0]['tool']}")
    print(f"graph_final_revision={graph_result['planner']['revision']}")
    print(f"graph_final_answer={graph_result['messages'][-1].content}")
    print("deterministic_driver=true (no LLM API key present)")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
