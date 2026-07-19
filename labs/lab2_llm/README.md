# Lab 2 — เรียกใช้ LLM API ครั้งแรกและเปรียบเทียบโมเดล

> หลักสูตร **Agentic AI Development with Python (หลักสูตรที่ 2)** — Module 1.2

> **ตำแหน่งใน [8 Layer ของ repo](../../README.md#สถาปัตยกรรม-agent-app--agent--llm--8-layers):** แกนกลางสุด คือตัว **LLM (reasoning/decision)** เอง — เรียกโมเดลตรงๆ ยังไม่มี layer ห่อ (ยังไม่ใช่ agent loop)

---

## จุดประสงค์การเรียนรู้

- เข้าใจโครงสร้าง **messages** และ **role** (system / user / assistant) ที่ใช้กับ LLM API
- อ่านและตีความ **token usage** (prompt / completion / total) เพื่อบริหารต้นทุนและ context window
- เปรียบเทียบผลลัพธ์และเวลาตอบสนองของหลายโมเดลบน OpenRouter เพื่อเลือกโมเดลให้เหมาะกับงาน

---

## สิ่งที่ต้องเตรียมก่อน (Prerequisites)

- ทำ Setup สภาพแวดล้อมใน [Lab 1](../lab1_setup/README.md) ให้เสร็จก่อน (conda env `agentic-ai` + `.env`)

---

## วิธีรัน

```bash
conda activate agentic-ai
cd v2-Python-Agent-LangGraph   # รันจาก root repo (เพราะ import labs.core.*)

# ไฟล์ที่ 1: เรียก LLM ครั้งแรก + ดู token usage
python labs/lab2_llm/first_llm.py "อธิบาย Agent Loop ใน 2 ประโยค"

# ไฟล์ที่ 2: เปรียบเทียบหลายโมเดลด้วยคำถามเดียวกัน
python labs/lab2_llm/compare_models.py
```

---

## `llm` กับ `config` มาจากไหน?

หลายคนสงสัยว่า `llm.chat(...)` ที่เรียกใน Lab นี้ ตัว `llm` เป็น object ที่ได้มาอย่างไร
— คำตอบคือ **`llm` ไม่ใช่ instance ของคลาส แต่เป็น "module"** ที่ import มาจาก `labs/core/`

บรรทัดต้นไฟล์ของ Lab 2 ทำสองอย่าง:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # (1) เพิ่ม root repo เข้า import path

from labs.core import config, llm   # (2) import โมดูลกลางที่ใช้ร่วมทุก Lab
```

- **(1)** `sys.path.insert(...)` ทำให้ Python มองเห็นแพ็กเกจ `labs.*` แม้รันสคริปต์ตรงๆ จาก root
  (เลยรันได้ทั้ง `python labs/lab2_llm/first_llm.py`)
- **(2)** `llm` คือไฟล์ `labs/core/llm.py` ทั้งไฟล์ — เรียก `llm.chat(...)` ก็คือเรียก **ฟังก์ชัน** `chat()` ในโมดูลนั้น
  ส่วน `config` คือ `labs/core/config.py` ที่โหลดค่าจาก `.env`

### ใต้ฝา: `llm.chat()` ทำงานอย่างไร

ไฟล์ `labs/core/llm.py` มีแค่ 2 ฟังก์ชันหลัก:

```python
from openai import OpenAI
from . import config

def build_client() -> OpenAI:
    return OpenAI(
        api_key=config.require_api_key(),       # อ่านคีย์จาก .env (ผ่าน config)
        base_url=config.OPENROUTER_BASE_URL,     # ชี้ base_url ไป OpenRouter — นี่คือหัวใจ "thin client"
    )

def chat(messages, model=None, tools=None, **kwargs):
    client = build_client()                      # สร้าง OpenAI client (ชี้ OpenRouter)
    params = {"model": model or config.OPENROUTER_MODEL, "messages": messages}
    if tools: params["tools"] = tools
    params.update(kwargs)                        # max_tokens ฯลฯ ส่งผ่านตรงนี้
    return client.chat.completions.create(**params)
```

จุดที่ต้องเข้าใจ:
- `llm.chat()` ใช้ **OpenAI SDK ตัวจริง** แต่เปลี่ยน `base_url` เป็นของ OpenRouter — นี่คือนิยามของ
  "thin client" ตาม outline บท 1.2 (ไม่ต้องใช้ framework แยกของ OpenRouter)
- `api_key`, `base_url`, `model` เริ่มต้น ทั้งหมดมาจาก `config` ซึ่งอ่านมาจาก `.env` —
  จึง **เปลี่ยนโมเดล/คีย์/endpoint ได้จากจุดเดียว** โดยไม่แตะโค้ด Lab
- `**kwargs` คือช่องที่ทำให้ Lab ส่ง `max_tokens` (Lab 2) หรือ `tools` (Lab 3+) เข้าไปได้

> สรุป: `llm` = โมดูล `labs/core/llm.py`, `llm.chat()` = ฟังก์ชันที่ห่อ `OpenAI(...).chat.completions.create(...)`
> ไว้ชั้นเดียว ทุก Lab ตั้งแต่ Lab 2 เป็นต้นไปจึงเรียก LLM ด้วยรูปแบบเดียวกันหมด

---

## อธิบายจุดสำคัญของโค้ด

### `first_llm.py` — โครงสร้าง messages และ token usage

#### ฟังก์ชัน `ask(question, max_tokens)`

จุดสำคัญที่ควรเปิดอ่าน:

```python
messages = [
    {"role": "system", "content": SYSTEM},   # system : กำหนดบทบาท/พฤติกรรม
    {"role": "user",   "content": question}, # user   : คำถามจากผู้ใช้
]
resp = llm.chat(messages=messages, max_tokens=max_tokens)
```

- ตัวแปร `SYSTEM` คือ system prompt ที่กำหนดบทบาทของ LLM
- `resp.choices[0].message.content` คือคำตอบของโมเดล
- `resp.usage` มีฟิลด์ `prompt_tokens`, `completion_tokens`, `total_tokens` — ใช้ติดตามค่าใช้จ่ายและตรวจว่าใกล้ context limit หรือยัง
- การตั้ง `max_tokens` ต่ำๆ เป็นวิธีฝึกดูผลของ output limit

### `compare_models.py` — เปรียบเทียบโมเดล

#### ฟังก์ชัน `run()`

ส่ง `QUESTION` เดียวกัน (`"อธิบายความต่างของ Chatbot กับ Agent ใน 2 ประโยค"`) ไปยังหลายโมเดลใน `MODELS` list โดยใช้ `llm.chat(model=model, ...)` แล้ววัด:
- `resp.usage.total_tokens` — จำนวน token ที่ใช้
- `time.time()` ก่อน/หลัง — เวลาตอบสนอง (วินาที)

สรุปผลเป็นตาราง `model / total_tok / sec / note` เพื่อเปรียบเทียบได้ทันที

> จุดที่ควรเปิดอ่าน: parameter `model=model` ใน `llm.chat()` — แสดงว่า OpenRouter รองรับการเลือกโมเดล
> ต่อ request ได้ (ส่งชื่อโมเดลต่างกันในแต่ละครั้งที่เรียก) โดยใช้ base_url/คีย์เดิมจาก `config`

---

## ผลลัพธ์ที่คาดหวัง

### `first_llm.py`

```
============================================================
[user]      อธิบาย Agent Loop ใน 2 ประโยค
[assistant] Agent Loop คือ...
------------------------------------------------------------
[token] prompt=42 completion=68 total=110
[model] qwen/qwen3.5-35b-a3b
```

### `compare_models.py`

```
==============================================================================
model                                   total_tok    sec  note
------------------------------------------------------------------------------
qwen/qwen3.5-35b-a3b                         185   2.31  Agent คือระบบที่...
openai/gpt-oss-120b                           172   3.10  ...
meta-llama/llama-3.1-8b-instruct              144   1.05  ...
```

> Lab 2 ไม่มี screenshot รวมไว้ใน repo เพราะ `compare_models.py` เรียกหลายโมเดลและมีค่าใช้จ่าย — รันได้เองตามคำสั่งด้านบน
