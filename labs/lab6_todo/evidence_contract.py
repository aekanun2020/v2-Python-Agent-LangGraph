"""Generic deterministic contracts applied before evidence admission."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from labs.lab6_todo.evidence_state import EvidenceRecord


class ContractDecision(str, Enum):
    ACCEPT = "accept"
    QUERY_MORE = "query_more"
    REJECT = "reject"


@dataclass(frozen=True)
class ContractResult:
    decision: ContractDecision
    reason: str


def _query_text(record: EvidenceRecord) -> str:
    for key in ("query", "sql", "statement"):
        value = record.arguments.get(key)
        if isinstance(value, str):
            return value
    return json.dumps(record.arguments, ensure_ascii=False, default=str)


def _has_unsafe_unicode_literal(query: str) -> bool:
    """MSSQL requires N'…' for Unicode string literals."""
    for match in re.finditer(r"(?P<prefix>[Nn]?)'(?P<value>(?:''|[^'])*)'", query):
        value = match.group("value")
        if any(ord(char) > 127 for char in value):
            if match.group("prefix").lower() != "n":
                return True
    return False


def validate_evidence_contract(
    question: str,
    record: EvidenceRecord,
) -> ContractResult:
    if "query" not in record.tool_name.lower():
        return ContractResult(ContractDecision.ACCEPT, "non-query evidence")
    query = _query_text(record)
    if _has_unsafe_unicode_literal(query):
        return ContractResult(
            ContractDecision.REJECT,
            "MSSQL Unicode filter literal must use N'…'",
        )
    lowered_question = question.lower()
    lowered_query = query.lower()
    if (
        any(term in lowered_question for term in ("coverage", "ความครอบคลุม"))
        and "performance_review" in lowered_query
        and "count(" in lowered_query
        and "distinct" not in lowered_query
    ):
        return ContractResult(
            ContractDecision.QUERY_MORE,
            "coverage numerator requires distinct entity grain",
        )
    return ContractResult(ContractDecision.ACCEPT, "contract checks passed")
