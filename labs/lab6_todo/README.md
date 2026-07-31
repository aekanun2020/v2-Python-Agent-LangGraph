# Lab 6 — Pure Python Agent: Observation, Evidence และ Skill Contracts

Lab นี้เริ่มจาก TodoWrite แบบ Pure Python แล้วพัฒนาเป็น agent runtime ที่แยก
การวางแผน การเรียก MCP การรับหลักฐาน และการตรวจคำตอบออกจากกันอย่างชัดเจน
โดยไม่ใช้ LangGraph

เป้าหมายปัจจุบันไม่ใช่ทำให้ LLM “ตอบเก่งทุกเรื่อง” แต่ทำให้คำตอบใน bounded
domain ตรวจสอบย้อนกลับได้ และไม่ปล่อย claim ที่เกินหลักฐาน

## สิ่งที่ผู้เรียนจะเห็น

- `TodoState` เก็บแผนงานหลายขั้นในหน่วยความจำ
- `ContextState` เก็บ goal, phase, action/error signatures และ budgets
- `EvidenceState` เก็บผล MCP ที่ผ่านการยอมรับพร้อม provenance
- Dynamic Observation ตรวจผลหลัง tool call และเลือก
  `accept / query_more / replan / stop`
- deterministic checks ตรวจ error, query role, grain, field, label และความครบ
- LLM Semantic Observer ถูกเรียกเฉพาะเส้นทางทั่วไปที่มีความเสี่ยงด้านความหมาย
- Claim Gate ประกอบคำตอบแบบ fail-closed จาก claim ที่ตรวจแล้ว
- Skill contracts ให้ semantics และ acceptance criteria ของ bounded domain

## สถาปัตยกรรมปัจจุบัน

```text
User question
      |
      v
Skill contract selector -------------------- no match
      |                                        |
    match                                      v
      |                                Pure Python Agent loop
      v                                Plan -> MCP -> Observe
MCP query declared by contract                |
      |                                        v
      v                              deterministic checks
evidence completeness                         |
      |                               semantic risk?
      v                                  |          |
deterministic answer emit                 no        yes
                                             |       |
                                             |       v
                                             |   LLM Observer
                                             |       |
                                             +-- Claim Gate
                                                     |
                                                     v
                                                   Answer
```

เส้นทางที่ match Skill contract จะไม่เรียก Agent หรือ Observer LLM:

```text
contract -> MCP -> completeness check -> deterministic emit
```

คำถามที่ไม่ match contract จะใช้ agent loop ทั่วไปและ semantic-risk routing
ตามเดิม

## Contract และ Skill คืออะไร

Contract คือ executable business specification ซึ่งกำหนด:

- intent family และคำที่ใช้เลือก contract
- MCP query roles และ read-only query template
- table, filter, grain และ field ที่ต้องพบ
- output columns, canonical labels และ arithmetic ที่อนุญาต
- terminal verdict, grounded notes และข้อห้ามทางความหมาย

Observation เป็นกลไกทั่วไป แต่ไม่รู้ business semantics ด้วยตัวเอง จึงต้องรับ
acceptance criteria จาก Skill:

```text
Skill          = ความรู้และข้อกำหนดของ bounded domain
Contract       = นิยามที่ runtime ตรวจได้ว่า evidence ถูกและครบหรือไม่
Observation    = ตัดสินผล tool เทียบกับ contract และ state ปัจจุบัน
Claim Gate     = อนุญาตเฉพาะ claim ที่พิสูจน์แล้วออกสู่คำตอบ
```

## ตำแหน่งของ contracts

Generic runtime ค้นหาไฟล์:

```text
skills/*/references/answer_contracts.json
```

Skill ที่มีอยู่:

- [`skills/hr-analytics`](../../skills/hr-analytics/SKILL.md)
- [`skills/finance-analytics`](../../skills/finance-analytics/SKILL.md)

ไฟล์ [`executable_metric_contracts.json`](executable_metric_contracts.json)
ตั้งใจให้ไม่มี domain contract (`"contracts": []`) เพื่อยืนยันว่า runtime core
ไม่ผูกกับ HR หรือ Finance

## วิธีรัน

รันจาก root repository เสมอ:

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph

python labs/lab6_todo/agent_todo.py \
  "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก"
```

ตัวอย่างคำถาม Finance:

```bash
python labs/lab6_todo/agent_todo.py \
  "สรุปจำนวนรายการและยอด loan_amnt กับ funded_amnt รวมทั้งพอร์ต"
```

ถ้าไม่ส่งคำถาม โปรแกรมจะเปิด interactive prompt:

```bash
python labs/lab6_todo/agent_todo.py
```

ตัวเลือกสำหรับการทดลองเปรียบเทียบ:

```bash
# ปิด LLM Final Semantic Observer
python labs/lab6_todo/agent_todo.py --semantic-observer off "คำถาม"

# ปิด Dynamic Observation/Claim Ledger เพื่อดู baseline path
python labs/lab6_todo/agent_todo.py --dynamic-observer off "คำถาม"

# กำหนด hard wall-clock deadline
python labs/lab6_todo/agent_todo.py --max-run-seconds 120 "คำถาม"
```

## Environment

คัดลอก `.env.example` เป็น `.env` และใส่ค่าจริง:

```dotenv
OPENROUTER_API_KEY=your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen3.5-35b-a3b
OBSERVER_MODEL=openai/gpt-oss-120b
MCP_SERVER_URL=https://your-mcp-server.example/mcp
```

`OPENROUTER_MODEL` ใช้กับ planning, tool selection และคำตอบบน general path
ส่วน `OBSERVER_MODEL` ใช้ตรวจความหมายเมื่อ risk router เห็นว่าจำเป็น หากไม่ตั้ง
`OBSERVER_MODEL` ระบบจะใช้ `OPENROUTER_MODEL`

คำถามที่ match contract ไม่จำเป็นต้องเรียกสองโมเดลนี้ แต่โปรแกรมยังต้องมี
OpenRouter key สำหรับ general fallback path

## ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| `agent_todo.py` | entry point, TodoWrite, agent loop และ contract fast path |
| `context_state.py` | control state และ runtime budgets |
| `evidence_state.py` | evidence/observation types และ provenance |
| `evidence_contract.py` | ค้นหา Skill contracts, ตรวจ evidence และประกอบ contract claims |
| `dynamic_observer.py` | post-tool observation และ claim ledger |
| `risk_router.py` | deterministic observation และ semantic-risk routing |
| `semantic_observer.py` | LLM observer สำหรับความเสี่ยงด้านความหมาย |
| `claim_gate.py` | verify-then-emit แบบ fail-closed |
| `phase2_runtime.py` | MCP/LLM budgets และ hard deadline |

## ผลที่พิสูจน์แล้ว

### HR Skill

| Run | Questions | Atomic items | Median |
|---|---:|---:|---:|
| HR run 4 | 10/10 | 77/77 | 0.710s |
| HR run 5 | 10/10 | 77/77 | 0.706s |

สองรอบได้ answer hash เดียวกัน:
`af20423f90d8b38b2469691032831cf67efa7f2da81868056ed391b015ed51f9`

ดู [HR report](../../artifacts/hr_skill_run4_run5_report.md)

### Finance Skill

| Run | Questions | Atomic items | Median |
|---|---:|---:|---:|
| ก่อน Finance Skill | 2/10 | — | 97.591s |
| Finance run 3 | 10/10 | 148/148 | 0.792s |
| Finance run 4 | 10/10 | 148/148 | 0.730s |

หลังเพิ่ม HR Skill แล้ว Finance non-regression ยังคง `10/10`, `148/148`
และได้ answer hash เดิม

ดู [Finance report](../../artifacts/finance_skill_run3_run4_report.md)

## สิ่งที่ผลทดลองยังไม่พิสูจน์

- ไม่ได้รับรองคำถาม HR/Finance ทุกแบบ
- ไม่ได้รับรองคำถามที่อยู่นอก intent families ใน contracts
- keyword contract selection ยังไม่ใช่ semantic router ทั่วไป
- ไม่ได้รับรอง causal inference หรือการตัดสินใจรายบุคคล
- การผ่าน frozen suite ไม่เท่ากับ production readiness
- general fallback path ยังมีความไม่แน่นอนจาก LLM และควรประเมินแยก

หลักที่ใช้ตีความผลคือ:

> Observation อย่างเดียวจำเป็นแต่ไม่เพียงพอ
> bounded-domain Skill ให้ semantics, contract ให้เกณฑ์ที่ตรวจได้ และ Claim
> Gate บังคับไม่ให้คำตอบเกิน accepted evidence

## ทดสอบ

```bash
python -m pytest tests --ignore=tests/test_lab8_planner.py -q
```

สถานะที่ merge เข้า `main`: `76 passed`

ไฟล์ทดสอบสำคัญ:

- `tests/test_lab6_phase2b.py`
- `tests/test_lab6_atomic_grader.py`
- `tests/test_hr_skill_contracts.py`
- `tests/test_finance_skill_contracts.py`

## ประวัติและจุดย้อนกลับ

เอกสารผลทดลอง Phase 1–2D เดิมยังอยู่ใน `artifacts/` เพื่อให้ตรวจย้อนกลับได้
แต่ไม่ใช่คำอธิบาย runtime ปัจจุบัน

- `archive/original-49f6f10` — original baseline ก่อนงาน Observation/Evidence/Skill
- `milestone/skill-contracts-7e24c20` — HR/Finance Skill contracts ที่ merge เข้า `main`

ทดลองเปิด baseline โดยไม่แก้ `main`:

```bash
git switch -c investigate-original archive/original-49f6f10
```

กลับสู่ปัจจุบัน:

```bash
git switch main
```
