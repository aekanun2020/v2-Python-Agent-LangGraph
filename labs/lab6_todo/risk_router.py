"""Cheap deterministic observation and semantic-risk routing."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from labs.lab6_todo.evidence_state import EvidenceRecord, EvidenceState


class DeterministicDecision(str, Enum):
    ACCEPT = "accept"
    RETRY = "retry"
    QUERY_MORE = "query_more"


@dataclass(frozen=True)
class DeterministicObservation:
    action_succeeded: bool
    decision: DeterministicDecision
    result_kind: str
    fields: tuple[str, ...]
    semantic_risk: bool
    risk_reasons: tuple[str, ...]
    reason: str


ERROR_MARKERS = (
    '"status": "error"',
    "'status': 'error'",
    "traceback (most recent call last)",
    "syntax error",
    "invalid object name",
    "connection error",
    "timeout",
)
EMPTY_MARKERS = (
    "no results",
    "no rows",
    "empty result",
    "0 rows",
)
SQL_RISK_PATTERNS = {
    "distinct-grain": r"\bcount\s*\(\s*distinct\b",
    "multi-source": r"\bjoin\b",
    "derived-ratio": r"(?<!\*)/(?!\*)|\bpercent(?:age)?\b|\brate\b",
    "conditional-metric": r"\bcase\b",
    "time-validity": r"\b(current_date|getdate|expiry|effective_date)\b",
    "aggregate-comparison": r"\b(avg|sum|min|max)\s*\(",
}
DECISION_TERMS = (
    "recommend",
    "should ",
    "decision",
    "caus",
    "efficient",
    "productiv",
    "risk",
    "approve",
    "reject",
    "แนะนำ",
    "ควร",
    "ตัดสิน",
    "สาเหตุ",
    "ประสิทธิภาพ",
    "ความเสี่ยง",
    "อนุมัติ",
    "ปฏิเสธ",
)
QUALITATIVE_TERMS = (
    "indicates", "suggests", "reflects", "implies", "important",
    "balanced", "efficient", "risk", "therefore", "because",
    "แสดงถึง", "สะท้อน", "บ่งชี้", "หมายความว่า", "สำคัญ",
    "สมดุล", "มีประสิทธิภาพ", "ความเสี่ยง", "ดังนั้น", "เนื่องจาก",
    "สามารถนำไปใช้", "เหมาะสม",
)


def _arguments_text(record: EvidenceRecord) -> str:
    return json.dumps(record.arguments, ensure_ascii=False, default=str)


def _extract_fields(raw_result: str) -> tuple[str, ...]:
    first = next(
        (line.strip() for line in raw_result.splitlines() if line.strip()),
        "",
    )
    if not first or first.startswith(("{", "[", "(")):
        return ()
    tokens = tuple(
        token for token in re.split(r"\s{2,}|\t+|,\s*", first)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$]*", token)
    )
    return tokens


def observe_deterministically(
    question: str,
    record: EvidenceRecord,
) -> DeterministicObservation:
    raw_lower = record.raw_result.lower()
    if any(marker in raw_lower for marker in ERROR_MARKERS):
        return DeterministicObservation(
            False,
            DeterministicDecision.RETRY,
            "error",
            (),
            False,
            (),
            "tool payload reports an execution or transport error",
        )
    if any(marker in raw_lower for marker in EMPTY_MARKERS):
        return DeterministicObservation(
            True,
            DeterministicDecision.QUERY_MORE,
            "empty",
            (),
            False,
            (),
            "tool succeeded but returned no usable rows",
        )

    tool_lower = record.tool_name.lower()
    if "context" in tool_lower or "schema" in tool_lower:
        return DeterministicObservation(
            True,
            DeterministicDecision.ACCEPT,
            "schema",
            _extract_fields(record.raw_result),
            False,
            (),
            "schema/context result accepted by deterministic checks",
        )

    query_text = _arguments_text(record).lower()
    reasons = tuple(
        name for name, pattern in SQL_RISK_PATTERNS.items()
        if re.search(pattern, query_text, flags=re.IGNORECASE)
    )
    question_lower = question.lower()
    if any(term in question_lower for term in DECISION_TERMS):
        reasons += ("semantic-decision",)
    return DeterministicObservation(
        True,
        DeterministicDecision.ACCEPT,
        "query_result",
        _extract_fields(record.raw_result),
        bool(reasons),
        tuple(dict.fromkeys(reasons)),
        "hard checks passed",
    )


def _number_tokens(text: str) -> set[str]:
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    values = set()
    for match in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?", text):
        normalized = match.replace(",", "")
        percent = normalized.endswith("%")
        core = normalized[:-1] if percent else normalized
        if "." in core:
            core = core.rstrip("0").rstrip(".")
        values.add(core + ("%" if percent else ""))
    return values


def final_semantic_risk(
    question: str,
    answer: str,
    evidence: EvidenceState,
) -> tuple[str, ...]:
    """Route only answers that need semantic judgment to the LLM reviewer."""
    reasons: list[str] = []
    if not answer.strip():
        reasons.append("empty-answer")
    allowed_numbers = _number_tokens(question)
    for record in evidence.records:
        allowed_numbers.update(_number_tokens(record.raw_result))
        allowed_numbers.update(_number_tokens(_arguments_text(record)))
    unsupported = _number_tokens(answer) - allowed_numbers
    if unsupported:
        reasons.append(
            "unsupported-numbers:" + ",".join(sorted(unsupported))
        )

    combined = (question + "\n" + answer).lower()
    if any(term in combined for term in DECISION_TERMS):
        reasons.append("semantic-decision")
    if any(term in answer.lower() for term in QUALITATIVE_TERMS):
        reasons.append("qualitative-interpretation")
    if any(
        observation.semantic_risk
        for observation in evidence.structured_observations
        if isinstance(observation, DeterministicObservation)
    ):
        reasons.append("risky-tool-semantics")
    return tuple(dict.fromkeys(reasons))
