"""
Lab 9 — Containerized Agent + MCP Server (Capstone / Deploy)
============================================================
หลักสูตร Agentic AI Development with Python (หลักสูตรที่ 2) — Module 3.3

ห่อ LangGraph Agent ของ Lab 8 ให้เป็น **API Service** ด้วย FastAPI แล้ว deploy
เป็น Docker Container สำหรับ Production ตาม course outline:
  - POST /chat   : รับข้อความ -> agent ตอบ (จำ context ต่อ thread ด้วย Checkpointer)
  - GET  /health : health check สำหรับ Docker / load balancer
  - Error Handling + Retry : ต่อ MCP ล้มเหลวจะ retry แบบ exponential backoff
  - Logging      : log ทุก tool call + ผลลัพธ์ เพื่อ debug agent behavior

agent ตัวนี้ใช้ build_graph() ตัวเดียวกับ Lab 8 (reuse) — ชี้ไป MCP MSSQL จริง
ผ่านตัวแปร MCP_SERVER_URL (ตั้งใน .env / docker-compose) โดยไม่แก้โค้ด agent

รัน (local):  uvicorn labs.lab9_deploy.app:app --host 0.0.0.0 --port 8080
รัน (docker): docker compose up --build   (ดู labs/lab9_deploy/README.md)
"""
import os
import sys
import time
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# reuse องค์ประกอบ LangGraph จาก Lab 8 (State + Node + Edge + Checkpointer)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from labs.lab8_langgraph.agent_langgraph import build_graph, MCP_SERVER_URL  # noqa: E402

# ---- Logging : log ทุก tool call เพื่อ debug agent behavior (outline 3.3) ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lab9.agent")

# ---- ค่า config สำหรับ Retry Strategy ----
MCP_MAX_RETRIES = int(os.environ.get("MCP_MAX_RETRIES", "4"))
MCP_BACKOFF_BASE = float(os.environ.get("MCP_BACKOFF_BASE", "1.5"))

SYSTEM_PROMPT = (
    "คุณคือนักวิเคราะห์ข้อมูลของบริษัท ตอบคำถามเชิงธุรกิจจากฐานข้อมูล MS SQL Server "
    "ขั้นตอน: เรียก get_database_context ก่อนเสมอเพื่อดู schema แล้วจึงเขียน T-SQL "
    "ที่ถูกต้อง (ใช้ TOP ไม่ใช่ LIMIT) ส่งให้ execute_query_tool ตอบเป็นภาษาไทย "
    "พร้อมตารางสรุปและข้อสังเกตเชิงธุรกิจ"
)

# state ระดับ process: graph ที่ compile แล้ว (สร้างครั้งเดียวตอน startup)
_state = {"app": None}


async def build_graph_with_retry():
    """ต่อ MCP + ประกอบ graph พร้อม Retry แบบ exponential backoff (outline 3.3).

    ถ้า MCP Server ยังไม่พร้อม (เช่น container เพิ่งสตาร์ต) จะ retry หลายครั้ง
    ก่อนยอมแพ้ แทนที่จะ crash ทันที.
    """
    last_err = None
    for attempt in range(1, MCP_MAX_RETRIES + 1):
        try:
            log.info("กำลังต่อ MCP + ประกอบ graph (ครั้งที่ %d/%d) -> %s",
                     attempt, MCP_MAX_RETRIES, MCP_SERVER_URL)
            graph = await build_graph()
            log.info("ประกอบ agent graph สำเร็จ")
            return graph
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = MCP_BACKOFF_BASE ** attempt
            log.warning("ต่อ MCP ล้มเหลว (%s) — รอ %.1fs แล้ว retry", e, wait)
            if attempt < MCP_MAX_RETRIES:
                await asyncio.sleep(wait)
    raise RuntimeError(f"ต่อ MCP ไม่สำเร็จหลัง retry {MCP_MAX_RETRIES} ครั้ง: {last_err}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # สร้าง agent ครั้งเดียวตอน service เริ่มทำงาน
    _state["app"] = await build_graph_with_retry()
    yield
    _state["app"] = None


app = FastAPI(title="Lab 9 — Containerized LangGraph Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"          # แยก memory ต่อผู้ใช้/บทสนทนา


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    tool_calls: list[str]               # ชื่อ tool ที่ agent เรียก (เพื่อความโปร่งใส)
    elapsed_ms: int


@app.get("/health")
async def health():
    """health check — Docker ใช้เช็คว่า service พร้อมรับ request หรือยัง."""
    return {"status": "ok", "agent_ready": _state["app"] is not None,
            "mcp_server": MCP_SERVER_URL}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    graph = _state["app"]
    if graph is None:
        raise HTTPException(status_code=503, detail="agent ยังไม่พร้อม (MCP ยังต่อไม่ได้)")

    config = {"configurable": {"thread_id": req.thread_id}}
    started = time.time()
    log.info("[/chat thread=%s] user: %s", req.thread_id, req.message)

    # ข้อความที่ส่งเข้า graph: system (ครั้งแรกของ thread) + user
    snapshot = graph.get_state(config)
    msgs = [] if snapshot.values.get("messages") else [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.append({"role": "user", "content": req.message})

    try:
        result = await graph.ainvoke({"messages": msgs}, config=config)
    except Exception as e:  # noqa: BLE001 — Error Handling: ไม่ให้ service ล่ม
        log.exception("agent ทำงานผิดพลาด")
        raise HTTPException(status_code=502, detail=f"agent error: {e}") from e

    # ดึงชื่อ tool ที่ถูกเรียกจาก message history ของรอบนี้ + log ไว้ debug
    tool_calls = []
    for m in result["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                tool_calls.append(name)
    if tool_calls:
        log.info("[/chat thread=%s] tool calls: %s", req.thread_id, tool_calls)

    reply = result["messages"][-1].content
    elapsed = int((time.time() - started) * 1000)
    log.info("[/chat thread=%s] ตอบใน %dms", req.thread_id, elapsed)
    return ChatResponse(reply=reply, thread_id=req.thread_id,
                        tool_calls=tool_calls, elapsed_ms=elapsed)
