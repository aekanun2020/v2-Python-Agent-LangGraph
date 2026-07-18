"""Lab 8 baseline — original ReAct loop before PlannerState was added."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from labs.lab8_langgraph.agent_langgraph import build_llm

BASELINE_SYSTEM_PROMPT = (
    "คุณคือนักวิเคราะห์ข้อมูลของบริษัท ตอบคำถามเชิงธุรกิจจากฐานข้อมูล MS SQL Server "
    "ขั้นตอน: เรียก get_database_context ก่อนเสมอเพื่อดู schema แล้วจึงเขียน T-SQL "
    "ที่ถูกต้อง (ใช้ TOP ไม่ใช่ LIMIT) ส่งให้ execute_query_tool ตอบเป็นภาษาไทย "
    "พร้อมตารางสรุปและข้อสังเกตเชิงธุรกิจ"
)


class BaselineState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_baseline_graph(*, llm=None, tools, checkpointer=None):
    """Build the original model → tools → model loop with no explicit plan state."""
    base_llm = llm or build_llm()
    llm_with_tools = base_llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def call_model(state: BaselineState):
        response = llm_with_tools.invoke(
            [SystemMessage(content=BASELINE_SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    def after_model(state: BaselineState):
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(BaselineState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", after_model, {"tools": "tools", END: END})
    graph.add_edge("tools", "call_model")
    return graph.compile(checkpointer=checkpointer or MemorySaver())
