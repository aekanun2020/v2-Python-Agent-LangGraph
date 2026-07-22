"""Validate declared capabilities against structural properties of an action."""

from __future__ import annotations

import re

from labs.lab6_todo.observation_types import Claim, EvidenceRequirement

CAPABILITY_CATALOG = (
    "schema_inspection",
    "sample_rows",
    "query_execution",
    "aggregation",
    "comparison",
    "existence_check",
)

EVIDENCE_PREDICATE_CATALOG = (
    "inspectable_payload",
    "schema_inspected",
    "rows_returned",
    "aggregation_executed",
    "comparison_executed",
    "existence_checked",
)

CAPABILITY_EVIDENCE_PREDICATES = {
    "schema_inspection": {"schema_inspected"},
    "sample_rows": {"rows_returned"},
    "query_execution": {"rows_returned"},
    "aggregation": {"aggregation_executed"},
    "comparison": {"comparison_executed"},
    "existence_check": {"existence_checked"},
}


def infer_action_capabilities(tool: str, arguments: dict | None = None) -> set[str]:
    name = tool.lower()
    sql = re.sub(r"\s+", " ", str((arguments or {}).get("query", ""))).lower()
    capabilities: set[str] = set()
    if any(token in name for token in ("schema", "table", "column", "describe", "database_context")):
        capabilities.update(("schema_inspection", "sample_rows"))
    if any(token in name for token in ("query", "sql", "execute")):
        capabilities.add("query_execution")
        if any(token in sql for token in ("information_schema", "sys.columns", "sys.tables")):
            capabilities.add("schema_inspection")
        if re.search(r"\bgroup\s+by\b|\b(?:avg|sum|count|min|max)\s*\(", sql):
            capabilities.add("aggregation")
        if re.search(r"(?:=|<>|!=|<=|>=|<|>)|\b(?:case|order\s+by)\b", sql):
            capabilities.add("comparison")
        if re.search(r"\bexists\b|\bcount\s*\(", sql):
            capabilities.add("existence_check")
    return capabilities


def validate_declared_capability(capability: str) -> None:
    if capability not in CAPABILITY_CATALOG:
        raise ValueError(
            f"unknown required_capability={capability!r}; choose one of {CAPABILITY_CATALOG}"
        )


def validate_evidence_predicate(predicate: str) -> None:
    if predicate not in EVIDENCE_PREDICATE_CATALOG:
        raise ValueError(
            f"unknown evidence predicate={predicate!r}; choose one of "
            f"{EVIDENCE_PREDICATE_CATALOG}"
        )


def validate_capability_requirements(
    capability: str, requirements: list[EvidenceRequirement],
) -> None:
    """Require a predicate that proves the declared capability, not generic payload only."""
    accepted = CAPABILITY_EVIDENCE_PREDICATES[capability]
    predicates = {requirement.predicate for requirement in requirements}
    if not predicates & accepted:
        raise ValueError(
            f"required_capability={capability!r} needs at least one evidence predicate "
            f"from {sorted(accepted)}"
        )


def evaluate_evidence_requirements(
    requirements: list[EvidenceRequirement], capabilities: set[str], result: str,
) -> list[Claim]:
    """Evaluate a bounded generic predicate vocabulary; never infer step intent."""
    checks = {
        "inspectable_payload": bool(result.strip()),
        "schema_inspected": "schema_inspection" in capabilities,
        "rows_returned": bool(result.strip()),
        "aggregation_executed": "aggregation" in capabilities,
        "comparison_executed": "comparison" in capabilities,
        "existence_checked": "existence_check" in capabilities,
    }
    claims: list[Claim] = []
    for requirement in requirements:
        validate_evidence_predicate(requirement.predicate)
        proven = checks[requirement.predicate]
        claims.append(Claim(
            id=requirement.claim_id,
            type=requirement.predicate,
            description=requirement.target or requirement.claim_id,
            status="proven" if proven else "unsupported",
            basis=(
                f"action structurally satisfies {requirement.predicate}"
                if proven else f"choose an action that satisfies {requirement.predicate}"
            ),
        ))
    return claims
