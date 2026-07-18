"""Discover HR table fields from the configured MSSQL MCP server."""

import asyncio
import json
import os

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

HR_TABLES = [
    "employees", "performance_reviews", "training_records", "position_history",
    "projects", "skills", "certifications", "education",
]


def tool_text(result) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, list):
        return "\n".join(str(getattr(part, "text", part)) for part in content)
    return str(content)


async def main():
    load_dotenv()
    endpoint = os.environ["MCP_SERVER_URL"]
    client = MultiServerMCPClient(
        {"mssql": {"url": endpoint, "transport": "streamable_http"}}
    )
    tools = {tool.name: tool for tool in await client.get_tools()}
    table_list = ", ".join(f"N'{table}'" for table in HR_TABLES)
    query = f"""
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ({table_list})
ORDER BY TABLE_NAME, ORDINAL_POSITION
""".strip()
    result = await tools["execute_query_tool"].ainvoke({"query": query})
    print(f"[MCP] {endpoint}")
    print(f"[HR TABLES REQUESTED] {json.dumps(HR_TABLES)}")
    print(tool_text(result))


if __name__ == "__main__":
    asyncio.run(main())
