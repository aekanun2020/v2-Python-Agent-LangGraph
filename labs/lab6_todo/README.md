# Lab 6 — TodoWrite: วางแผน Multi-step Task

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 2.2

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 3 (Skills) + เริ่มแตะ Layer 2 (Memory) — TodoWrite คือ state ของแผนงานหลายขั้นที่ไหลข้าม step

---

## จุดประสงค์การเรียนรู้

- เพิ่ม internal tools (`todo_write`, `todo_update`) เพื่อให้ agent วางแผนงานหลายขั้นก่อนเริ่มลงมือ
- เข้าใจการจัดการ **state ใน agent** ด้วย class `TodoState` ที่เก็บ todo list ไว้ใน memory
- เห็นว่า agent ใช้ todo เป็นแผนงาน แล้วอัปเดตสถานะ (todo → doing → done) ระหว่างทำงานจริงด้วย MCP tools

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab6_todo/agent_todo.py
```

(default task คือรายงาน HR 3 ขั้น: นับพนักงานแยกแผนก → top-3 มูลค่าโครงการ → สรุปเชิงธุรกิจ)

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab6_todo/agent_todo.py`

### `TodoState` — state ของ todo list (in-memory)

```python
class TodoState:
    def write(self, items: list[str]) -> str: ...    # สร้าง todo ใหม่ทั้งหมด
    def update(self, index: int, status: str) -> str: ...  # เปลี่ยนสถานะทีละข้อ
    def render(self) -> str: ...                     # แสดง [ ] / [~] / [x] ต่อ item
```

`render()` คืน string เช่น `"[x] 1. นับพนักงาน\n[~] 2. top-3\n[ ] 3. สรุป"` — LLM อ่านและรู้สถานะปัจจุบันของแผนงาน

> จุดที่ควรเปิดอ่าน: method `update()` — มี logic รองรับทั้ง 1-based index (ตาม render) และ 0-based (ที่ LLM บางครั้งส่งมาผิด) เพื่อความทนทาน

### `build_tools(registry)` — รวม todo tools + MCP tools

```python
todo_tools = [
    {tool: "todo_write", ...},   # สร้าง todo list
    {tool: "todo_update", ...},  # อัปเดตสถานะ
]
return todo_tools + registry.openai_tools   # รวมกับ MCP tools
```

agent เห็น tools ทั้งหมดรวมกัน — ตัดสินใจว่าจะใช้ todo tool หรือ MCP tool ตามความเหมาะสม

### `run(question, registry, max_steps=30)` — agent loop + todo dispatch

```python
if name == "todo_write":
    result = todo.write(args.get("items", []))
elif name == "todo_update":
    result = todo.update(args.get("index"), args.get("status"))
else:
    result = registry.dispatch(name, args)   # MCP tool
```

todo tools ถูก handle ใน Python โดยตรง (ไม่ผ่าน MCP) ส่วน tools อื่นส่งไป `registry.dispatch()`

### System prompt — บังคับ planning ก่อน action

```python
SYSTEM = (
    "...ถ้างานมี 3 ขั้นขึ้นไป ให้เรียก todo_write เขียนแผนก่อนเริ่มลงมือ "
    "แล้วทำทีละข้อ เรียก todo_update เปลี่ยนสถานะเป็น 'doing' ก่อนทำ และ 'done' เมื่อเสร็จ..."
)
```

pattern นี้คือ **plan-then-execute** ที่ให้ agent โปร่งใสและตรวจสอบได้

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] ค้นพบ 5 tools

[user] ช่วยทำรายงาน HR: 1) นับพนักงาน... 2) หาพนักงาน... 3) สรุป...
[step 1] TODO_WRITE
[ ] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[ ] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[ ] 3. สรุปข้อค้นพบเชิงธุรกิจ
[step 2] TODO_UPDATE -> {'index': 1, 'status': 'doing'}
...
[step N] TODO_UPDATE -> {'index': 3, 'status': 'done'}
------------------------------------------------------------
[answer]
สรุปข้อค้นพบ: แผนก IT มีพนักงานมากที่สุด...
------------------------------------------------------------
[todo สุดท้าย]
[x] 1. นับพนักงานที่ปฏิบัติงานแยกตามแผนก
[x] 2. หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก
[x] 3. สรุปข้อค้นพบเชิงธุรกิจ
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab6_todowrite.png`
