# v2-Python-Agent-LangGraph

## ผลไหนโดดเด่นที่สุด

**V2 เด่นที่สุดด้านผลลัพธ์ที่ทำซ้ำได้ใน bounded domain**: ชุด HR ผ่าน 10/10 คำถามและ 77/77 atomic items สองรอบ ส่วน Finance ผ่าน 10/10 คำถามและ 148/148 atomic items สองรอบ โดย HR ให้ answer hash เดียวกันและ Finance ไม่ regression หลังเพิ่ม HR Skill ผลนี้ชี้ว่า deterministic Skill contract ให้คำตอบเร็วและคงที่เมื่อคำถามอยู่ในขอบเขตที่ประกาศไว้ แต่ไม่ใช่หลักฐานว่าครอบคลุม paraphrase หรือคำถามนอก contract ทั้งหมด.



## สถานะปัจจุบัน: Pure Python Agent + bounded-domain Skills


งานพัฒนาล่าสุดอยู่ที่ **Lab 6** และไม่ใช้ LangGraph ใน critical path:


```text
Skill contract -> MCP evidence -> deterministic checks
               -> LLM semantic review เฉพาะกรณีเสี่ยง
               -> fail-closed Claim Gate -> Answer
```


แนวคิดสำคัญคือ Observation เพียงอย่างเดียวไม่รู้ความหมายทางธุรกิจ:


- **Skill** เก็บ semantics และ policy ของ bounded domain
- **Contract** นิยาม query, grain, field, label และ completion rule ที่ runtime ตรวจได้
- **Observation** ตรวจผล tool เทียบกับ state และ contract
- **Claim Gate** ปล่อยเฉพาะ claim ที่ accepted evidence รองรับ


Runtime core ค้นหา contracts จาก
`skills/*/references/answer_contracts.json`; ไฟล์ generic
`labs/lab6_todo/executable_metric_contracts.json` ไม่มี HR/Finance contract
เพื่อไม่ให้ core ผูกกับโดเมนใดโดเมนหนึ่ง


Skills ปัจจุบัน:


- [HR Analytics](skills/hr-analytics/SKILL.md)
- [Finance Analytics](skills/finance-analytics/SKILL.md)


### ผล controlled tests


| Suite | Repeated runs | Questions | Atomic items | Median |
|---|---:|---:|---:|---:|
| HR Skill | 2 | 10/10 | 77/77 | 0.706–0.710s |
| Finance Skill | 2 | 10/10 | 148/148 | 0.730–0.792s |


HR ทั้งสองรอบได้ answer hash เดียวกัน และ Finance non-regression หลังเพิ่ม HR
Skill ยังคง score และ answer hash เดิม คำถามที่ match contract ใช้เส้นทาง
`contract → MCP → deterministic emit` โดยไม่เรียก Agent/Observer LLM


ผลนี้รับรองเฉพาะ intent families และชุดข้อมูลที่ contracts ประกาศไว้
ไม่ใช่การรับรองคำถาม HR/Finance ทุกแบบหรือ production readiness


อ่านรายละเอียดและวิธีรันที่
[Lab 6 — current architecture](labs/lab6_todo/README.md),
[HR report](artifacts/hr_skill_run4_run5_report.md) และ
[Finance report](artifacts/finance_skill_run3_run4_report.md)


## Quick start สำหรับผู้เรียน


พัฒนาและทดสอบด้วย Python 3.11:


```bash
conda create -n agentic-ai python=3.11 -y
conda activate agentic-ai
pip install -r requirements.txt
cp .env.example .env
```


แก้ `.env` แล้วใส่ค่าของตนเอง ห้าม commit คีย์จริง:


```dotenv
OPENROUTER_API_KEY=ใส่คีย์ของผู้เรียน
OPENROUTER_MODEL=qwen/qwen3.5-35b-a3b
OBSERVER_MODEL=openai/gpt-oss-120b
MCP_SERVER_URL=https://your-mcp-server.example/mcp
```


รัน Pure Python Agent ปัจจุบันกับ MCP:


```bash
python labs/lab6_todo/agent_todo.py \
  "นับพนักงานที่ยังปฏิบัติงานแยกตามแผนก"
```


รัน automated tests:


```bash
python -m pytest tests --ignore=tests/test_lab8_planner.py -q
```


สถานะที่ merge เข้า `main`: `76 passed`


### จุดย้อนกลับ


- `archive/original-49f6f10` — original baseline
