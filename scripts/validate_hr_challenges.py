"""Validate required fields and non-empty preflight results for HR challenges."""

import asyncio
import os
import re

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

from scripts.hr_challenges import HR_CHALLENGES


def tool_text(result) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, list):
        return "\n".join(str(getattr(part, "text", part)) for part in content)
    return str(content)


async def main():
    load_dotenv()
    endpoint = os.environ["MCP_SERVER_URL"]
    client = MultiServerMCPClient({"mssql": {"url": endpoint, "transport": "streamable_http"}})
    tools = {tool.name: tool for tool in await client.get_tools()}
    query_tool = tools["execute_query_tool"]

    for challenge_id, challenge in HR_CHALLENGES.items():
        predicates = []
        for field in challenge["required_fields"]:
            table, column = field.split(".", 1)
            predicates.append(f"(TABLE_NAME=N'{table}' AND COLUMN_NAME=N'{column}')")
        field_query = (
            "SELECT COUNT(*) AS matched_fields FROM INFORMATION_SCHEMA.COLUMNS WHERE "
            + " OR ".join(predicates)
        )
        field_result = tool_text(await query_tool.ainvoke({"query": field_query}))
        match = re.search(r"matched_fields\\n\s*(\d+)", field_result)
        matched = int(match.group(1)) if match else -1
        if matched != len(challenge["required_fields"]):
            raise RuntimeError(
                f"{challenge_id}: matched {matched}/{len(challenge['required_fields'])} fields"
            )
        preflight = tool_text(await query_tool.ainvoke({"query": challenge["preflight_sql"]}))
        if not preflight.strip():
            raise RuntimeError(f"{challenge_id}: empty preflight result")
        print(f"[VALID] {challenge_id}: fields={len(challenge['required_fields'])}, preflight_nonempty=true")
        print(preflight[:900])
        print()


if __name__ == "__main__":
    asyncio.run(main())
