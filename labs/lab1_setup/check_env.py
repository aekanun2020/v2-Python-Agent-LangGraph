"""
Lab 1 — ติดตั้งและตรวจสอบสภาพแวดล้อมการพัฒนา
อ้างอิง outline: บทที่ 1.2 / แบบฝึกหัดที่ 1

ตรวจ 2 อย่างที่เป็น precondition ของทุก Lab ถัดไป:
  (1) เรียก LLM ผ่าน OpenRouter ได้จริง (thin client: OpenAI SDK + base_url)
  (2) MCP MSSQL Server จริงของหลักสูตรที่ 1 ยังรันอยู่ (initialize + tools/list)

รัน:  python labs/lab1_setup/check_env.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import config, llm
from labs.core.mcp_client import MCPClient


def check_llm() -> bool:
    print("[1/2] ตรวจ OpenRouter (LLM) ...")
    try:
        resp = llm.chat(
            messages=[{"role": "user", "content": "ตอบสั้น ๆ คำเดียวว่า 'พร้อม'"}],
            max_tokens=20,
        )
        answer = resp.choices[0].message.content
        print(f"      โมเดล {config.OPENROUTER_MODEL} ตอบ: {answer!r}")
        return True
    except Exception as e:
        print(f"      ❌ เรียก LLM ไม่สำเร็จ: {e}")
        return False


def check_mcp() -> bool:
    print("[2/2] ตรวจ MCP MSSQL Server ...")
    client = MCPClient(config.MCP_SERVER_URL)
    try:
        info = client.initialize()
        server_name = info.get("result", {}).get("serverInfo", {}).get("name", "(unknown)")
        tools = client.list_tools()
        names = [t["name"] for t in tools]
        print(f"      เชื่อม {config.MCP_SERVER_URL}")
        print(f"      serverInfo: {server_name} — ค้นพบ {len(tools)} tools")
        print(f"      tools: {names}")
        need = {"get_database_context", "execute_query_tool"}
        ok = need.issubset(set(names))
        if not ok:
            print(f"      ❌ ไม่พบ tool ที่ต้องมี: {need - set(names)}")
        return ok
    except Exception as e:
        print(f"      ❌ เชื่อม MCP ไม่สำเร็จ: {e}")
        return False
    finally:
        client.close()


def main():
    print("=" * 60)
    print("Lab 1 — ตรวจสอบสภาพแวดล้อมการพัฒนา (หลักสูตรที่ 2)")
    print("=" * 60)
    ok_llm = check_llm()
    ok_mcp = check_mcp()
    print("-" * 60)
    if ok_llm and ok_mcp:
        print("✅ environment พร้อม — ไปต่อ Lab 2 ได้เลย")
        return 0
    print("⚠️  ยังไม่พร้อม — แก้ตามข้อความ ❌ ด้านบนก่อน")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
