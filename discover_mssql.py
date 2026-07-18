"""ตรวจการเชื่อมต่อ MCP MSSQL จริง (ngrok) + ค้นพบ tools และ schema.

อ่าน MCP_SERVER_URL จาก .env (แก้ URL ngrok ที่ไฟล์ .env ที่เดียว — ไม่ต้องแก้โค้ด)
"""
import os
import asyncio
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()
URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp")


async def main():
    client = MultiServerMCPClient(
        {"mssql": {"url": URL, "transport": "streamable_http"}}
    )
    tools = await client.get_tools()
    print(f"[MCP] connected. discovered {len(tools)} tools:\n")
    for t in tools:
        print("=" * 60)
        print(f"name        : {t.name}")
        print(f"description : {t.description}")
        try:
            schema = t.args_schema
            print(f"args        : {schema}")
        except Exception as e:
            print(f"args        : (n/a) {e}")


if __name__ == "__main__":
    asyncio.run(main())
