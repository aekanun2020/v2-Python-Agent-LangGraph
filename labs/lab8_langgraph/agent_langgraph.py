"""Lab 8 — LangGraph agent with an explicit, revisable PlannerState."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

load_dotenv()

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.5-35b-a3b")

SYSTEM_PROMPT = (
    "คุณคือนักวิเคราะห์ข้อมูลของบริษัท ตอบคำถามเชิงธุรกิจจากฐานข้อมูล MS SQL Server "
    "เรียกเครื่องมือเพื่อหาหลักฐานจริงก่อนตอบ เขียน T-SQL ด้วย TOP ไม่ใช้ LIMIT "
    "และอย่าอ้างข้อสรุปที่ไม่มีหลักฐานจาก tool"
)


class PlanStep(BaseModel):
    id: int
    description: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    evidence: list[str] = Field(default_factory=list)


class PlanDraft(BaseModel):
    goal: str
    steps: list[PlanStep]
    assumptions: list[str] = Field(default_factory=list)


class PlanReview(BaseModel):
    sufficient: bool = False
    reason: str
    steps: list[PlanStep]
    assumptions: list[str] = Field(default_factory=list)


class PlannerState(TypedDict):
    goal: str
    steps: list[dict]
    assumptions: list[str]
    revision: int
    last_reason: str
    ready_to_answer: bool


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    planner: PlannerState
    tool_trace: list[dict]


def build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
    )


def latest_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def render_plan(planner: PlannerState) -> str:
    lines = [f"เป้าหมาย: {planner['goal']}", f"แผน revision {planner['revision']}:"]
    for step in planner["steps"]:
        evidence = "; ".join(step.get("evidence", [])) or "ยังไม่มี"
        lines.append(
            f"- [{step['status']}] ขั้น {step['id']}: {step['description']} | หลักฐาน: {evidence}"
        )
    if planner.get("assumptions"):
        lines.append("สมมติฐาน: " + "; ".join(planner["assumptions"]))
    return "\n".join(lines)


def plan_changed(old: PlannerState, review: PlanReview) -> bool:
    old_core = [(s["description"], s["status"]) for s in old["steps"]]
    new_core = [(s.description, s.status) for s in review.steps]
    return old_core != new_core or old.get("assumptions", []) != review.assumptions


def apply_review(old: PlannerState, review: PlanReview) -> PlannerState:
    changed = plan_changed(old, review)
    return {
        "goal": old["goal"],
        "steps": [step.model_dump() for step in review.steps],
        "assumptions": review.assumptions,
        "revision": old["revision"] + int(changed),
        "last_reason": review.reason,
        "ready_to_answer": review.sufficient,
    }


async def build_graph(*, llm=None, tools=None, checkpointer=None):
    """Build the agent; injectable dependencies keep planner tests deterministic."""
    if tools is None:
        client = MultiServerMCPClient(
            {"mcp": {"url": MCP_SERVER_URL, "transport": "streamable_http"}}
        )
        tools = await client.get_tools()
        print(f"[MCP] เชื่อมกับ {MCP_SERVER_URL}")
        print(f"[MCP] ค้นพบ {len(tools)} tools: {[tool.name for tool in tools]}")

    base_llm = llm or build_llm()
    planner_llm = base_llm.with_structured_output(PlanDraft)
    reviewer_llm = base_llm.with_structured_output(PlanReview)
    llm_with_tools = base_llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def create_plan(state: AgentState):
        objective = latest_user_text(state["messages"])
        draft = planner_llm.invoke(
            [
                SystemMessage(content=(
                    "สร้างแผนสั้นที่ตรวจสอบได้สำหรับตอบคำถามด้วยฐานข้อมูล "
                    "ฐานข้อมูลเป็น Microsoft SQL Server: ใช้ T-SQL (TOP ไม่ใช่ LIMIT) "
                    "ห้ามใช้ SHOW TABLES หรือ DESCRIBE; เริ่มจาก MCP schema tool แล้ว query และตรวจหลักฐาน "
                    "แต่ละขั้นต้องเป็นการกระทำที่สังเกตผลได้"
                )),
                HumanMessage(content=objective),
            ]
        )
        planner: PlannerState = {
            "goal": draft.goal,
            "steps": [step.model_dump() for step in draft.steps],
            "assumptions": draft.assumptions,
            "revision": 1,
            "last_reason": "สร้างแผนเริ่มต้น",
            "ready_to_answer": False,
        }
        print("\n[PLANNER] สร้างแผน revision 1")
        print(render_plan(planner))
        return {"planner": planner, "tool_trace": []}

    def call_model(state: AgentState):
        plan_context = (
            SYSTEM_PROMPT
            + "\n\nคุณต้องทำตาม PlannerState ด้านล่าง ปรับการเรียก tool ให้ตรงขั้นที่ยังไม่เสร็จ "
            + "เมื่อหลักฐานเพียงพอจึงตอบผู้ใช้\n"
            + render_plan(state["planner"])
        )
        response = llm_with_tools.invoke([SystemMessage(content=plan_context), *state["messages"]])
        return {"messages": [response]}

    def capture_tool_result(state: AgentState):
        trace = list(state.get("tool_trace", []))
        for message in reversed(state["messages"]):
            if isinstance(message, ToolMessage):
                item = {
                    "tool": message.name or "unknown",
                    "tool_call_id": message.tool_call_id,
                    "result": str(message.content)[:30000],
                }
                if not trace or trace[-1]["tool_call_id"] != item["tool_call_id"]:
                    trace.append(item)
                    print(f"[TOOL CALL] {item['tool']} id={item['tool_call_id']}")
                    print(f"[TOOL RESULT] {item['result'][:220]}")
                break
        return {"tool_trace": trace}

    def review_plan(state: AgentState):
        last_tool = state.get("tool_trace", [])[-1]
        current = state["planner"]
        review = reviewer_llm.invoke(
            [
                SystemMessage(content=(
                    "คุณเป็น plan reviewer ตรวจผล tool เทียบกับเป้าหมายและแผนเดิม "
                    "อัปเดต status/evidence และแก้ เพิ่ม ลบ หรือเรียงขั้นใหม่เมื่อผลจริงทำให้แผนเดิมไม่พอ "
                    "ตั้ง sufficient=true เฉพาะเมื่อหลักฐานพอตอบเป้าหมาย แต่ยังคงขั้นสรุปคำตอบไว้"
                )),
                HumanMessage(content=json.dumps({
                    "planner": current,
                    "latest_tool_result": last_tool,
                }, ensure_ascii=False)),
            ]
        )
        updated = apply_review(current, review)
        label = "REPLAN" if updated["revision"] > current["revision"] else "PLAN REVIEW"
        print(f"\n[{label}] revision {current['revision']} -> {updated['revision']}: {review.reason}")
        print(render_plan(updated))
        return {"planner": updated}

    def review_answer(state: AgentState):
        current = state["planner"]
        draft_answer = str(state["messages"][-1].content)
        review = reviewer_llm.invoke(
            [
                SystemMessage(content=(
                    "ตรวจคำตอบร่างเทียบ PlannerState และหลักฐาน tool จริง "
                    "หากคำตอบมีหลักฐานครบ ให้ตั้ง sufficient=true และ mark ทุกขั้นที่เสร็จเป็น completed "
                    "หากยังขาดหลักฐาน ให้ sufficient=false ระบุขั้น in_progress ที่ต้องทำต่อ และห้ามอนุมัติคำตอบ"
                )),
                HumanMessage(content=json.dumps({
                    "planner": current,
                    "tool_evidence": state.get("tool_trace", []),
                    "draft_answer": draft_answer,
                }, ensure_ascii=False)),
            ]
        )
        updated = apply_review(current, review)
        verdict = "APPROVED" if review.sufficient else "REJECTED"
        print(f"\n[ANSWER REVIEW {verdict}] revision {current['revision']} -> {updated['revision']}: {review.reason}")
        print(render_plan(updated))
        result = {"planner": updated}
        if not review.sufficient:
            # Anthropic rejects conversations ending in an assistant prefill. Turn the
            # review into an explicit new instruction so the agent can gather evidence.
            result["messages"] = [HumanMessage(content=(
                "[PLAN REVIEW FEEDBACK — ทำงานต่อ ห้ามตอบจบ] " + review.reason
            ))]
        return result

    def after_model(state: AgentState):
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "review_answer"

    def after_answer_review(state: AgentState):
        return END if state["planner"]["ready_to_answer"] else "call_model"

    graph = StateGraph(AgentState)
    graph.add_node("planner", create_plan)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", tool_node)
    graph.add_node("capture_tool_result", capture_tool_result)
    graph.add_node("review_plan", review_plan)
    graph.add_node("review_answer", review_answer)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "call_model")
    graph.add_conditional_edges("call_model", after_model, {"tools": "tools", "review_answer": "review_answer"})
    graph.add_edge("tools", "capture_tool_result")
    graph.add_edge("capture_tool_result", "review_plan")
    graph.add_edge("review_plan", "call_model")
    graph.add_conditional_edges("review_answer", after_answer_review, {END: END, "call_model": "call_model"})
    return graph.compile(checkpointer=checkpointer or MemorySaver())


async def main():
    app = await build_graph()
    config = {"configurable": {"thread_id": "planner-demo-1"}}
    question = (
        "วิเคราะห์ว่าแผนกใดมีพนักงานที่ยังปฏิบัติงานมากที่สุด "
        "พร้อมรายชื่อพนักงานในแผนกนั้น และอธิบายว่าตรวจสอบคำตอบอย่างไร"
    )
    print(f"\n[USER] {question}")
    result = await app.ainvoke({"messages": [HumanMessage(content=question)]}, config=config)
    print(f"\n[FINAL ANSWER]\n{result['messages'][-1].content}")
    print("\n[FINAL PLANNER STATE]")
    print(render_plan(result["planner"]))
    print(f"[PROOF] tool_calls={len(result.get('tool_trace', []))}, revisions={result['planner']['revision']}")


if __name__ == "__main__":
    asyncio.run(main())
