# Lab 8 — สร้าง Agent ด้วย LangGraph

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 3.1

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** รวม Layer 2 (Memory ผ่าน Checkpointer) + 3 (Tools) + 5 (Reasoning Loop เป็น graph) เข้าด้วยกัน — จุด pivot ที่ framework ห่อหลาย layer ให้

---

## จุดประสงค์การเรียนรู้

- สร้าง Agent ด้วย **LangGraph** ครบ 4 องค์ประกอบหลัก: **State / Node / Edge / Checkpointer**
- ใช้ `PlannerState` เก็บ goal, steps, status, evidence, assumptions และ revision
- ตรวจผล tool ผ่าน `review_plan` และแก้แผนก่อนทำขั้นถัดไป
- เปรียบเทียบ Pure Python Agent (Lab 1–7) กับ LangGraph — เห็นว่า framework ช่วย "ลดโค้ดส่วนไหน"
- ใช้ **Conditional Routing** (`should_continue`) แทน `if msg.tool_calls` ที่เขียนมือใน Lab 3–7
- ใช้ **MemorySaver Checkpointer** รับ memory ข้ามรอบ "ฟรี" แทน `ConversationMemory` ที่เขียนเองใน Lab 7
- ค้นพบ MCP tools อัตโนมัติผ่าน `MultiServerMCPClient` (LangChain MCP Adapters)

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo

python labs/lab8_langgraph/agent_langgraph.py
```

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab8_langgraph/agent_langgraph.py`

### (1) `AgentState` — State ที่ไหลผ่านทุก Node

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    planner: PlannerState
    tool_trace: list[dict]
```

`add_messages` เป็น reducer ของ LangGraph — เมื่อ Node คืน `{"messages": [new_msg]}` จะ **append** เข้า list อัตโนมัติ ไม่ต้องเขียน `messages.append(...)` เองเหมือน Lab 3–7

`planner` เป็น state ที่ตรวจสอบได้โดยตรง แผนจึงเปลี่ยน revision ตามหลักฐานใหม่จาก MCP
และเก็บเหตุผลไว้ใน `last_reason`

```text
planner → call_model → tools → capture_tool_result → review_plan ─┐
                    └→ review_answer → APPROVED → END             │
                              └→ REJECTED → call_model ←──────────┘
```

รันหลักฐานโดยไม่ใช้ LLM API key แต่เรียก MCP tool จริง:

```bash
python -m scripts.prove_planner_mcp
```

`scripts.prove_planner_mcp` โหลด `MCP_SERVER_URL` จาก `.env` และใช้ deterministic
driver เฉพาะส่วนตัดสินใจ แต่ `ToolNode` และ MCP call เป็นของจริง ส่วนการรัน
`agent_langgraph.py` ใช้ OpenRouter LLM จริงทั้ง Planner, Reviewer และ tool selection

### (2) Nodes — call_model และ tools

```python
def call_model(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

tool_node = ToolNode(tools)   # ToolNode รัน MCP tools ได้โดยตรง
```

`call_model` แทน `resp = llm.chat(...)` ของ Pure Python  
`ToolNode(tools)` แทนบล็อก `for call in msg.tool_calls: dispatch(...)` ทั้งหมด

### (3) Edges — Conditional Routing

```python
def should_continue(state: AgentState):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END

graph.add_edge(START, "call_model")
graph.add_conditional_edges("call_model", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "call_model")   # วนกลับ
```

`should_continue` แทน `if msg.tool_calls: continue` ใน agent loop ของ Pure Python — LangGraph จัดการ routing เองจาก edge definition

### (4) `MemorySaver` Checkpointer

```python
checkpointer = MemorySaver()
return graph.compile(checkpointer=checkpointer)
```

`MemorySaver` เก็บ state ทุก `thread_id` ไว้ใน memory — แทน `ConversationMemory` ที่เขียนเองใน Lab 7 โดยไม่ต้องเขียน logic ใดเพิ่ม

### MCP Tool Discovery — `MultiServerMCPClient`

```python
client = MultiServerMCPClient(
    {"mcp": {"url": MCP_SERVER_URL, "transport": "streamable_http"}}
)
tools = await client.get_tools()
llm_with_tools = build_llm().bind_tools(tools)
```

`MultiServerMCPClient.get_tools()` (langchain-mcp-adapters) แทน `ToolRegistry.add_server()` ของ Pure Python — ค้นพบ tools จาก MCP Server แล้วแปลงเป็น LangChain tool objects พร้อมใช้

> จุดที่ควรเปิดอ่าน: ฟังก์ชัน `build_graph()` ทั้งหมด — เปรียบเทียบบรรทัดต่อบรรทัดกับ `run_agent()` ใน Lab 4 จะเห็นชัดว่า LangGraph ลด boilerplate อะไรบ้าง

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] เชื่อมกับ https://...ngrok-free.app/mcp
[MCP] ค้นพบ 5 tools: ['get_database_context', 'execute_query_tool', ...]

[Q1] ผู้ใช้: แต่ละแผนกมีพนักงานที่ยัง 'ปฏิบัติงาน' อยู่กี่คน เรียงจากมากไปน้อย
[A1] Agent: แผนก IT: 5 คน, แผนก HR: 3 คน, ...

[Q2] ผู้ใช้: พนักงาน 5 อันดับแรกที่ทำโครงการรวมมูลค่าสูงสุดคือใคร
[A2] Agent: 1. สมชาย (IT) — 2.5M บาท, ...

======================================================================
[Checkpointer] มี 11 messages ใน thread นี้
```

Screenshots ตัวอย่าง:
- `../../screenshots/labs/lab8_01_mssql_discovery.png` — MCP Tool Discovery
- `../../screenshots/labs/lab8_02_agent_q1.png` — ตอบ Q1
- `../../screenshots/labs/lab8_03_agent_q2.png` — ตอบ Q2 + Checkpointer จำ context ข้ามคำถาม
