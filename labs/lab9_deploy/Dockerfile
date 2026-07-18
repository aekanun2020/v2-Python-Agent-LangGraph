# Lab 9 — Dockerfile ของ Agent API Service (LangGraph + MCP)
# หลักสูตร Agentic AI Development with Python — Module 3.3
FROM python:3.11-slim

WORKDIR /app

# ติดตั้ง dependencies ก่อน (cache layer) — ใช้ requirements ของ Lab 9
COPY labs/lab9_deploy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# คัดลอกเฉพาะโค้ดที่ agent ต้องใช้: core + lab8 (reuse) + lab9 (API)
COPY labs/__init__.py            /app/labs/__init__.py
COPY labs/core                   /app/labs/core
COPY labs/lab8_langgraph         /app/labs/lab8_langgraph
COPY labs/lab9_deploy            /app/labs/lab9_deploy

EXPOSE 8080

# health check ให้ Docker รู้ว่า service พร้อมหรือยัง
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

# รัน FastAPI ด้วย uvicorn
CMD ["uvicorn", "labs.lab9_deploy.app:app", "--host", "0.0.0.0", "--port", "8080"]
