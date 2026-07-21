"""Dynamic observation policy for the plain-Python planner.

The policy is selected from the active plan step, tool name, and returned
payload.  Hard checks remain deterministic; the LLM receives the structured
decision and decides whether to retry, query more, or revise the plan.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

ObservationDecision = Literal["accept", "retry", "query_more", "reject"]


@dataclass
class ObservationState:
    result_type: str
    policy_modules: list[str]
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    semantic_requirements: list[str] = field(default_factory=list)
    supports_step: bool = False
    sufficient: bool = False
    decision: ObservationDecision = "reject"
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


ERROR_MARKERS = (
    "[mcp error]", "[registry]", "runtime rejected", "traceback", "exception",
    "bad gateway", "service unavailable", "timed out", "timeout",
)
TRUNCATION_MARKERS = ("truncated", "ถูกตัด", "more rows", "has_more", "next_cursor")
SCHEMA_WORDS = ("schema", "table", "column", "field", "โครงสร้าง", "คอลัมน์")
QUERY_WORDS = ("query", "sql", "aggregate", "metric", "จำนวน", "อัตรา", "ค่าเฉลี่ย")


def _result_type(tool: str, result: str) -> str:
    lowered_tool = tool.lower()
    lowered = result.lower()
    if any(marker in lowered for marker in ERROR_MARKERS):
        return "error"
    if any(marker in lowered for marker in TRUNCATION_MARKERS):
        return "truncated"
    if any(word in lowered_tool for word in ("schema", "table", "column", "describe", "database_context")):
        return "schema"
    if any(word in lowered_tool for word in ("query", "sql", "execute")):
        return "query_result"
    try:
        parsed = json.loads(result)
        if isinstance(parsed, (list, dict)):
            return "structured"
    except json.JSONDecodeError:
        pass
    return "text"


def _has_substantive_payload(result: str) -> bool:
    compact = re.sub(r"\s+", " ", result).strip().lower()
    empty_success = (
        "query executed successfully, but rows omitted",
        "success with no payload",
        '"rows": []',
        '"data": []',
    )
    return len(compact) >= 8 and not any(marker in compact for marker in empty_success)


def _semantic_requirements(step_description: str) -> list[str]:
    """Infer hard semantic claims from the active step, not from a global prompt."""
    step = step_description.lower()
    requirements = []
    if any(word in step for word in ("ปฏิบัติงาน", "active employee", "active workforce")):
        requirements.append("active_employee_population")
    if any(word in step for word in ("แยกแผนก", "รายแผนก", "by department", "department grain")):
        requirements.append("department_grain")
    if any(word in step for word in ("เปอร์เซ็นต์", "ร้อยละ", "percent", "percentage", " pct")):
        requirements.append("explicit_denominator")
    return requirements


def _check_query_semantics(requirements: list[str], tool_arguments: dict | None,
                           result: str) -> tuple[list[str], list[str]]:
    args = tool_arguments or {}
    sql = re.sub(r"\s+", " ", str(args.get("query", ""))).lower()
    payload = result.lower()
    passed, failed = [], []
    for requirement in requirements:
        ok = True
        if requirement == "active_employee_population":
            ok = bool(re.search(r"\bwhere\b.*\bstatus\b.*(?:ปฏิบัติงาน|active)", sql))
        elif requirement == "department_grain":
            ok = bool(re.search(r"\bgroup\s+by\b[^;]*(?:department|แผนก)", sql))
            ok = ok and any(token in payload for token in ("department", "แผนก"))
        elif requirement == "explicit_denominator":
            ok = ("/" in sql or "nullif" in sql) and any(
                token in sql for token in ("count(", "sum(", "total", "headcount")
            )
        (passed if ok else failed).append(requirement)
    return passed, failed


def observe_result(*, step_description: str, tool: str, result: str,
                   tool_arguments: dict | None = None,
                   semantic_checks: bool = False) -> ObservationState:
    """Select and execute deterministic checks for this step/tool/result tuple."""
    result_type = _result_type(tool, result)
    step = step_description.lower()
    tool_lower = tool.lower()
    modules = ["execution_integrity", "payload_presence", "step_tool_alignment"]
    if result_type == "schema" or any(word in step for word in SCHEMA_WORDS):
        modules.append("schema_coverage")
    if result_type == "query_result" or any(word in step for word in QUERY_WORDS):
        modules.extend(["result_shape", "population_and_grain"])
    if result_type == "truncated":
        modules.append("completeness")
    requirements = _semantic_requirements(step_description) if semantic_checks else []
    if requirements:
        modules.append("semantic_contract")

    state = ObservationState(result_type=result_type, policy_modules=modules,
                             semantic_requirements=requirements)
    if result_type == "error":
        state.failed.extend(["execution_integrity", "supports_current_step"])
        state.decision = "retry"
        state.reason = "tool payload reports an execution/transport error"
        return state
    state.passed.append("execution_integrity")

    if not _has_substantive_payload(result):
        state.failed.extend(["payload_presence", "supports_current_step"])
        state.decision = "query_more"
        state.reason = "non-empty text contains no inspectable rows, fields, or evidence"
        return state
    state.passed.append("payload_presence")

    expects_schema = any(word in step for word in SCHEMA_WORDS)
    schema_tool = any(word in tool_lower for word in (
        "schema", "table", "column", "describe", "database_context"
    ))
    expects_query = any(word in step for word in QUERY_WORDS)
    query_tool = any(word in tool_lower for word in ("query", "sql", "execute"))
    if (expects_schema and not schema_tool) or (expects_query and not query_tool):
        state.failed.append("step_tool_alignment")
        state.decision = "reject"
        state.reason = "tool type does not support the active plan step"
        return state
    state.passed.append("step_tool_alignment")

    if result_type == "truncated":
        state.warnings.append("result_completeness_unknown")
        state.decision = "query_more"
        state.reason = "truncated result cannot prove population-level completion"
        return state

    semantic_passed, semantic_failed = _check_query_semantics(
        requirements, tool_arguments, result
    )
    state.passed.extend(f"semantic:{item}" for item in semantic_passed)
    if semantic_failed:
        state.failed.extend(f"semantic:{item}" for item in semantic_failed)
        state.decision = "retry"
        state.reason = "successful payload violates active-step semantics: " + ", ".join(
            semantic_failed
        )
        return state

    state.supports_step = True
    state.sufficient = True
    state.decision = "accept"
    state.reason = "hard checks passed for this step, tool, and result type"
    return state
