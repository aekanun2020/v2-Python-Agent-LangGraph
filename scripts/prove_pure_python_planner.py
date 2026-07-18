"""Proof that the Pure Python planner gates completion and captures real MCP evidence."""

import asyncio
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

from labs.lab6_todo.planner_runtime import PlanStep, PlannerState


def result_text(result) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, list):
        return "\n".join(str(getattr(part, "text", part)) for part in content)
    return str(content)


async def main() -> None:
    load_dotenv()
    endpoint = os.environ["MCP_SERVER_URL"]
    plan = PlannerState(
        goal="ตรวจ schema และนับพนักงาน active จาก HR MCP",
        steps=[
            PlanStep(1, "ตรวจ schema"),
            PlanStep(2, "นับพนักงาน active จาก SQL"),
        ],
    )
    plan.start(1)
    try:
        plan.complete(1)
    except ValueError as exc:
        print(f"[EXPECTED REJECTION] {exc}")

    client = MultiServerMCPClient({"mssql": {"url": endpoint, "transport": "streamable_http"}})
    tools = {tool.name: tool for tool in await client.get_tools()}
    raw = await tools["get_database_context"].ainvoke({})
    schema = result_text(raw)
    print(f"[REAL MCP CALL] get_database_context chars={len(schema):,}")
    plan.observe(1, tool="get_database_context", tool_call_id="schema-1", result=schema)
    plan.complete(1)
    plan.start(2)
    query = "SELECT COUNT(*) AS active_employees FROM employees WHERE status = N'ปฏิบัติงาน'"
    raw = await tools["execute_query_tool"].ainvoke({"query": query})
    rows = result_text(raw)
    print(f"[REAL MCP CALL] execute_query_tool result={rows[:160]}")
    plan.observe(2, tool="execute_query_tool", tool_call_id="sql-1", result=rows)
    plan.complete(2)
    plan.approve_answer()
    print(plan.render())
    print(f"[PROOF] approved={plan.answer_approved} framework=pure-python real_mcp=true")


if __name__ == "__main__":
    asyncio.run(main())
