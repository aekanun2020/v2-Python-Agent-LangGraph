# Lab 4 — Agent เชื่อมต่อ MCP Server จริง

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 1.4

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 3 (Tools+Skills) เป็นหลัก — ต่อ **MCP** จริงเป็นแหล่ง tools ภายนอก โดยยังหมุนใน Reasoning Loop (Layer 5) เดิม

---

## จุดประสงค์การเรียนรู้

- ค้นพบ MCP tools อัตโนมัติผ่าน **Streamable HTTP** (`core.mcp_client`) โดยเรียก `initialize` + `tools/list`
- แปลง MCP `inputSchema` ให้เป็น **OpenAI function parameters** ผ่าน `core.registry.mcp_to_openai_tools`
- ใช้ **Tool Registry** รวม tools จากหลาย MCP server ไว้ที่เดียวและ dispatch กลับไปยัง server ที่ถูกต้อง
- ต่อสะพานระหว่างสองหลักสูตร: หลักสูตรที่ 1 ใช้ Claude Desktop/LangFlow เป็น MCP client — Lab นี้เขียน MCP client เป็น Python เองแล้วต่อเข้ากับ agent loop

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง **MCP MSSQL Server จริง** ที่เปิดและ expose ผ่าน ngrok แล้ว

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab4_mcp_agent/agent_mcp.py "มีตารางอะไรบ้างในฐานข้อมูล และมีพนักงานทั้งหมดกี่คน"
```

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab4_mcp_agent/agent_mcp.py`

### `main()` — สร้าง Tool Registry และ discover MCP tools

```python
registry = ToolRegistry()
n = registry.add_server(config.MCP_SERVER_URL)
print(f"[MCP] ค้นพบ {n} tools: {registry.tool_names}")
```

`ToolRegistry.add_server()` (ใน `labs/core/registry.py`) เชื่อมต่อ MCP Server ผ่าน Streamable HTTP, เรียก `initialize` + `tools/list`, แล้วแปลง inputSchema → OpenAI function format เก็บไว้ใน `registry.openai_tools` พร้อมใช้

> จุดที่ควรเปิดอ่าน: `labs/core/registry.py` ฟังก์ชัน `add_server()` และ `mcp_to_openai_tools()` — นี่คือ "ตัวแปลภาษา" ระหว่าง MCP schema กับ OpenAI function calling

### `run_agent(question, registry, max_steps)` — agent loop + MCP dispatch

```python
resp = llm.chat(messages=messages, tools=registry.openai_tools)
...
result = registry.dispatch(call.function.name, args)
```

- `registry.openai_tools` ส่งไปให้ LLM รู้ว่ามี tools อะไรบ้าง (เหมือน Lab 3 แต่ใช้ MCP tools แทน local tools)
- `registry.dispatch(name, args)` ส่ง tool call ไปยัง MCP Server จริงแล้วรับผลกลับมาใส่ใน messages

### System prompt — ควบคุม workflow ของ agent

```python
SYSTEM = (
    "...เรียก get_database_context ก่อนเสมอเพื่อดู schema แล้วจึงเขียน T-SQL "
    "ที่ถูกต้อง (ใช้ TOP ไม่ใช่ LIMIT, GETDATE() ไม่ใช่ NOW())..."
)
```

System prompt บังคับให้ agent วางแผนถูกต้อง: ดู schema ก่อน → เขียน T-SQL → ส่งให้ `execute_query_tool`

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] เชื่อม https://...ngrok-free.app/mcp
[MCP] ค้นพบ 5 tools: ['get_database_context', 'execute_query_tool', ...]

[user] มีตารางอะไรบ้างในฐานข้อมูล และมีพนักงานทั้งหมดกี่คน
[step 1] THINK -> ขอเรียก 1 tool
           TOOL_USE get_database_context(...)
[step 2] THINK -> ขอเรียก 1 tool
           TOOL_USE execute_query_tool(...)
[step 3] END_TURN
------------------------------------------------------------
[answer]
ฐานข้อมูล TestDB มี 16 ตาราง มีพนักงานทั้งหมด 25 คน แบ่งเป็น 8 แผนก...
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab4_mcp_agent.png`
