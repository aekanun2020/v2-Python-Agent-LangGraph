"""
Lab 2 — เรียกใช้ LLM API ครั้งแรกด้วย Python ผ่าน OpenRouter
อ้างอิง outline: บทที่ 1.2 / แบบฝึกหัดที่ 2

เรียนรู้:
  - โครงสร้าง messages (system / user / assistant) และ role
  - อ่าน token usage (prompt / completion / total) เพื่อบริหารค่าใช้จ่าย (บทที่ 1.1)

รัน:  python labs/lab2_llm/first_llm.py "คำถามของคุณ"
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import config, llm

SYSTEM = "คุณเป็นผู้ช่วยด้านเทคนิคที่ตอบกระชับ ตรงประเด็น เป็นภาษาไทย"


def ask(question: str, max_tokens: int | None = None):
    messages = [
        {"role": "system", "content": SYSTEM},   # system : กำหนดบทบาท/พฤติกรรม
        {"role": "user", "content": question},    # user   : คำถามจากผู้ใช้
    ]
    resp = llm.chat(messages=messages, max_tokens=max_tokens)

    answer = resp.choices[0].message.content
    usage = resp.usage   # ฝึกบริหาร token: ดูว่าใช้ token ไปเท่าไร

    print("=" * 60)
    print(f"[user]   {question}")
    print(f"[assistant] {answer}")
    print("-" * 60)
    print(f"[token] prompt={usage.prompt_tokens} "
          f"completion={usage.completion_tokens} total={usage.total_tokens}")
    print(f"[model] {config.OPENROUTER_MODEL}")
    return answer


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "อธิบาย Agent Loop ใน 2 ประโยค"
    # ทดลองตั้ง max_tokens ต่ำ ๆ เพื่อเห็นผลของ context/output limit ได้ที่นี่
    ask(q)
