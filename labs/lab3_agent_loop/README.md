# Lab 3 — สร้าง Agent Loop แรกด้วย Pure Python

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 1.3

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 5 (Reasoning Loop) เป็นหลัก — สร้างวง reason→act→observe ด้วยมือ (ReAct) + แตะ Layer 3 ด้วย local tools

---

## จุดประสงค์การเรียนรู้

- เข้าใจสูตร **Minimal Agent = while loop + model + tools** โดยไม่ใช้ framework ใดเลย
- นิยาม local tools (ฟังก์ชัน + OpenAI function schema) และเชื่อมเข้า agent loop
- เห็นวงจร **THINK → TOOL_USE → OBSERVE → END_TURN** ที่เขียนเองด้วย Pure Python
- เทียบกับสิ่งที่ Lab 8 จะได้รับ "ฟรี" จาก LangGraph (เข้าใจ framework โดยรู้เบื้องหลัง)

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab3_agent_loop/agent_loop.py "ตอนนี้กี่โมง แล้ว 15*4 เท่ากับเท่าไร"
```

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab3_agent_loop/agent_loop.py`

### (1) Local tools — ฟังก์ชัน + schema แบบ OpenAI function

```python
def get_time() -> str: ...       # คืนวันเวลาปัจจุบัน
def calculate(expression: str):  # คำนวณนิพจน์เลขคณิต (whitelist อักขระปลอดภัย)

LOCAL_FUNCS = {"get_time": ..., "calculate": ...}
TOOLS = [...]   # schema แบบ OpenAI function ของ get_time และ calculate
```

`TOOLS` คือ list ของ dict ที่มีฟิลด์ `type: "function"` พร้อม `name`, `description`, และ `parameters` (JSON Schema) — นี่คือรูปแบบที่ส่งให้ `llm.chat(tools=TOOLS)` เพื่อให้ LLM รู้ว่ามี tool อะไรบ้าง

### (2) `dispatch(name, args)` — เรียก local function ตามชื่อ tool

```python
def dispatch(name: str, args: dict) -> str:
    fn = LOCAL_FUNCS.get(name)
    return fn(**args) if fn else f"error: ไม่พบ tool {name}"
```

เป็น bridge ที่แปลง tool call จาก LLM ให้เรียก Python function จริง

### (3) `run_agent(question, max_steps)` — heart of the agent loop

```python
for step in range(1, max_steps + 1):
    resp = llm.chat(messages=messages, tools=TOOLS)
    msg = resp.choices[0].message

    if msg.tool_calls:
        # THINK: LLM ตัดสินใจเรียก tool
        # TOOL_USE: dispatch() เรียก function จริง
        # OBSERVE: append role="tool" กลับเข้า messages
        continue   # วนกลับให้ LLM อ่านผล tool

    # END_TURN: ไม่มี tool_calls = LLM ตอบสรุป
    print(f"[answer] {msg.content}")
    return msg.content
```

จุดสำคัญคือต้อง `append` assistant message ที่มี `tool_calls` **ก่อน** แล้วจึง append `role="tool"` — ลำดับนี้ตาม OpenAI API spec อย่างเคร่งครัด

> จุดที่ควรเปิดอ่าน: บล็อก `messages.append({"role": "tool", "tool_call_id": call.id, "content": result})` — นี่คือ OBSERVE step ที่ป้อนผล tool กลับเข้า context เพื่อให้ LLM อ่านต่อ

---

## ผลลัพธ์ที่คาดหวัง

```
[user] ตอนนี้กี่โมง แล้ว 15*4 เท่ากับเท่าไร
[step 1] THINK -> ขอเรียก 2 tool
           TOOL_USE get_time({}) -> 2025-06-25 19:47:00
           TOOL_USE calculate({'expression': '15*4'}) -> 60
[step 2] END_TURN
------------------------------------------------------------
[answer] ตอนนี้เวลา 19:47:00 และ 15×4 = 60
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab3_agent_loop.png`
