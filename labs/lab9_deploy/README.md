# Lab 9 — Containerized Agent + MCP Server (Capstone / Deploy)

หลักสูตร Agentic AI Development with Python — **Module 3.3**

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** ระดับ **App** — ห่อ Agent ของ Lab 8 ด้วย Layer 7 (Gateway: FastAPI `/chat`) + แตะ Layer 6/8 (Docker, retry/logging). ดูตารางเต็มที่หัวข้อ Layer Coverage & Gaps ด้านล่าง

ปิด loop ทั้งหลักสูตร: นำ **LangGraph Agent ของ Lab 8** มาห่อเป็น **API Service** ด้วย
FastAPI แล้ว deploy เป็น **Docker Container** สำหรับ Production พร้อม Error Handling,
Retry และ Logging

---

## จุดประสงค์การเรียนรู้

- ห่อ LangGraph Agent เป็น **HTTP API service** ด้วย FastAPI (`POST /chat`, `GET /health`) โดย reuse `build_graph()` จาก Lab 8 ไม่เขียน agent ซ้ำ
- ทำ **Error Handling** ที่ถูกต้อง: agent error → HTTP 502, agent ยังไม่พร้อม → HTTP 503 แทนที่จะ crash
- สร้าง **Retry Strategy** แบบ exponential backoff (`build_graph_with_retry()`) เพื่อรองรับ container startup race condition
- ติดตั้ง **Logging** ทุก request และทุก tool call เพื่อ debug agent behavior ใน production
- Deploy ด้วย **Docker Compose** — containerize agent service และชี้ MCP Server จริงผ่าน environment variable

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)
- ต้องมี `MCP_SERVER_URL` ใน `.env` ชี้ไปยัง MCP MSSQL Server จริง
- (สำหรับ Docker) ติดตั้ง Docker Desktop และ Docker Compose

---

## อธิบายจุดสำคัญของโค้ด

ไฟล์: `labs/lab9_deploy/app.py`

### `build_graph_with_retry()` — Retry Strategy (outline 3.3)

```python
for attempt in range(1, MCP_MAX_RETRIES + 1):
    try:
        graph = await build_graph()
        return graph
    except Exception as e:
        wait = MCP_BACKOFF_BASE ** attempt   # exponential backoff
        await asyncio.sleep(wait)
```

เรียก `build_graph()` ของ Lab 8 ซ้ำด้วย exponential backoff (`MCP_BACKOFF_BASE=1.5`) กัน container เพิ่งสตาร์ตแล้ว MCP Server ยังไม่พร้อม ควบคุมได้ผ่าน env var `MCP_MAX_RETRIES` และ `MCP_BACKOFF_BASE`

### `lifespan(_: FastAPI)` — สร้าง agent ครั้งเดียวตอน startup

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    _state["app"] = await build_graph_with_retry()
    yield
    _state["app"] = None
```

`_state["app"]` เก็บ compiled graph ไว้ระดับ process — ทุก request ใช้ instance เดิมไม่ต้องสร้างใหม่

### `GET /health` — health check

```python
return {"status": "ok", "agent_ready": _state["app"] is not None, "mcp_server": MCP_SERVER_URL}
```

Docker healthcheck เรียก endpoint นี้ตรวจว่า agent พร้อมรับ request แล้วหรือยัง

### `POST /chat` — Error Handling + Logging

```python
try:
    result = await graph.ainvoke({"messages": msgs}, config=config)
except Exception as e:
    raise HTTPException(status_code=502, detail=f"agent error: {e}")  # ไม่ให้ service ล่ม

if tool_calls:
    log.info("[/chat thread=%s] tool calls: %s", req.thread_id, tool_calls)  # Logging
```

`ChatRequest` รับ `thread_id` เพื่อแยก Checkpointer memory ต่อผู้ใช้ ส่ง thread_id เดิมซ้ำ = agent จำ context ต่อเนื่อง

> จุดที่ควรเปิดอ่าน: บล็อก `for m in result["messages"]: for tc in getattr(m, "tool_calls", None) or []:` — วิธีดึงชื่อ tool ที่ถูกเรียกจาก LangGraph message history

---

## ไฟล์ใน Lab นี้

| ไฟล์ | หน้าที่ |
|------|---------|
| `app.py` | FastAPI service — `POST /chat`, `GET /health` (reuse `build_graph()` ของ Lab 8) |
| `requirements.txt` | dependencies ของ image (LangGraph + FastAPI/uvicorn) |
| `Dockerfile` | สร้าง image ของ agent (python:3.11-slim + uvicorn + healthcheck) |
| `../../docker-compose.yml` | service `agent` (อยู่ที่ root ของ repo) |
| `../../.dockerignore` | ตัด `.env`/`.git`/screenshots ออกจาก build context |

> ออกแบบให้ `app.py` **import `build_graph()` จาก Lab 8 โดยตรง** — agent ตัวเดียวกัน
> ไม่เขียนซ้ำ ทำให้ Lab 8 → Lab 9 ต่อเนื่องกันจริง

---

## API

### `GET /health`
```json
{"status": "ok", "agent_ready": true, "mcp_server": "https://.../mcp"}
```

### `POST /chat`
Request:
```json
{"message": "แต่ละแผนกมีพนักงานกี่คน", "thread_id": "demo-1"}
```
Response:
```json
{
  "reply": "...คำตอบภาษาไทย + ตารางสรุป...",
  "thread_id": "demo-1",
  "tool_calls": ["get_database_context", "execute_query_tool"],
  "elapsed_ms": 26194
}
```
ส่ง `thread_id` เดิมซ้ำ = คุยต่อเนื่องในบทสนทนาเดียวกัน (Checkpointer จำ context ให้)

---

## คุณสมบัติตาม outline 3.3

- **API Service** — FastAPI + uvicorn ห่อ agent เป็น HTTP endpoint
- **Error Handling** — จับ exception ตอน agent ทำงาน คืน HTTP 502 แทนการ crash;
  ถ้า agent ยังไม่พร้อม (MCP ต่อไม่ได้) คืน 503
- **Retry Strategy** — ตอน startup ต่อ MCP ด้วย **exponential backoff**
  (`MCP_MAX_RETRIES`, `MCP_BACKOFF_BASE`) กัน container เพิ่งสตาร์ตแล้ว MCP ยังไม่พร้อม
- **Logging** — log ทุก request + **ทุก tool call ที่ agent เรียก** + เวลาที่ใช้
  เพื่อ debug agent behavior

---

## วิธีรัน

### 1) รันแบบ local (ทดสอบเร็ว)
```bash
conda activate agentic-ai
pip install -r labs/lab9_deploy/requirements.txt
# รันจาก root ของ repo (ให้ import labs.* ได้)
uvicorn labs.lab9_deploy.app:app --host 0.0.0.0 --port 8080
```

### 2) รันด้วย Docker Compose (production)
```bash
# ตั้งค่า .env ให้มี OPENROUTER_API_KEY และ MCP_SERVER_URL (MCP MSSQL จริง)
docker compose up --build
```

### ทดสอบ
```bash
curl -s localhost:8080/health

curl -s -X POST localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"แต่ละแผนกมีพนักงานที่ยังปฏิบัติงานกี่คน","thread_id":"demo-1"}'

# ถามต่อใน thread เดิม -> agent จำ context (Checkpointer)
curl -s -X POST localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"แล้วแผนกที่มากที่สุดนั้น มีใครบ้าง","thread_id":"demo-1"}'
```

ภาพผลการรันจริง: `screenshots/labs/lab9_api_deploy.png`

---

## หมายเหตุขอบเขต (ตามกติกาของ Space — ขอแจ้ง)

course outline ข้อ 3.3 กำหนดให้ deploy ด้วย **Docker Compose + Agent + MCP Servers**
(พร้อม Error Handling / Retry / Logging) โดยไม่ได้ล็อกว่าต้องใช้ MCP ตัวไหน — ผู้สอน
กำหนดให้ยึด **MCP MSSQL จริงตัวเดียว** (ตาม endpoint ที่ส่งให้ และสอดคล้องกับ Lab 4–8)
ดังนั้น `docker-compose.yml` จึงมี **service `agent` ตัวเดียว** ที่ชี้ไป MCP MSSQL จริง
ภายนอกผ่าน `MCP_SERVER_URL`

หากภายหลังต้องการรัน MCP MSSQL server ใน compose ด้วย ก็เพิ่ม service `mssql-mcp`
เข้า network เดียวกัน แล้วเปลี่ยนเป็น `MCP_SERVER_URL=http://mssql-mcp:9000/mcp` —
โครงสร้าง compose รองรับไว้แล้ว (อยู่ในขอบเขต outline ไม่ได้ลดความสามารถของ Lab)

---

## Layer Coverage & Gaps (บันทึกไว้ตามขอบเขต)

สถาปัตยกรรม agent มี 8 layer ตามแนวคิดทั่วไป — ตารางข้างล่างแมป Lab 1–9
ของหลักสูตรนี้เข้ากับแต่ละ layer เพื่อให้เห็นชัดว่าหลักสูตรครอบอะไร และ **ยังขาดอะไร**

สัญลักษณ์: ● = เป็นแกนหลักของ Lab นั้น · ◐ = แตะ/มีบางส่วน · (ว่าง) = ไม่มี

| Layer | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 1. Instructions / Bootstrap | | | ◐ | ◐ | ● | ◐ | ◐ | ◐ | ◐ |
| 2. Memory | | | | | | | ● | ● | ◐ |
| 3. Tools + Skills | ◐ | | ◐ | ● | ● | ● | ● | ● | ● |
| 4. Hooks | | | | | | | ◐* | | ◐* |
| 5. Reasoning Loop | | | ● | ● | ● | ● | ● | ● | ◐ |
| 6. Sandbox + Execution | | | ◐* | | | | | | ◐* |
| 7. Gateway + Scheduler | | | | | | | | | ◐ |
| 8. Safety Layer | | | ◐* | | | | | | ◐ |
| (พื้นฐาน) Env check | ● | | | | | | | | |
| (พื้นฐาน) Model select | | ● | | | | | | | |

### สรุปสถานะ layer
- ✅ **ครบจริง 4 layer:** 1 (Instructions), 2 (Memory), 3 (Tools+Skills), 5 (Reasoning Loop)
- 🟡 **มีบางส่วน 1 layer:** 7 (Gateway) — มี HTTP gateway (`/chat`, `/health`) แต่ยังไม่มี Telegram/Slack และไม่มี Scheduler/Cron
- ❌ **ยังไม่มีจริง 3 layer:** 4 (Hooks), 6 (Sandbox/Execution ตามนิยาม), 8 (Safety)

### Gap ที่เหลือ (`◐*` = มีร่องรอยแต่ไม่ใช่ระบบจริง)
- **Layer 4 — Hooks:** L7 (inject note) / L9 (log tool calls) เป็นพฤติกรรมแบบ hook ที่ hardcode ไว้ในลูป
  ยังไม่มี hook system ที่ถอด/เสียบได้ (pre/post tool-call, pre/post-model, interrupt)
- **Layer 6 — Sandbox/Execution:** L9 Docker = containerize ตัว agent service เองเพื่อ deploy
  (ไม่ใช่ sandbox ที่ agent รันโค้ดที่ LLM สร้างขึ้น); L3 `eval()` = เดโมเครื่องคิดเลข
  — ไม่ใช่ code-execution sandbox จริง
- **Layer 8 — Safety:** L9 มีแค่ retry/backoff + error handling + logging (robustness)
  ยังไม่มี permission gating, audit trail, หรือ self-check ก่อนรัน query

### ทำไม Lab 9 ถึง "แตะหลาย layer แต่ไม่เต็ม"
Lab 9 เป็น **Capstone / Deploy** — หน้าที่คือ "รวมร่าง Lab ก่อนหน้าแล้ว deploy"
จึงกว้างหลาย layer โดยธรรมชาติ ส่วนความลึกของแต่ละ layer อยู่ใน Lab เฉพาะทาง
(Memory → L7, Skills → L5, Loop → L3/L8). ส่วน layer 4/6/8 ที่ยังไม่เต็ม
เป็นเพราะ **อยู่นอกขอบเขต `course2_outline-1.pdf`** (outline ข้อ 3.3 ระบุแค่ Docker Compose +
Agent + MCP + Error Handling + Retry + Logging) — ไม่ใช่ข้อบกพร่องของ Lab

### ถ้าจะเติม layer ที่ขาดให้เต็ม (เกินขอบเขต — ต้องอนุมัติตามกติกา Space)
แนวทางที่เป็นไปได้ (ไว้เป็น advanced topics นอกหลักสูตร):
- Lab 10 — Hooks system (layer 4): pre/post tool-call, interrupt, ปลั๊กอินถอด/เสียบได้
- Lab 11 — Safety layer (layer 8): permission gating (บล็อก DELETE/DROP), audit log, self-check
- Lab 12 — Gateway/Scheduler (layer 7 เต็ม): Telegram/Slack adapter + Cron
