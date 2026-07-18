# Lab 1 — ติดตั้งและตรวจสอบสภาพแวดล้อม

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 1.2

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** ฐานก่อน Layer 3 (Tools+Skills) — ตรวจว่า LLM (แกนกลาง) + ช่องต่อ MCP tools พร้อมใช้ ก่อนจะเริ่มประกอบ layer อื่น

**Lab นี้เป็นเจ้าของ Setup สภาพแวดล้อมเต็มรูปแบบ** — Lab 2–9 ทุกตัวต้องผ่านขั้นตอนนี้ก่อน

---

## จุดประสงค์การเรียนรู้

- ตั้งค่า Python environment ด้วย Miniconda (conda env `agentic-ai`, Python 3.11)
- เชื่อมต่อ LLM API ผ่าน **OpenRouter** โดยใช้ OpenAI SDK + `base_url` (thin client)
- ตรวจสอบว่า MCP MSSQL Server จากหลักสูตรที่ 1 รันอยู่และค้นพบ tools ได้ถูกต้อง
- ใช้ `check_env.py` เป็น precondition gate ก่อนเข้าสู่ Lab ถัดไป

---

## ขั้นตอน Setup สภาพแวดล้อม (ทำครั้งเดียว — ใช้ร่วมกันทุก Lab)

### 1) Clone repository

```bash
git clone https://github.com/aekanun2020/v2-Python-Agent-LangGraph.git
cd v2-Python-Agent-LangGraph
```

### 2) สร้างและเปิดใช้งาน conda environment

> ต้องติดตั้ง [Miniconda](https://docs.conda.io/en/latest/miniconda.html) ก่อน

```bash
# สร้าง env ชื่อ agentic-ai ด้วย Python 3.11
conda create -n agentic-ai python=3.11 -y

# เปิดใช้งาน
conda activate agentic-ai
```

### 3) ติดตั้ง dependencies

```bash
pip install -r requirements.txt
```

### 4) ตั้งค่า environment variables

```bash
# คัดลอกเทมเพลต
cp .env.example .env
```

จากนั้นแก้ไขไฟล์ `.env` ให้มีค่าดังนี้:

| ตัวแปร | ค่า | หมายเหตุ |
|--------|-----|----------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | ขอคีย์ได้ที่ https://openrouter.ai/keys |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | endpoint มาตรฐาน OpenRouter |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.6` | โมเดลที่ทดสอบแล้ว |
| `MCP_SERVER_URL` | `https://<subdomain>.ngrok-free.app/mcp` | URL ของ MCP MSSQL Server จริง (expose ผ่าน ngrok) |

> ⚠️ ไฟล์ `.env` ถูก `.gitignore` ไว้แล้ว — **ห้าม commit คีย์จริงขึ้น repo เด็ดขาด**

---

## วิธีรัน Lab 1

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # root ของ repo

python labs/lab1_setup/check_env.py
```

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab1_setup/check_env.py`

### `check_llm()` — ตรวจ OpenRouter (LLM)

เรียก `llm.chat()` ด้วย prompt สั้น (`"ตอบสั้น ๆ คำเดียวว่า 'พร้อม'"`) แล้วอ่าน `resp.choices[0].message.content` และแสดงชื่อโมเดลจาก `config.OPENROUTER_MODEL` เพื่อยืนยันว่า API key ถูกต้องและเชื่อมต่อ OpenRouter ได้จริง

### `check_mcp()` — ตรวจ MCP MSSQL Server

สร้าง `MCPClient(config.MCP_SERVER_URL)` แล้วเรียก:
1. `client.initialize()` — เพื่อ handshake และดึง `serverInfo`
2. `client.list_tools()` — ค้นพบ tools ทั้งหมดจาก MCP Server
3. ตรวจว่ามี `get_database_context` และ `execute_query_tool` อยู่ใน tools (precondition ของ Lab 4–8)

### `main()` — gate ก่อนไป Lab 2

รวม `ok_llm and ok_mcp` แล้ว return code 0 (ผ่าน) หรือ 1 (ยังไม่ผ่าน) — ถ้าทั้งสองผ่านถึงไป Lab 2 ได้

> จุดที่ควรเปิดอ่าน: บล็อก `need = {"get_database_context", "execute_query_tool"}` ใน `check_mcp()` — แสดงว่า Lab นี้ตรวจเฉพาะ tools ที่เป็น core ของทุก Lab ถัดไป

---

## ผลลัพธ์ที่คาดหวัง

รันสำเร็จจะเห็นผลลัพธ์ประมาณนี้:

```
============================================================
Lab 1 — ตรวจสอบสภาพแวดล้อมการพัฒนา (หลักสูตรที่ 2)
============================================================
[1/2] ตรวจ OpenRouter (LLM) ...
      โมเดล anthropic/claude-sonnet-4.6 ตอบ: 'พร้อม'
[2/2] ตรวจ MCP MSSQL Server ...
      เชื่อม https://...ngrok-free.app/mcp
      serverInfo: mssql-streamable-http-server — ค้นพบ 5 tools
      tools: ['get_database_context', 'execute_query_tool', ...]
------------------------------------------------------------
✅ environment พร้อม — ไปต่อ Lab 2 ได้เลย
```

ดู screenshot ตัวอย่าง: `../../screenshots/labs/lab1_check_env.png`
