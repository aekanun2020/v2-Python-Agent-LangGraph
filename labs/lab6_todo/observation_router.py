"""Risk-based routing for optional semantic review at the Observation stage."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

from labs.lab6_todo.observation_policy import ObservationState
from labs.lab6_todo.semantic_reviewer import SemanticReview, hybrid_decision

RiskLevel = Literal["low", "medium", "high"]
RoutingMode = Literal["rules", "shadow", "enforce"]


@dataclass
class RiskAssessment:
    level: RiskLevel
    signals: list[str]
    reviewer_required: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


HIGH_REQUIREMENTS = {
    "pre_review_time_window", "latest_review_anchor", "safe_join_cardinality",
    "cross_evidence_consistency", "employment_length_dimension",
    "loan_amount_metric", "funded_amount_proxy", "loan_status_not_approval",
}
MEDIUM_REQUIREMENTS = {
    "active_employee_population", "department_grain", "explicit_denominator",
}


def assess_observation_risk(*, hard: ObservationState, step_description: str,
                            tool: str, tool_arguments: dict | None = None) -> RiskAssessment:
    requirements = set(hard.semantic_requirements)
    sql = re.sub(r"\s+", " ", str((tool_arguments or {}).get("query", ""))).lower()
    signals: list[str] = []

    high = sorted(requirements & HIGH_REQUIREMENTS)
    medium = sorted(requirements & MEDIUM_REQUIREMENTS)
    signals.extend(f"contract:{item}" for item in high + medium)
    if re.search(r"\b(row_number|rank|dense_rank)\s*\(", sql):
        signals.append("sql:window_function")
        high.append("window_function")
    satellite_joins = sum(
        bool(re.search(rf"\bjoin\s+(?:dbo\.)?{table}\b", sql))
        for table in ("skills", "training_records", "performance_reviews", "projects")
    )
    if satellite_joins >= 2:
        signals.append("sql:multi_satellite_join")
        high.append("multi_satellite_join")
    if not high and (medium or any(token in sql for token in ("group by", "count(", "sum("))):
        signals.append("sql:aggregate")

    if high:
        level: RiskLevel = "high"
    elif medium or "sql:aggregate" in signals:
        level = "medium"
    else:
        level = "low"

    reviewer_required = hard.decision == "accept" and level == "high"
    if hard.decision != "accept":
        reason = "hard policy already rejected the result; reviewer cannot override it"
    elif reviewer_required:
        reason = "high semantic risk passed hard checks; independent review is useful"
    else:
        reason = f"{level} risk is handled by deterministic policy without reviewer cost"
    return RiskAssessment(level, signals, reviewer_required, reason)


def validate_routing_mode(mode: str) -> RoutingMode:
    normalized = mode.strip().lower()
    if normalized not in ("rules", "shadow", "enforce"):
        raise ValueError("OBSERVATION_ROUTING_MODE must be rules, shadow, or enforce")
    return normalized  # type: ignore[return-value]


def routed_decision(mode: RoutingMode, hard: ObservationState,
                    review: SemanticReview | None = None) -> str:
    if mode in ("rules", "shadow") or review is None:
        return hard.decision
    return hybrid_decision(hard, review)
