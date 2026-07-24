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
observe
    ├─ accept     → เก็บ evidence และไป step ถัดไป
    ├─ retry      → ทำ action เดิมใหม่
    ├─ query_more → หา evidence เพิ่ม
    ├─ replan     → plan_revise
    └─ stop       → หยุดพร้อมเหตุผล
```

`PlannerState` เก็บ goal, steps, revision และ accepted evidence ส่วน
`ObservationState` เก็บ:

- action สำเร็จหรือไม่
- result สนับสนุน active step หรือไม่
- evidence ครบหรือยัง
- claim ที่พิสูจน์ได้หรือขัดแย้ง
- decision และเหตุผล

## อะไรเป็น Dynamic และอะไรเป็น Deterministic

LLM อ่านเป้าหมาย, active step, action และ tool result แล้วสร้าง semantic Observation
ตามประเภทของงาน จึงไม่ได้ผูกกับคำถาม HR ตาราง หรือ field ใดเป็นพิเศษ

Python runtime ไม่พยายามเข้าใจความหมายของโดเมน ทำหน้าที่เพียง:

- บังคับให้สร้างแผนก่อนเรียก MCP
- บังคับให้ observe หลัง MCP ทุกครั้ง
- ไม่ยอมรับ `accept` ถ้า action/result/evidence ไม่ผ่านครบ
- ผูก accepted evidence กับ step ที่กำลังทำ
- เก็บ evidence ที่เสร็จแล้วไว้เมื่อแก้แผน
- ไม่ยอมให้ตอบก่อนแผนครบหรือถูกสั่ง stop

นี่เป็น teaching implementation ที่ตั้งใจให้เล็กและอ่านง่าย ไม่ใช่ production
semantic assurance และยังไม่มี Domain Skill หรือ ontology เฉพาะทาง

## สถานะการทดลอง

เวอร์ชันนี้เป็น **experimental baseline** สำหรับให้ผู้เรียนสังเกตความไม่แน่นอนของ
LLM-based Observation ไม่ใช่เวอร์ชัน production:

- live run 1: tool call จริง แต่ Observation accept หลักฐานผิดขั้น
- live run 2: recovery สำเร็จและตอบจำนวนจาก query evidence ถูกต้อง
- Python guard กันการข้ามลำดับและกัน `accept` ที่ boolean ไม่ครบได้
- Python guard ยังพิสูจน์ไม่ได้ว่าเหตุผลเชิงความหมายของ LLM ถูกต้อง

ควรรันคำถามเดิมซ้ำอย่างน้อย 5 รอบและเก็บ trace `[ACTION]`, `[RESULT]`,
`[OBSERVATION]`, `[ANSWER]` ก่อนตัดสินความเสถียร

## ทดสอบ runtime

```bash
python -m unittest -v tests.test_lab6_planner_runtime
```

ชุดทดสอบไม่เรียก API และตรวจ state transition หลัก 6 กรณี
