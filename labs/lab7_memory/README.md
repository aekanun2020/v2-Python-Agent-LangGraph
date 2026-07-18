# Lab 7 — Memory Persistence: จำการสนทนาข้ามรอบ

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 2.3

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** Layer 2 (**Memory**) เป็นหลัก — จำข้ามรอบ + compaction + note-taking; พฤติกรรม inject note เป็นร่องรอยของ Layer 4 (Hooks)

---

## จุดประสงค์การเรียนรู้

- สร้าง **ConversationMemory** ที่เก็บ message history ข้ามรอบสนทนาด้วย Pure Python
- เข้าใจ **Compaction** — เมื่อ token เกินเกณฑ์ ให้ LLM สรุปบทสนทนาเก่าเป็นย่อหน้าเดียว (รักษา token budget)
- ใช้ **Note-taking** เก็บ fact สำคัญที่คงอยู่แม้หลังทำ compaction แล้ว
- เทียบกับสิ่งที่ Lab 8 จะได้รับ "ฟรี" จาก LangGraph `MemorySaver` — Lab นี้ทำให้เห็นเบื้องหลัง

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

python labs/lab7_memory/agent_memory.py
```

สคริปต์รัน 2 รอบสนทนา: รอบแรกถามแผนกที่มีพนักงานมากสุด รอบสองอ้างถึง "แผนกนั้น" (ต้องจำได้)

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab7_memory/agent_memory.py`

### `ConversationMemory` — หน่วยความจำ in-memory + compaction + notes

```python
class ConversationMemory:
    self.history: list[dict]   # messages ข้ามรอบ
    self.notes: list[str]      # fact สำคัญที่คงอยู่แม้ compaction
```

#### `add(message)` — เพิ่ม message เข้า history

เรียกหลังทุก step ของ agent loop ทั้ง user / assistant / tool messages

#### `add_note(fact)` — บันทึก fact ถาวร

```python
mem.add_note("ผู้ใช้สนใจข้อมูลแผนก IT เป็นพิเศษ")
```

notes จะถูกใส่ใน system prompt ทุกรอบ (ไม่หายหลัง compaction)

#### `context()` — ประกอบ context ส่งเข้า LLM

```python
def context(self) -> list[dict]:
    sys_msg = {"role": "system", "content": SYSTEM}
    if self.notes:
        sys_msg["content"] += "\n\n[บันทึกที่ต้องจำ]\n- " + "\n- ".join(self.notes)
    return [sys_msg] + self.history
```

รวม system + notes + history ไว้ในที่เดียว เรียกทุกครั้งก่อนส่งให้ LLM

#### `maybe_compact()` — compaction อัตโนมัติ

```python
COMPACT_AFTER_MESSAGES = 12   # เกณฑ์ (ตั้งต่ำเพื่อให้เห็นผลในแล็บ)

def maybe_compact(self):
    if len(self.history) < COMPACT_AFTER_MESSAGES:
        return
    keep = self.history[-4:]    # เก็บ 4 ข้อความล่าสุดไว้ดิบๆ
    old = self.history[:-4]     # ที่เหลือเอาไปสรุป
    summary = llm.chat([...สรุปบทสนทนา...]).choices[0].message.content
    self.history = [{"role": "assistant", "content": f"[สรุป] {summary}"}] + keep
```

> จุดที่ควรเปิดอ่าน: ค่า `COMPACT_AFTER_MESSAGES = 12` ที่ตั้งต่ำไว้เพื่อให้เห็น compaction เกิดขึ้นจริงใน lab — production ควรตั้งสูงกว่านี้

### `turn(question, mem, registry)` — หนึ่งรอบสนทนา + memory

```python
def turn(question, mem, registry, max_steps=8):
    mem.add({"role": "user", "content": question})
    for step in range(1, max_steps + 1):
        resp = llm.chat(messages=mem.context(), tools=registry.openai_tools)
        ...
        mem.add({...})      # เพิ่มทุก message เข้า history
    mem.maybe_compact()     # ตรวจว่าต้อง compact หรือยัง
```

---

## ผลลัพธ์ที่คาดหวัง

```
[MCP] ค้นพบ 5 tools

[user] แผนกที่มีพนักงานปฏิบัติงานมากที่สุดคือแผนกไหน กี่คน
[answer] แผนก IT มีพนักงานที่ยังปฏิบัติงานมากที่สุด จำนวน 5 คน

[user] แล้วในแผนกนั้น มีใครบ้าง บอกชื่อมา
[answer] แผนก IT ประกอบด้วย: สมชาย..., สมหญิง..., ...

============================================================
[memory] history เก็บ 8 ข้อความ, notes 1 รายการ
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab7_memory.png`
(Agent อ้างถึง "แผนกนั้น" ได้ถูกต้องโดยไม่ต้องระบุชื่อซ้ำ แสดงว่าจำ context ข้ามรอบได้จริง)
