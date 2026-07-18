"""
Lab 7 — เพิ่ม Memory ให้ Agent จำการสนทนาข้ามรอบได้
อ้างอิง outline: บทที่ 2.3 / แบบฝึกหัดที่ 7

ปิดท้าย Module 2 — เพิ่ม 3 อย่างที่เขียนเองด้วย Pure Python:
  1) ConversationMemory : เก็บ messages ข้ามรอบ ส่งเข้า context ทุกครั้ง
  2) Compaction         : เมื่อ token เกินเกณฑ์ ให้ LLM สรุปบทสนทนาเก่าเป็นย่อหน้าเดียว
  3) Note-taking        : เก็บ fact สำคัญที่คงอยู่แม้ compaction

** สิ่งนี้คือสิ่งที่ Lab 8 จะได้ "ฟรี" จาก LangGraph (MemorySaver) — Lab นี้ทำให้
   เห็นว่าเบื้องหลังมันทำอะไร **

รัน:  python labs/lab7_memory/agent_memory.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import llm, config
from labs.core.registry import ToolRegistry

SYSTEM = (
    "คุณคือนักวิเคราะห์ข้อมูลที่จำบริบทการสนทนาก่อนหน้าได้ ตอบเป็นภาษาไทย "
    "ใช้ MCP tools ของฐานข้อมูล (เรียก get_database_context ก่อนเขียน T-SQL ใช้ TOP ไม่ใช่ LIMIT)"
)

# เกณฑ์ compaction (ตั้งต่ำเพื่อให้เห็นผลในแล็บ — ปรับได้)
COMPACT_AFTER_MESSAGES = 12


class ConversationMemory:
    """หน่วยความจำการสนทนาแบบ in-memory + compaction + notes."""
    def __init__(self):
        self.history: list[dict] = []     # messages ข้ามรอบ
        self.notes: list[str] = []         # fact สำคัญที่คงอยู่แม้ compaction

    def add(self, message: dict):
        self.history.append(message)

    def add_note(self, fact: str):
        self.notes.append(fact)

    def context(self) -> list[dict]:
        """ประกอบ context: system + notes + history (ไว้ส่งเข้า LLM ทุกครั้ง)."""
        sys_msg = {"role": "system", "content": SYSTEM}
        if self.notes:
            sys_msg["content"] += "\n\n[บันทึกที่ต้องจำ]\n- " + "\n- ".join(self.notes)
        return [sys_msg] + self.history

    def maybe_compact(self):
        """ถ้า history ยาวเกินเกณฑ์ ให้ LLM สรุปของเก่าเป็นย่อหน้าเดียว (รักษา token budget)."""
        if len(self.history) < COMPACT_AFTER_MESSAGES:
            return
        # เก็บ 4 ข้อความล่าสุดไว้ดิบ ๆ, ที่เหลือเอาไปสรุป
        keep = self.history[-4:]
        old = self.history[:-4]
        transcript = "\n".join(
            f"{m['role']}: {m.get('content','')}" for m in old if m.get("content"))
        summary = llm.chat(messages=[
            {"role": "system", "content": "สรุปบทสนทนาต่อไปนี้เป็นย่อหน้าเดียว เก็บข้อเท็จจริงสำคัญไว้"},
            {"role": "user", "content": transcript},
        ], max_tokens=300).choices[0].message.content
        self.history = [{"role": "assistant", "content": f"[สรุปบทสนทนาก่อนหน้า] {summary}"}] + keep
        print(f"[compaction] ย่อ {len(old)} ข้อความเป็นสรุป 1 ก้อน (เหลือ {len(self.history)} ข้อความ)")


def turn(question: str, mem: ConversationMemory, registry: ToolRegistry, max_steps: int = 8):
    print(f"\n[user] {question}")
    mem.add({"role": "user", "content": question})
    for step in range(1, max_steps + 1):
        resp = llm.chat(messages=mem.context(), tools=registry.openai_tools)
        msg = resp.choices[0].message
        if msg.tool_calls:
            mem.add({"role": "assistant", "content": msg.content or "",
                     "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = registry.dispatch(call.function.name, args)
                mem.add({"role": "tool", "tool_call_id": call.id, "content": result})
            continue
        mem.add({"role": "assistant", "content": msg.content})
        print(f"[answer] {msg.content}")
        mem.maybe_compact()
        return msg.content
    return None


def main():
    registry = ToolRegistry()
    n = registry.add_server(config.MCP_SERVER_URL)
    print(f"[MCP] ค้นพบ {n} tools")
    mem = ConversationMemory()
    mem.add_note("ผู้ใช้สนใจข้อมูลแผนก IT เป็นพิเศษ")  # ตัวอย่าง note ที่คงอยู่

    # ทดสอบความต่อเนื่อง: รอบสองอ้างถึง "แผนกนั้น" จากรอบแรก (ต้องจำได้)
    turn("แผนกที่มีพนักงานปฏิบัติงานมากที่สุดคือแผนกไหน กี่คน", mem, registry)
    turn("แล้วในแผนกนั้น มีใครบ้าง บอกชื่อมา", mem, registry)

    print("\n" + "=" * 60)
    print(f"[memory] history เก็บ {len(mem.history)} ข้อความ, notes {len(mem.notes)} รายการ")
    registry.close()


if __name__ == "__main__":
    main()
