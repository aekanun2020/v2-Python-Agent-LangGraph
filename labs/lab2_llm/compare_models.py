"""
Lab 2 (ต่อ) — เปรียบเทียบหลายโมเดลบน OpenRouter
อ้างอิง outline: บทที่ 1.2 / แบบฝึกหัดที่ 2 (ข้อ 3)

ส่งคำถามเดียวกันไปหลายโมเดล แล้วบันทึก คำตอบ + token + เวลา ลงตาราง
เพื่อฝึกเลือกโมเดลให้เหมาะกับงาน/งบประมาณ

รัน:  python labs/lab2_llm/compare_models.py
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import llm

# ปรับรายชื่อโมเดลได้ตามที่อยากเทียบ (ชื่อโมเดลตามรูปแบบ OpenRouter)
MODELS = [
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-oss-120b",
    "meta-llama/llama-3.1-8b-instruct",
]

QUESTION = "อธิบายความต่างของ Chatbot กับ Agent ใน 2 ประโยค"


def run():
    rows = []
    for model in MODELS:
        print(f"\n>>> {model}")
        t0 = time.time()
        try:
            resp = llm.chat(
                messages=[{"role": "user", "content": QUESTION}],
                model=model,
                max_tokens=200,
            )
            dt = time.time() - t0
            ans = resp.choices[0].message.content.strip().replace("\n", " ")
            tot = resp.usage.total_tokens
            print(ans)
            rows.append((model, tot, round(dt, 2), ans[:60] + "..."))
        except Exception as e:
            rows.append((model, "-", "-", f"ERROR: {e}"))

    # สรุปเป็นตาราง
    print("\n" + "=" * 78)
    print(f"{'model':<40}{'total_tok':>10}{'sec':>7}  note")
    print("-" * 78)
    for m, tok, sec, note in rows:
        print(f"{m:<40}{str(tok):>10}{str(sec):>7}  {note}")


if __name__ == "__main__":
    run()
