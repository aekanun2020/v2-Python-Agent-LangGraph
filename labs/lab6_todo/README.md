# Lab 6 — Pure Python Planner + Dynamic Observation

Lab นี้ต่อยอดจาก `agent_todo.py` โดยตรงและ **ไม่ใช้ LangGraph**

## รันอย่างไร

รันจาก root ของ repository:

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph

# ของเดิม: TodoWrite
python labs/lab6_todo/agent_todo.py

# ของใหม่: Pure Python Planner + Dynamic Observation
python labs/lab6_todo/agent_planner.py \
  "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก"
```

โปรแกรมใช้ค่าต่อไปนี้จาก `.env`:

```dotenv
OPENROUTER_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen3.5-35b-a3b
MCP_SERVER_URL=https://your-mcp-server/mcp
```

## เรียนรู้อะไร

Agent loop ทั้งหมดอยู่ใน `agent_planner.py` ไฟล์เดียว:

```text
plan_write
    ↓
MCP action
    ↓
Python เรียก Observer LLM ด้วย fresh context
    ├─ evidence: accept / reject
    └─ next: continue / retry / query_more / replan / stop
                            ↓
ทุก step เสร็จ → Draft answer → Final Observer → Answer
```

`PlannerState` เก็บ goal, steps, revision และ accepted evidence ส่วน
`ObservationState` เก็บ:

- action สำเร็จหรือไม่
- result สนับสนุน active step หรือไม่
- evidence ครบหรือยัง
- claim ที่พิสูจน์ได้หรือขัดแย้ง
- requirement IDs ที่พิสูจน์แล้วหรือยังขาด
- evidence verdict, next action และเหตุผล

## อะไรเป็น Dynamic และอะไรเป็น Deterministic

LLM อ่านเป้าหมาย, active step, action และ tool result แล้วสร้าง semantic Observation
ตามประเภทของงาน จึงไม่ได้ผูกกับคำถาม HR ตาราง หรือ field ใดเป็นพิเศษ

Python runtime ไม่พยายามเข้าใจความหมายของโดเมน ทำหน้าที่เพียง:

- บังคับให้สร้างแผนก่อนเรียก MCP
- เรียก Observer อัตโนมัติหลัง MCP ทุกครั้งด้วย context แยกจาก executor
- ไม่ยอมรับ `accept` ถ้า action/result/evidence/requirement IDs ไม่ผ่านครบ
- downgrade verdict ที่ขัดกันเป็น `reject + query_more`
- สะสม partial evidence ภายใน active step เมื่อต้อง query เพิ่ม
- เปิด `plan_revise` เฉพาะเมื่อ Observer คืน `next_action=replan`
- ปฏิเสธ tool ที่ไม่ได้เปิดใน phase ปัจจุบัน
- ผูก accepted evidence กับ step ที่กำลังทำ
- เก็บ evidence ที่เสร็จแล้วไว้เมื่อแก้แผน
- ส่ง draft answer ให้ Final Observer ตรวจ accepted evidence ก่อนแสดง
- Final Observer รักษา canonical category/status/identifier จาก evidence โดยตรง
  อนุญาตการจัดรูปแบบและคำแปลที่แสดงค่าเดิมกำกับ แต่ไม่อนุญาตการเปลี่ยน label
  หรือสร้างข้อจำกัดเฉพาะข้อมูลที่ไม่มีหลักฐาน

นี่เป็น teaching implementation ที่ตั้งใจให้เล็กและอ่านง่าย ไม่ใช่ production
semantic assurance และยังไม่มี Domain Skill หรือ ontology เฉพาะทาง

## สถานะการทดลอง

เวอร์ชันนี้เป็น **experimental baseline** สำหรับให้ผู้เรียนสังเกตความไม่แน่นอนของ
LLM-based Observation ไม่ใช่เวอร์ชัน production:

- คำถามนับพนักงาน: live smoke test ผ่านทั้ง MCP, Observer และ Final Observer
- Workforce Matrix: ไปถึง 5/7 steps โดยไม่ปล่อยคำตอบผิด แต่ยังไม่จบภายในเวลา
- Observer จับ query ผิด step, SQL error และ requirement ที่ขาดได้
- ยังพบความเสี่ยงที่ Planner สร้าง requirement ไม่ละเอียดพอ เช่นนิยาม denominator
- Python guard ยังไม่ใช่ Domain Skill และไม่รับรอง semantic correctness ระดับ production

ควรรันคำถามเดิมซ้ำอย่างน้อย 5 รอบและเก็บ trace `[ACTION]`, `[RESULT]`,
`[OBSERVATION]`, `[ANSWER]` ก่อนตัดสินความเสถียร

## ทดสอบ runtime

```bash
python -m unittest -v tests.test_lab6_planner_runtime
```

ชุดทดสอบไม่เรียก API และตรวจ state transition หลัก 10 กรณี
