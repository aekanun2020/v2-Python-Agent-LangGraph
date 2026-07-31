# v2-Python-Agent-LangGraph

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
- `milestone/skill-contracts-7e24c20` — HR/Finance Skill milestone

Tags ทั้งสองมีคำอธิบายและอยู่บน remote จึงทดลองย้อนหลังได้โดยไม่แก้ `main`

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** —
> เขียน Agent ด้วย Pure Python ทีละขั้น (Lab 1–7) แล้วเปรียบเทียบกับ LangGraph (Lab 8) ก่อน deploy เป็น API Service (Lab 9)

repo นี้เป็นชุดแล็บ **9 Lab** ที่ต่อเนื่องกัน สอนตั้งแต่เรียก LLM ครั้งแรก จนถึง deploy Agent เป็น API + Docker
ทุก Lab เชื่อมกับ **MCP MSSQL Server จริง** ของหลักสูตรที่ 1 เป็นแกนข้อมูลเดียวกัน

---

## เอกสารในโปรเจกต์นี้ต่างกันอย่างไร (อ่านไฟล์ไหนก่อน)

repo นี้มี README หลายระดับ แต่ละไฟล์ตอบคนละคำถาม — เลือกอ่านตามว่าคุณอยากรู้อะไร:

| ไฟล์ | ตอบคำถามว่า | เหมาะกับใคร |
| --- | --- | --- |
| **`README.md` (ไฟล์นี้)** | "โปรเจกต์นี้คืออะไร โครงสร้าง repo เป็นแบบไหน จะเริ่มอ่านที่ไหน" — ภาพรวมระดับ repo + จุดเริ่มต้น | คนเปิด repo ครั้งแรก |
| [`labs/README.md`](labs/README.md) | "หลักสูตรมีกี่ Lab เรียงยังไง **เส้นทางการเรียนรู้** ไล่จาก Lab 1 ถึง 9 อย่างไร ติดตั้ง/รันยังไง" — สารบัญ + เส้นเรื่องการสอน + setup/run | ผู้เรียน/ผู้สอนที่จะเดินตามหลักสูตร |
| `labs/labN_*/README.md` | "Lab นี้มีจุดประสงค์อะไร รันยังไง โค้ดจุดสำคัญอยู่ตรงไหน" — รายละเอียดเชิงลึกราย Lab | คนที่กำลังทำ Lab นั้นอยู่ |

> สรุปสั้น: **ไฟล์นี้ = ประตูหน้าระดับ repo** (โครงสร้าง + ชี้ทาง) · **`labs/README.md` = สารบัญ + เส้นเรื่องหลักสูตร + setup/run** · **README ราย Lab = คู่มือลงมือทำของแต่ละ Lab**

---

## เริ่มต้น (Clone Repository)

```bash
git clone https://github.com/aekanun2020/v2-Python-Agent-LangGraph.git
cd v2-Python-Agent-LangGraph
```

> **ขั้นตอนติดตั้งสภาพแวดล้อม (conda env + `.env` + dependencies) และวิธีรันแต่ละ Lab อยู่ใน [`labs/README.md`](labs/README.md)** — โดย Setup เต็มเป็นแหล่งเดียว (single source) อยู่ที่ [Lab 1](labs/lab1_setup/README.md) ทำครั้งเดียวก่อนเริ่มทุก Lab (พัฒนา/ทดสอบด้วย **Miniconda**, Python 3.11)

---

## โครงสร้างโปรเจกต์

```
Python-Agent-LangGraph/
├── README.md                   # ไฟล์นี้ — ภาพรวมระดับ repo + ชี้ทาง
├── labs/
│   ├── README.md               # สารบัญ Lab 1–9 + เส้นทางการเรียนรู้ + setup/run
│   ├── core/                   # โค้ดกลางที่ทุก Lab ใช้ร่วมกัน (config/llm/mcp_client/registry)
│   ├── lab1_setup/             # Lab 1: ตรวจสภาพแวดล้อม (เจ้าของ Setup เต็ม)
│   ├── lab2_llm/               # Lab 2: เรียก LLM + เทียบโมเดล
│   ├── lab3_agent_loop/        # Lab 3: agent loop แรก (Pure Python)
│   ├── lab4_mcp_agent/         # Lab 4: + MCP MSSQL จริง
│   ├── lab5_skills/            # Lab 5: + Skill routing (มีโฟลเดอร์ skills/)
│   ├── lab6_todo/              # Lab 6: Pure Python Observation/Evidence/Claim Gate
│   ├── lab7_memory/            # Lab 7: + Memory/Compaction/Note-taking
│   ├── lab8_langgraph/         # Lab 8: LangGraph Agent (pivot — เทียบ Pure Python)
│   └── lab9_deploy/            # Lab 9: ห่อ agent เป็น FastAPI API + Docker
├── skills/
│   ├── hr-analytics/           # HR semantics + executable answer contracts
│   └── finance-analytics/      # Finance semantics + executable answer contracts
├── docker-compose.yml          # Lab 9: service agent (ชี้ MCP MSSQL จริงผ่าน .env)
├── .dockerignore
├── discover_mssql.py           # ยูทิลิตี้ตรวจการเชื่อมต่อ + list tools/args schema
├── screenshots/labs/           # ภาพหน้าจอผลการรันทดสอบจริง (Lab 1–9)
│   ├── lab1_check_env.png ... lab7_memory.png
│   ├── lab8_01_mssql_discovery.png / lab8_02_agent_q1.png / lab8_03_agent_q2.png
│   ├── lab9_api_deploy.png
│   └── layer_coverage_matrix.png   # ตารางแมป layer สถาปัตยกรรม × Lab
├── requirements.txt
├── .env.example                # เทมเพลต env (ไม่มีคีย์จริง)
├── .gitignore
└── (README.md)
```

---

## สถาปัตยกรรม Agent: App → Agent → LLM + 8 Layers

เพื่อให้เข้าใจว่าแต่ละ Lab "กำลังสร้างชิ้นส่วนไหนของ Agent" repo นี้ยึดภาพสถาปัตยกรรมเดียวกันทั้งหลักสูตร
หัวใจคือ **LLM ทำหน้าที่ reasoning/decision** แต่สิ่งที่ทำให้มันเป็น "Agent" และประกอบขึ้นเป็น "App" จริง
คือ layer ที่ห่อรอบ LLM ต่างหาก

```
┌──────────────────────────────────────────────┐
│                    APP                         │
│  + UI, Auth, DB, Business Logic, Infra         │
│  ┌──────────────────────────────────────────┐ │
│  │              AGENT                        │ │
│  │  + Memory, Tools, Hooks, State            │ │
│  │   ┌────────────────────────────────┐      │ │
│  │   │           LLM                  │      │ │
│  │   │  (reasoning / decision)        │      │ │
│  │   └────────────────────────────────┘      │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

กางภาพข้างบนออกเป็น **8 layer** ของ Agent harness — แต่ละ layer มีคำอธิบายและ **แหล่งอ้างอิงต้นทาง** (origin paper / เอกสารทางการของบริษัทเทคโนโลยี) ที่เข้าดูได้จริง:

| # | Layer | ทำหน้าที่อะไร | แหล่งอ้างอิงต้นทาง (เปิดดูได้จริง) |
| :-: | --- | --- | --- |
| 1 | **Instructions / Bootstrap** | คำสั่งระบบ/บุคลิก/ขอบเขตที่โหลดตอนเริ่ม (เช่น `SOUL.md`, `AGENTS.md`) — กำหนดพฤติกรรมก่อนโมเดลเห็นงาน | Anthropic — [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) |
| 2 | **Memory** | ความจำสั้น/ยาว/procedural + compaction + note-taking | CoALA: [Cognitive Architectures for Language Agents](https://arxiv.org/abs/2309.02427) (Sumers et al., 2024) · Anthropic — [context engineering: compaction & note-taking](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) |
| 3 | **Tools + Skills** | ความสามารถภายนอก (MCP) + procedure ที่นำกลับมาใช้ซ้ำ (Skills) โหลดตามความจำเป็น | Anthropic — [Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) · [Agent Skills (Claude Docs)](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) |
| 4 | **Hooks** | callback ที่ดักจังหวะ lifecycle ของ agent (เช่น `PreToolUse`/`PostToolUse`/`Stop`) เพื่อ log/บล็อก/แทรก context แบบ deterministic | Anthropic — [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) |
| 5 | **Reasoning Loop (Agent Loop)** | วงคิด-ทำ-สังเกต (reason → act → observe → วน) แกนของ agent | ReAct: [Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) (Yao et al., ICLR 2023) |
| 6 | **Sandbox + Execution** | ที่รันโค้ด/คำสั่งที่โมเดลสร้างขึ้นแบบแยกขอบเขต (Docker/VM/Computer Use) | Anthropic — [Computer use tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool) · [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) |
| 7 | **Gateway + Scheduler** | ช่องทางเข้า-ออกประตูเดียว (HTTP/Telegram/Slack) + ตัวกระตุ้นตามเวลา/เหตุการณ์ (Cron/Webhook) | **Gateway:** AWS — [Amazon Bedrock AgentCore Gateway: single secure entry point for agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html) · วิชาการ: Nowaczyk — [Architectures for Building Agentic AI](https://arxiv.org/abs/2512.09458) (แนวคิด Execution Gateway) · **Scheduler:** Dust — [Introducing Triggers (Schedule + Webhook)](https://dust.tt/blog/introducing-triggers-your-agents-working-while-you-sleep) |
| 8 | **Safety Layer** | permission gating, audit trail, self-check + containment ที่ environment layer | Anthropic — [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude) |

> หมายเหตุ: CoALA (layer 2), ReAct (layer 5) และ Architectures for Building Agentic AI (layer 7) เป็น academic paper · MCP/Skills/Hooks/Computer Use/Containment เป็นเอกสารทางการของ Anthropic · AgentCore Gateway (layer 7) เป็นเอกสาร AWS · Triggers (layer 7) เป็นเอกสาร Dust

### แต่ละ Lab อยู่ตรงไหนของ 8 Layer นี้

สัญลักษณ์: ● = เป็นแกนหลักของ Lab นั้น · ◐ = แตะ/มีบางส่วน · (ว่าง) = ไม่มี

| Layer | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 |
| --- | :--: | :--: | :--: | :--: | :--: | :--: | :--: | :--: | :--: |
| 1. Instructions / Bootstrap | | | ◐ | ◐ | ● | ◐ | ◐ | ◐ | ◐ |
| 2. Memory | | | | | | | ● | ● | ◐ |
| 3. Tools + Skills | ◐ | | ◐ | ● | ● | ● | ● | ● | ● |
| 4. Hooks | | | | | | | ◐* | | ◐* |
| 5. Reasoning Loop (Agent Loop) | | | ● | ● | ● | ● | ● | ● | ◐ |
| 6. Sandbox + Execution | | | ◐* | | | | | | ◐* |
| 7. Gateway + Scheduler | | | | | | | | | ◐ |
| 8. Safety Layer | | | ◐* | | | ◐ | | | ◐ |

> `◐*` = มีร่องรอย/พฤติกรรมคล้าย แต่ยังไม่ใช่ระบบจริงตามนิยาม layer
> **สรุป coverage:** ครบจริง 4 layer (1, 2, 3, 5) · มีบางส่วนใน layer 7 (HTTP gateway) และ layer 8 (Lab 6 evidence admission/Claim Gate แต่ยังไม่มี permission/containment เต็มระบบ) · layer 4 Hooks และ layer 6 Sandbox/Execution ยังไม่ใช่ระบบเต็ม
> รายละเอียด gap + เหตุผลว่าทำไม layer 4/6/8 อยู่นอกขอบเขต `course2_outline-1.pdf` อธิบายไว้ที่ [Lab 9 — Layer Coverage & Gaps](labs/lab9_deploy/README.md) (มีภาพ matrix ประกอบ)

README ของแต่ละ Lab จะมีบรรทัด **"ตำแหน่งใน 8 Layer"** บอกว่า Lab นั้นสร้างชิ้นส่วนไหนของภาพนี้

### กรอบ "Agent Harness": repo นี้สร้างอะไร และอยู่ในขอบเขตไหน

**Agent harness** คือ runtime ที่ครอบ LLM ไว้ ทำหน้าที่วน loop เรียกโมเดล → รัน tool → ป้อนผลกลับ → จัดการ context จนงานเสร็จ — ตามที่ Anthropic นิยามว่า agent คือ "ระบบที่ LLM กำกับกระบวนการและการใช้ tool ของตัวเองแบบ dynamic โดยใช้ tool ตาม feedback จาก environment แบบวน loop" ([Anthropic — Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents))

**repo นี้ = harness ของ single-agent ที่ "ถอดประกอบให้เห็นทุกชิ้น"** — Lab 1–7 เขียนแต่ละชิ้นส่วนของ harness ด้วย Pure Python เอง (ผ่านโมดูลกลางใน `labs/core/`) ก่อนจะเห็นใน Lab 8 ว่า LangGraph ห่อชิ้นส่วนเหล่านั้นให้อย่างไร แล้ว Lab 9 นำไป deploy แต่ละชิ้นส่วน map ตรงกับ 8 layer ด้านบน:

| ชิ้นส่วน harness (เขียนเองใน repo) | ไฟล์/Lab ที่สร้าง | ตรงกับ Layer | LangGraph ห่อให้ (Lab 8) |
| --- | --- | :--: | --- |
| Reasoning loop (while: model→tool→observe) | `lab3_agent_loop` | **5** | `StateGraph` + conditional edge |
| Tool/skill registry (MCP→OpenAI schema) | `core/registry.py`, `lab4` | **3** | `ToolNode` + `MultiServerMCPClient` |
| Skill routing (Progressive Disclosure) | `lab5_skills` | **3 + 1** | conditional edge |
| Plan state (TodoWrite) | `lab6_todo` | **3 → 2** | state ใน `AgentState` |
| Evidence admission + Dynamic Observation | `lab6_todo/evidence_*`, `dynamic_observer.py` | **5 + 8** | ไม่มี counterpart ใน Lab 8 ตัวอย่าง |
| Domain Skill contracts + Claim Gate | `skills/*`, `lab6_todo/claim_gate.py` | **1 + 3 + 8** | ไม่มี counterpart ใน Lab 8 ตัวอย่าง |
| Memory + compaction + notes | `lab7_memory` | **2** | `MemorySaver` checkpointer |
| Prompt/instruction assembly | `core/llm.py`, system prompts | **1** | system message ใน state |
| API gateway (FastAPI `/chat`) | `lab9_deploy` | **7** | — (ชั้น deploy) |

**ขอบเขตที่ตั้งใจ: single-agent harness เท่านั้น** — ครบ 4 layer หลัก (1, 2, 3, 5) ตามตาราง coverage ด้านบน ตรงกับ `course2_outline-1.pdf` ทั้งหมด

**สิ่งที่อยู่เหนือกรอบนี้ (ไม่อยู่ใน repo): multi-agent orchestration** — เมื่อโจทย์ซับซ้อนเกินกว่า agent เดียว (context เต็ม, ต้อง parallelize, ต้องการ specialist) จึงขยับเป็นหลาย agent ที่มี supervisor route งานไป worker — LangGraph รองรับ pattern นี้อย่างเป็นทางการ (supervisor / network / hierarchical) ([LangGraph — Multi-Agent Systems](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)) และ Anthropic เรียก pattern คล้ายกันว่า orchestrator-workers ([Anthropic — Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)) ส่วนนี้คือ **module ถัดไป นอกขอบเขต outline ของ course2** — ปัจจุบัน repo จึงไม่มี layer สำหรับ sub-agent orchestration

> สรุป: repo นี้คือ harness ของ agent ตัวเดียวที่สร้างครบ layer 1/2/3/5 และนำไป deploy — multi-agent (supervisor + worker) คือชั้นที่ครอบขึ้นไป ซึ่งเป็นเนื้อหานอก outline ของ course2

---

## หมายเหตุด้านความปลอดภัย

- `.env` (คีย์จริง) ถูก `gitignore` ไว้ — repo นี้มีเฉพาะ `.env.example` ที่ไม่มีคีย์จริง
- ก่อน push ทุกครั้ง ตรวจสอบว่าไม่มีคีย์หลุดเข้าไปในไฟล์ที่ commit
