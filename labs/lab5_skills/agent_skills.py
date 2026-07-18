"""
Lab 5 (ต่อ) — Agent + Skill Routing
อ้างอิง outline: บทที่ 2.1 / แบบฝึกหัดที่ 5

รวม SkillLoader เข้ากับ agent loop + MCP (จาก Lab 4):
  1) ใส่ "ดัชนี skill" (ชื่อ+คำอธิบาย) ลง system prompt — Progressive Disclosure
  2) รอบแรก ให้ LLM เลือก skill ที่ตรงที่สุด (route)
  3) โหลดเนื้อหาเต็มเฉพาะ skill นั้น ใส่กลับเข้า context แล้วทำงานต่อด้วย MCP tools

รัน:  python labs/lab5_skills/agent_skills.py "แต่ละแผนกมีพนักงานกี่คน"
      python labs/lab5_skills/agent_skills.py "ลูกค้าโกรธมาก ขอคุยหัวหน้า"
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import llm, config
from labs.core.registry import ToolRegistry
from labs.lab5_skills.skill_loader import SkillLoader

BASE_SYSTEM = "คุณคือ agent ของบริษัท ตอบเป็นภาษาไทย ใช้ MCP tools เมื่อจำเป็น"


def run(question: str, loader: SkillLoader, registry: ToolRegistry, max_steps: int = 8):
    # ---- (1) Routing : ใส่ดัชนี skill ลง system prompt แล้วให้ LLM เลือก ----
    routing_system = BASE_SYSTEM + "\n\n" + loader.index_for_prompt()
    route_resp = llm.chat(messages=[
        {"role": "system", "content": routing_system},
        {"role": "user", "content": question},
    ], max_tokens=30)
    chosen = SkillLoader.route_from_reply(route_resp.choices[0].message.content)
    print(f"[route] เลือก skill: {chosen}")

    # ---- (2) โหลดเนื้อหาเต็มเฉพาะ skill ที่ถูกเลือก (Progressive Disclosure) ----
    skill_body = loader.load_full(chosen) if chosen else ""
    system = BASE_SYSTEM
    if skill_body:
        system += "\n\n[เนื้อหา skill ที่ใช้กับงานนี้]\n" + skill_body

    # ---- (3) ทำงานด้วย agent loop + MCP tools ----
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    for step in range(1, max_steps + 1):
        resp = llm.chat(messages=messages, tools=registry.openai_tools)
        msg = resp.choices[0].message
        if msg.tool_calls:
            print(f"[step {step}] เรียก {len(msg.tool_calls)} tool")
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = registry.dispatch(call.function.name, args)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            continue
        print("-" * 60)
        print(f"[answer]\n{msg.content}")
        return msg.content
    return None


def main():
    loader = SkillLoader()
    print(f"[skills] พบ {len(loader.names())} skills: {loader.names()}")
    registry = ToolRegistry()
    n = registry.add_server(config.MCP_SERVER_URL)
    print(f"[MCP] ค้นพบ {n} tools\n")

    q = sys.argv[1] if len(sys.argv) > 1 else "แต่ละแผนกมีพนักงานที่ยังปฏิบัติงานกี่คน"
    print(f"[user] {q}")
    try:
        run(q, loader, registry)
    finally:
        registry.close()


if __name__ == "__main__":
    main()
