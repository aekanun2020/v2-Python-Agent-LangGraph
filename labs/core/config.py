"""core.config — โหลดค่าตั้งจาก .env และรวมไว้ที่เดียว (เริ่มใช้ตั้งแต่ Lab 1)

ทุก Lab import ค่าจากที่นี่ เพื่อไม่ให้กระจัดกระจาย และเปลี่ยน MCP server / โมเดล
ได้จากจุดเดียว (แก้ .env อย่างเดียว)
"""
import os
from dotenv import load_dotenv

# โหลด .env จาก root ของโปรเจกต์ (หาไฟล์ขึ้นไปจากตำแหน่งนี้)
load_dotenv()

# ---- OpenRouter (LLM provider แบบ thin client — แนวคิดเดียวกับหลักสูตรที่ 1) ----
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")

# ---- MCP MSSQL Server จริงของหลักสูตรที่ 1 (Streamable HTTP) ----
# ค่าเริ่มต้นชี้ localhost:9000 — ตั้งใน .env ให้เป็น URL ngrok ถ้า expose ออกมา
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp")


def require_api_key() -> str:
    """คืน OpenRouter API key พร้อมข้อความช่วยเหลือถ้ายังไม่ได้ตั้ง"""
    if not OPENROUTER_API_KEY:
        raise SystemExit(
            "ยังไม่ได้ตั้ง OPENROUTER_API_KEY — คัดลอก .env.example เป็น .env "
            "แล้วใส่คีย์จาก https://openrouter.ai/keys"
        )
    return OPENROUTER_API_KEY
