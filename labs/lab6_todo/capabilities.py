"""Validate declared capabilities against structural properties of an action."""

from __future__ import annotations

import re
from dataclasses import dataclass

from labs.lab6_todo.observation_types import Claim, EvidenceRequirement, ResourceRequirement

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


@dataclass(frozen=True)
class SQLStructure:
    has_select: bool = False
    has_where: bool = False
    has_group_by: bool = False
    has_aggregate: bool = False
    has_order_by: bool = False
    has_having: bool = False
    has_case: bool = False
    reads_catalog: bool = False


def analyze_sql_structure(sql: str) -> SQLStructure:
    """Small SQL lexer for capability shape; it never interprets domain names."""
    without_comments = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_literals = re.sub(r"N?'(?:''|[^'])*'", " STRING ", without_comments)
    normalized = re.sub(r"\s+", " ", without_literals).strip().lower()
    return SQLStructure(
        has_select=bool(re.search(r"\bselect\b", normalized)),
        has_where=bool(re.search(r"\bwhere\b", normalized)),
        has_group_by=bool(re.search(r"\bgroup\s+by\b", normalized)),
        has_aggregate=bool(re.search(r"\b(?:avg|sum|count|min|max)\s*\(", normalized)),
        has_order_by=bool(re.search(r"\border\s+by\b", normalized)),
        has_having=bool(re.search(r"\bhaving\b", normalized)),
        has_case=bool(re.search(r"\bcase\b", normalized)),
        reads_catalog=any(
            token in normalized for token in ("information_schema", "sys.columns", "sys.tables")
        ),
    )


def _identifier_tokens(value: str) -> set[str]:
    clean = re.sub(r"[\[\]`\"]", "", value).lower()
    return set(re.findall(r"[\w$]+(?:\.[\w$]+)*", clean, flags=re.UNICODE))


def action_resource_error(
    tool: str, arguments: dict | None, result: str | None,
    requirements: list[ResourceRequirement],
) -> str | None:
    """Bind declared resources to action structure (or schema payload for broad inspectors)."""
    if not requirements:
        return None
    args = arguments or {}
    name = tool.lower()
    query = str(args.get("query", ""))
    table_arg = str(args.get("table_name", args.get("table", "")))
    action_text = f"{query} {table_arg}".lower()
    payload_text = (result or "").lower()
    action_tokens = _identifier_tokens(action_text)
    payload_tokens = _identifier_tokens(payload_text)
    broad_schema_inspector = "database_context" in name or "schema" in name
    missing: list[str] = []
    for requirement in requirements:
        resource = requirement.name.lower().replace("[", "").replace("]", "")
        terminal = resource.split(".")[-1]
        # SQL aliases may replace table qualifiers, so a field binds by its terminal
        # identifier while its table is independently declared as a table resource.
        found_in_action = resource in action_tokens or (
            requirement.kind == "field"
            and any(token.split(".")[-1] == terminal for token in action_tokens)
        )
        found = found_in_action or (
            broad_schema_inspector and (
                resource in payload_tokens
                or any(token.split(".")[-1] == terminal for token in payload_tokens)
            )
        )
        if not found:
            missing.append(f"{requirement.kind}:{requirement.name}")
    if missing:
        return "action/result does not bind declared resources: " + ", ".join(missing)
    return None


def infer_action_capabilities(tool: str, arguments: dict | None = None) -> set[str]:
    name = tool.lower()
    sql = str((arguments or {}).get("query", ""))
    structure = analyze_sql_structure(sql)
    capabilities: set[str] = set()
    if any(token in name for token in ("schema", "table", "column", "describe", "database_context")):
        capabilities.update(("schema_inspection", "sample_rows"))
    if any(token in name for token in ("query", "sql", "execute")):
        capabilities.add("query_execution")
        if structure.reads_catalog:
            capabilities.add("schema_inspection")
        if structure.has_group_by or structure.has_aggregate:
            capabilities.add("aggregation")
        if structure.has_case or structure.has_order_by or structure.has_having:
            capabilities.add("comparison")
        # A filtered SELECT establishes whether matching records exist even when
        # the model chooses rows rather than COUNT/EXISTS as its SQL form.
        if structure.has_select and structure.has_where:
            capabilities.add("existence_check")
    return capabilities


def action_capability_error(
    required_capability: str | None, tool: str, arguments: dict | None = None,
) -> str | None:
    """Validate action shape and prevent a broad declaration hiding a specific action."""
    if not required_capability:
        return None
    capabilities = infer_action_capabilities(tool, arguments)
    if required_capability not in capabilities:
        return (
            f"action capabilities={sorted(capabilities)} do not satisfy "
            f"required_capability={required_capability!r}"
        )
    specialized = capabilities & {
        "schema_inspection", "aggregation", "comparison", "existence_check",
    }
    if required_capability == "query_execution" and specialized:
        return (
            "declared query_execution is too broad for this action; choose the most-specific "
            f"capability from {sorted(specialized)}"
        )
    return None


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
