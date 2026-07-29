"""
Lab 6 — เพิ่ม TodoWrite ให้ Agent และทดสอบกับ multi-step task
อ้างอิง outline: บทที่ 2.2 / แบบฝึกหัดที่ 6

เพิ่ม internal tool 2 ตัวที่เก็บ todo list ใน state ของ agent:
  - todo_write(items)          : สร้าง todo list ก่อนเริ่มงานหลายขั้น
  - todo_update(index, status) : อัปเดตสถานะแต่ละข้อระหว่างทำงาน

รวมกับ MCP tools (จาก Lab 4) เพื่อให้ todo มี "งานจริง" ให้วางแผน เช่น
ดึงข้อมูลจาก MSSQL หลายขั้นแล้วสรุป

รัน:  python labs/lab6_todo/agent_todo.py
"""
import argparse
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from labs.core import llm, config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.context_state import (
    ActionKind,
    AgentPhase,
    ContextState,
)
from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    SemanticVerdict,
)
from labs.lab6_todo.semantic_observer import review_final_answer

SYSTEM = (
    "คุณคือ agent ที่ทำงานเป็นขั้นตอน ตอบเป็นภาษาไทย\n"
    "กฎ: ถ้างานมี 3 ขั้นขึ้นไป ให้เรียก todo_write เขียนแผนก่อนเริ่มลงมือ "
    "แล้วทำทีละข้อ เรียก todo_update เปลี่ยนสถานะเป็น 'doing' ก่อนทำ และ 'done' เมื่อเสร็จ\n"
    "index ของ todo_update ให้ใช้เลขข้อแบบ 1-based ตามที่แสดงใน list (ข้อแรก = 1)\n"
    "เมื่อทำครบทุกข้อแล้ว (todo เป็น done หมด) ให้สรุปข้อค้นพบเชิงธุรกิจเป็นข้อความสุดท้าย โดยไม่ต้องเรียก tool อีก\n"
    "ใช้ MCP tools ของฐานข้อมูล (เรียก get_database_context ก่อนเขียน T-SQL ใช้ TOP ไม่ใช่ LIMIT)"
)


class TodoState:
    """เก็บ todo list ไว้ใน state ของ agent (in-memory)."""
    def __init__(self):
        self.items: list[dict] = []

    def write(self, items: list[str]) -> str:
        self.items = [{"index": i + 1, "task": t, "status": "todo"} for i, t in enumerate(items)]
        return self.render()

    def resolve_index(self, index: int) -> int | None:
        if not isinstance(index, int):
            return None
        # normalize: รองรับ index ทั้ง 1-based (ตามที่ render แสดง) และ 0-based (ที่ LLM บางครั้งส่งมา)
        # ถ้า index ตรงกับเลขข้อ 1-based ที่มีอยู่ → ใช้เลย; ไม่งั้นจึงลองตีความเป็น 0-based (index+1)
        valid = {it["index"] for it in self.items}
        if index in valid:
            return index
        if (index + 1) in valid:
            return index + 1
        return None

    def update(self, index: int, status: str) -> str:
        target = self.resolve_index(index)
        if target is None:
            return self.render()  # index ไม่ถูกต้อง — ไม่แก้ไขอะไร
        for it in self.items:
            if it["index"] == target:
                it["status"] = status
                break
        return self.render()

    def render(self) -> str:
        mark = {"todo": "[ ]", "doing": "[~]", "done": "[x]"}
        return "\n".join(f"{mark.get(i['status'],'[ ]')} {i['index']}. {i['task']}" for i in self.items)


def build_tools(registry: ToolRegistry) -> list[dict]:
    todo_tools = [
        {"type": "function", "function": {
            "name": "todo_write", "description": "เขียน todo list ก่อนเริ่มงานหลายขั้น",
            "parameters": {"type": "object", "properties": {
                "items": {"type": "array", "items": {"type": "string"},
                          "description": "รายการขั้นตอนงาน"}}, "required": ["items"]}}},
        {"type": "function", "function": {
            "name": "todo_update", "description": "อัปเดตสถานะของ todo ทีละข้อ",
            "parameters": {"type": "object", "properties": {
                "index": {"type": "integer"},
                "status": {"type": "string", "enum": ["todo", "doing", "done"]}},
                "required": ["index", "status"]}}},
    ]
    return todo_tools + registry.openai_tools


def _print_final(content: str, todo: TodoState, context: ContextState) -> str:
    print("-" * 60)
    print(f"[answer]\n{content}")
    print("-" * 60)
    print(f"[todo สุดท้าย]\n{todo.render()}")
    print(f"[context budget] {context.budgets}")
    return content


def run(
    question: str,
    registry: ToolRegistry,
    max_steps: int = 30,
    semantic_observer: bool = True,
    max_semantic_reviews: int = 2,
    max_mcp_calls: int = 12,
):
    todo = TodoState()
    context = ContextState(original_goal=question, phase=AgentPhase.ACT)
    evidence = EvidenceState()
    semantic_reviews = 0
    tools = build_tools(registry)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    for step in range(1, max_steps + 1):
        resp = llm.chat(messages=messages, tools=tools)
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                name = call.function.name
                try:
                    if name == "todo_write":
                        result = todo.write(args.get("items", []))
                        kind = ActionKind.PLAN
                        print(f"[step {step}] TODO_WRITE\n{result}")
                    elif name == "todo_update":
                        result = todo.update(args.get("index"), args.get("status"))
                        kind = ActionKind.STATE_UPDATE
                        target = todo.resolve_index(args.get("index"))
                        item = next(
                            (value for value in todo.items
                             if value["index"] == target),
                            None,
                        )
                        if item and args.get("status") == "doing":
                            context.start_step(item["task"])
                        elif item and args.get("status") == "done":
                            context.complete_step(item["task"])
                        print(f"[step {step}] TODO_UPDATE -> {args}\n{result}")
                    else:
                        if context.budgets.tool_calls >= max_mcp_calls:
                            result = (
                                "[runtime] MCP tool-call budget exhausted; "
                                "use accepted evidence and answer now"
                            )
                            kind = ActionKind.STATE_UPDATE
                            print(
                                f"[step {step}] TOOL BLOCKED {name} "
                                f"(budget={max_mcp_calls})"
                            )
                        else:
                            result = registry.dispatch(name, args)
                            kind = ActionKind.TOOL
                            context.add_evidence_ref(call.id)
                            evidence.accept(EvidenceRecord.from_tool(
                                call.id, name, args, result
                            ))
                            print(f"[step {step}] TOOL {name}")
                except Exception as error:
                    report = context.observe_error(error)
                    if report.alert:
                        print(f"[CONTEXT ALERT] {'; '.join(report.reasons)}")
                    raise

                report = context.observe_action(name, args, result, kind=kind)
                if report.alert:
                    print(f"[CONTEXT ALERT] {'; '.join(report.reasons)}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            continue
        context.set_phase(AgentPhase.ANSWER)
        proposed = msg.content or ""
        if semantic_observer:
            semantic_reviews += 1
            observation = review_final_answer(question, proposed, evidence)
            print(
                f"[FINAL OBSERVATION] verdict={observation.verdict.value} "
                f"reason={observation.reason}"
            )
            if observation.verdict is SemanticVerdict.QUERY_MORE:
                if semantic_reviews < max_semantic_reviews:
                    messages.append({"role": "assistant", "content": proposed})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Final observer พบว่าหลักฐานยังไม่ครบ: "
                            f"{observation.reason}\n"
                            "เรียก MCP เฉพาะข้อมูลที่ขาด แล้วตอบใหม่ "
                            "ห้ามทำซ้ำ query ที่มี evidence ครบแล้ว"
                        ),
                    })
                    context.set_phase(AgentPhase.ACT)
                    continue
                proposed = (
                    "ยังไม่สามารถตอบข้อสรุปที่ร้องขอได้จากหลักฐานที่มี: "
                    + observation.reason
                )
            elif observation.verdict in {
                SemanticVerdict.REWRITE,
                SemanticVerdict.REFUSE_DECISION,
            }:
                candidate = observation.revised_answer or proposed
                recheck = review_final_answer(question, candidate, evidence)
                print(
                    f"[FINAL RECHECK] verdict={recheck.verdict.value} "
                    f"reason={recheck.reason}"
                )
                if recheck.verdict is SemanticVerdict.APPROVE:
                    proposed = candidate
                elif recheck.verdict is SemanticVerdict.REFUSE_DECISION:
                    proposed = recheck.revised_answer or candidate
                else:
                    proposed = (
                        "ยังไม่สามารถให้คำตอบที่ผ่านการตรวจหลักฐานได้: "
                        + recheck.reason
                    )
        return _print_final(proposed, todo, context)

    # ชนเพดาน max_steps — บังคับให้โมเดลสรุปปิดท้าย จะได้ไม่จบแบบเงียบๆ โดยไม่มีบทสรุป
    messages.append({"role": "user",
                     "content": "ถึงขีดจำกัดขั้นตอนแล้ว ห้ามเรียก tool เพิ่ม — สรุปข้อค้นพบเชิงธุรกิจจากข้อมูลที่ได้มาเป็นข้อความสุดท้าย"})
    final = llm.chat(messages=messages)  # ไม่ส่ง tools — บังคับให้ตอบเป็นข้อความ
    context.set_phase(AgentPhase.ANSWER)
    content = final.choices[0].message.content or ""
    if semantic_observer:
        observation = review_final_answer(question, content, evidence)
        print(
            f"[FINAL OBSERVATION] verdict={observation.verdict.value} "
            f"reason={observation.reason}"
        )
        if observation.verdict in {
            SemanticVerdict.REWRITE,
            SemanticVerdict.REFUSE_DECISION,
        }:
            candidate = observation.revised_answer or content
            recheck = review_final_answer(question, candidate, evidence)
            print(
                f"[FINAL RECHECK] verdict={recheck.verdict.value} "
                f"reason={recheck.reason}"
            )
            if recheck.verdict is SemanticVerdict.APPROVE:
                content = candidate
            elif recheck.verdict is SemanticVerdict.REFUSE_DECISION:
                content = recheck.revised_answer or candidate
            else:
                content = (
                    "ยังไม่สามารถให้คำตอบที่ผ่านการตรวจหลักฐานได้: "
                    + recheck.reason
                )
        elif observation.verdict is SemanticVerdict.QUERY_MORE:
            content = (
                "ถึงขีดจำกัดขั้นตอนและหลักฐานยังไม่พอสำหรับตอบ: "
                + observation.reason
            )
    return _print_final(content, todo, context)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--semantic-observer",
        choices=["on", "off"],
        default="on",
        help="เปิด Phase 2 final semantic observer (default: on)",
    )
    parser.add_argument("question", nargs="?")
    args = parser.parse_args()
    registry = ToolRegistry()
    n = registry.add_server(config.MCP_SERVER_URL)
    print(f"[MCP] ค้นพบ {n} tools\n")
    q = args.question or (
        "ช่วยทำรายงาน HR: 1) นับพนักงานที่ปฏิบัติงานแยกตามแผนก "
        "2) หาพนักงานที่มีมูลค่าโครงการรวมสูงสุด 3 อันดับแรก "
        "3) สรุปข้อค้นพบเชิงธุรกิจ"
    )
    print(f"[user] {q}")
    try:
        run(
            q,
            registry,
            semantic_observer=args.semantic_observer == "on",
        )
    finally:
        registry.close()


if __name__ == "__main__":
    main()
