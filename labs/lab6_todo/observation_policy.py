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

from labs.lab6_todo.capabilities import (
    evaluate_evidence_requirements, infer_action_capabilities,
)
from labs.lab6_todo.contract_runtime import (
    ResolvedContract, evaluate_action_claims, resolve_contract,
)
from labs.lab6_todo.observation_types import ActionHint, Claim, EvidenceRequirement

ObservationDecision = Literal["accept", "retry", "query_more", "replan", "stop", "reject"]


@dataclass
class ObservationState:
    result_type: str
    policy_modules: list[str]
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    semantic_requirements: list[str] = field(default_factory=list)
    execution_ok: bool = False
    supports_step: bool = False
    evidence_sufficient: bool = False
    # Backward-compatible alias kept for existing lesson code and traces.
    sufficient: bool = False
    decision: ObservationDecision = "reject"
    reason: str = ""
    proven_claims: list[Claim] = field(default_factory=list)
    contradicted_claims: list[Claim] = field(default_factory=list)
    unsupported_claims: list[Claim] = field(default_factory=list)
    suggested_action: ActionHint | None = None

    def as_dict(self) -> dict:
        return asdict(self)


ERROR_MARKERS = (
    "[mcp error]", "[registry]", "runtime rejected", "traceback", "exception",
    "bad gateway", "service unavailable", "timed out", "timeout",
)
TRUNCATION_MARKERS = ("truncated", "ถูกตัด", "more rows", "has_more", "next_cursor")
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


def _semantic_requirements(step_description: str, goal_description: str | None = None) -> list[str]:
    """Infer hard semantic claims from the active step, not from a global prompt."""
    step = step_description.lower()
    goal = (goal_description or "").lower()
    context = goal + " " + step
    requirements = []
    if any(word in step for word in ("ปฏิบัติงาน", "active employee", "active workforce")):
        requirements.append("active_employee_population")
    if any(word in step for word in ("แยกแผนก", "รายแผนก", "by department", "department grain")):
        requirements.append("department_grain")
    if any(word in step for word in ("เปอร์เซ็นต์", "ร้อยละ", "percent", "percentage", " pct")):
        requirements.append("explicit_denominator")
    if (any(word in step for word in ("ก่อน", "before", "pre-review"))
            and any(word in step for word in ("review", "ประเมิน"))):
        requirements.append("pre_review_time_window")
    if (any(word in step for word in ("ล่าสุด", "latest"))
            and any(word in step for word in ("review", "ประเมิน"))):
        requirements.append("latest_review_anchor")
    if any(word in step for word in (
        "ยอดซ้ำ", "แถวซ้ำ", "fan-out", "fanout", "join cardinality", "aggregate ก่อน join"
    )):
        requirements.append("safe_join_cardinality")
    if any(word in step for word in (
        "หลักฐานก่อนหน้า", "prior evidence", "cross-evidence", "cross evidence"
    )):
        requirements.append("cross_evidence_consistency")
    return requirements


def extract_numeric_facts(result: str) -> dict[str, float]:
    facts: dict[str, float] = {}
    try:
        parsed = json.loads(result)
        rows = parsed if isinstance(parsed, list) else parsed.get("rows", parsed.get("data", [parsed]))
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    for key, value in row.items():
                        if isinstance(value, (int, float)):
                            facts[str(key).lower()] = float(value)
    except (json.JSONDecodeError, AttributeError):
        pass
    lines = [line.strip() for line in result.splitlines() if line.strip()]
    for index in range(len(lines) - 1):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", lines[index]):
            match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", lines[index + 1].replace(",", ""))
            if match:
                facts[lines[index].lower()] = float(match.group())
    return facts


def _check_query_semantics(requirements: list[str], tool_arguments: dict | None,
                           result: str, prior_facts: dict[str, float] | None = None
                           ) -> tuple[list[str], list[str]]:
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
        elif requirement == "pre_review_time_window":
            ok = bool(re.search(
                r"(?:training|\bt\.)[^;]*(?:end_date|start_date)\s*<=\s*[^;]*review_date",
                sql,
            ))
        elif requirement == "latest_review_anchor":
            ok = bool(
                re.search(r"row_number\s*\(\s*\)\s*over[^;]*order\s+by[^;]*review_date\s+desc", sql)
                or re.search(r"max\s*\(\s*(?:\w+\.)?review_date\s*\)", sql)
            )
        elif requirement == "safe_join_cardinality":
            joined_satellites = sum(
                bool(re.search(rf"\bjoin\s+(?:dbo\.)?{table}\b", sql))
                for table in ("skills", "training_records", "performance_reviews", "projects")
            )
            employee_aggregates = len(re.findall(r"group\s+by\s+(?:\w+\.)?employee_id", sql))
            ok = joined_satellites < 2 or ("with " in sql and employee_aggregates >= joined_satellites)
        (passed if ok else failed).append(requirement)
    if prior_facts and "cross_evidence_consistency" in requirements:
        current = extract_numeric_facts(result)
        shared = set(current) & {key.lower() for key in prior_facts}
        contradictions = [
            key for key in shared
            if abs(current[key] - float(next(value for old_key, value in prior_facts.items()
                                             if old_key.lower() == key))) > 1e-9
        ]
        (failed if contradictions else passed).append("cross_evidence_consistency")
    return passed, failed


def observe_result(*, step_description: str, tool: str, result: str,
                   tool_arguments: dict | None = None,
                   semantic_checks: bool = False,
                   prior_facts: dict[str, float] | None = None,
                   goal_description: str | None = None,
                   contract: ResolvedContract | None = None,
                   required_capability: str | None = None,
                   evidence_requirements: list[EvidenceRequirement] | None = None,
                   ) -> ObservationState:
    """Select and execute deterministic checks for this step/tool/result tuple."""
    if contract is None and goal_description:
        contract = resolve_contract(goal_description)
    result_type = _result_type(tool, result)
    step = step_description.lower()
    tool_lower = tool.lower()
    modules = ["execution_integrity", "payload_presence", "step_tool_alignment"]
    if result_type == "schema" or required_capability == "schema_inspection":
        modules.append("schema_coverage")
    if result_type == "query_result" or required_capability in {
        "query_execution", "aggregation", "comparison", "existence_check",
    }:
        modules.extend(["result_shape", "population_and_grain"])
    if result_type == "truncated":
        modules.append("completeness")
    requirements = (
        _semantic_requirements(step_description, goal_description)
        # Legacy lesson policies remain available for old untyped callers only.
        # Typed plans declare their intent explicitly and are never reclassified
        # from natural-language description keywords.
        if (semantic_checks and result_type == "query_result"
            and not evidence_requirements) else []
    )
    step_capability = required_capability
    capabilities = infer_action_capabilities(tool, tool_arguments)
    contract_claims = (
        evaluate_action_claims(
            contract, sql=str((tool_arguments or {}).get("query", ""))
        ) if (semantic_checks and result_type == "query_result"
              and "schema_inspection" not in capabilities) else []
    )
    requirements.extend(claim.id for claim in contract_claims)
    if requirements:
        modules.append("semantic_contract")
    if "cross_evidence_consistency" in requirements:
        modules.append("cross_evidence_consistency")

    state = ObservationState(result_type=result_type, policy_modules=modules,
                             semantic_requirements=requirements)
    if result_type == "error":
        state.failed.extend(["execution_integrity", "supports_current_step"])
        state.decision = "retry"
        state.reason = "tool payload reports an execution/transport error"
        return state
    state.passed.append("execution_integrity")
    state.execution_ok = True

    if not _has_substantive_payload(result):
        state.failed.extend(["payload_presence", "supports_current_step"])
        state.decision = "query_more"
        state.reason = "non-empty text contains no inspectable rows, fields, or evidence"
        return state
    state.passed.append("payload_presence")

    required_capability = step_capability
    if required_capability and required_capability not in capabilities:
        state.failed.append("step_tool_alignment")
        state.decision = "reject"
        state.reason = "tool type does not support the active plan step"
        return state
    state.passed.append("step_tool_alignment")

    typed_claims = evaluate_evidence_requirements(
        evidence_requirements or [], capabilities, result
    )
    state.proven_claims.extend(
        claim for claim in typed_claims if claim.status == "proven"
    )
    state.unsupported_claims.extend(
        claim for claim in typed_claims if claim.status == "unsupported"
    )
    if state.unsupported_claims:
        state.failed.extend(
            f"evidence:{claim.id}" for claim in state.unsupported_claims
        )
        state.decision = "query_more"
        state.reason = "action does not satisfy typed evidence requirements"
        state.suggested_action = ActionHint(
            "query_more", " | ".join(claim.basis for claim in state.unsupported_claims)
        )
        return state

    if result_type == "truncated":
        state.warnings.append("result_completeness_unknown")
        state.decision = "query_more"
        state.reason = "truncated result cannot prove population-level completion"
        return state

    semantic_passed, semantic_failed = _check_query_semantics(
        [item for item in requirements if item not in {claim.id for claim in contract_claims}],
        tool_arguments, result, prior_facts
    )
    state.proven_claims.extend(claim for claim in contract_claims if claim.status == "proven")
    state.unsupported_claims.extend(
        claim for claim in contract_claims if claim.status == "unsupported"
    )
    if "cross_evidence_consistency" in semantic_failed:
        state.contradicted_claims.append(Claim(
            id="cross_evidence_consistency",
            type="consistency",
            description="current result conflicts with previously accepted evidence",
            status="contradicted",
            basis="numeric facts sharing the same field name do not match",
        ))
    semantic_passed.extend(claim.id for claim in state.proven_claims)
    semantic_failed.extend(claim.id for claim in state.unsupported_claims)
    state.passed.extend(f"semantic:{item}" for item in semantic_passed)
    if semantic_failed:
        state.failed.extend(f"semantic:{item}" for item in semantic_failed)
        state.decision = "retry"
        state.reason = "successful payload violates active-step semantics: " + ", ".join(
            semantic_failed
        )
        hint = " | ".join(claim.basis for claim in state.unsupported_claims if claim.basis)
        state.suggested_action = ActionHint("retry", hint or state.reason)
        return state

    state.supports_step = True
    state.evidence_sufficient = True
    state.sufficient = True
    state.decision = "accept"
    state.reason = "hard checks passed for this step, tool, and result type"
    return state
