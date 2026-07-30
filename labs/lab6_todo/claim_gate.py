"""Fail-closed typed claim gate for Phase 2C final answers."""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from enum import Enum

from labs.lab6_todo.evidence_state import (
    EvidenceState,
    ObservationState,
    SemanticVerdict,
)


class ClaimType(str, Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    QUALITATIVE = "qualitative"
    RECOMMENDATION = "recommendation"


@dataclass(frozen=True)
class GatedClaim:
    text: str
    claim_type: ClaimType
    accepted: bool
    reason: str


RECOMMENDATION_TERMS = (
    "recommend", "should", "must", "ควร", "แนะนำ", "จำเป็นต้อง",
    "เพิ่มคน", "ลดคน", "จ้าง", "เลิกจ้าง", "อนุมัติ", "ปฏิเสธ",
)
QUALITATIVE_TERMS = (
    "indicates", "suggests", "reflects", "implies", "important",
    "balanced", "efficient", "risk", "therefore", "because",
    "แสดงถึง", "สะท้อน", "บ่งชี้", "หมายความว่า", "สำคัญ",
    "สมดุล", "มีประสิทธิภาพ", "ความเสี่ยง", "ดังนั้น", "เนื่องจาก",
    "สามารถนำไปใช้", "เหมาะสม",
)


def _numbers(text: str) -> tuple[float, ...]:
    values = []
    for token in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?", text):
        try:
            values.append(float(token.rstrip("%").replace(",", "")))
        except ValueError:
            pass
    return tuple(values)


def classify_claim(text: str) -> ClaimType:
    lowered = text.lower()
    if any(term in lowered for term in RECOMMENDATION_TERMS):
        return ClaimType.RECOMMENDATION
    if _numbers(text):
        return ClaimType.NUMERIC
    if any(term in lowered for term in QUALITATIVE_TERMS):
        return ClaimType.QUALITATIVE
    return ClaimType.CATEGORICAL


def _numeric_closure(question: str, evidence: EvidenceState) -> tuple[float, ...]:
    """Numbers directly evidenced plus transparent ratio/difference arithmetic."""
    base = list(_numbers(question))
    for record in evidence.records:
        base.extend(_numbers(record.raw_result))
        base.extend(_numbers(str(record.arguments)))
    closure = list(base)
    # Bound combinatorics while covering common percentage/shortfall claims.
    unique = list(dict.fromkeys(base))[:200]
    for left, right in itertools.product(unique, repeat=2):
        closure.append(left - right)
        closure.append(abs(left - right))
        if right:
            closure.append(left / right)
            closure.append(left / right * 100)
    # One second bounded pass covers threshold minus a derived percentage,
    # e.g. 80 - (7 / 25 * 100) = 52 percentage points.
    derived = list(dict.fromkeys(closure))[len(unique):][:400]
    for left, right in itertools.product(unique, derived):
        closure.append(left - right)
        closure.append(abs(left - right))
    return tuple(closure)


def _numbers_supported(
    claim: str,
    question: str,
    evidence: EvidenceState,
) -> bool:
    allowed = _numeric_closure(question, evidence)
    return all(
        any(math.isclose(value, item, rel_tol=1e-4, abs_tol=0.011)
            for item in allowed)
        for value in _numbers(claim)
    )


def _grain_supported(claim: str, evidence: EvidenceState) -> bool:
    lowered = claim.lower()
    if not any(term in lowered for term in ("coverage", "ความครอบคลุม")):
        return True
    review_queries = [
        str(record.arguments).lower()
        for record in evidence.records
        if "performance_review" in str(record.arguments).lower()
    ]
    return any(
        "distinct" in query and "employee_id" in query
        for query in review_queries
    )


def verify_claims(
    question: str,
    observation: ObservationState,
    evidence: EvidenceState,
) -> tuple[GatedClaim, ...]:
    """Verify the Observer allowlist; never edit the Agent draft."""
    results = []
    for raw in observation.supported_claims:
        claim = str(raw).strip()
        if not claim:
            continue
        claim_type = classify_claim(claim)
        accepted = True
        reason = "observer-supported"
        if claim_type is ClaimType.RECOMMENDATION:
            accepted = False
            reason = "recommendations require a separate policy contract"
        elif claim_type is ClaimType.NUMERIC and not _numbers_supported(
            claim, question, evidence
        ):
            accepted = False
            reason = "numeric post-condition failed"
        elif not _grain_supported(claim, evidence):
            accepted = False
            reason = "grain contract failed"
        results.append(GatedClaim(claim, claim_type, accepted, reason))
    return tuple(results)


def verify_then_emit(
    question: str,
    observation: ObservationState,
    evidence: EvidenceState,
) -> str:
    """Compose only verified claims; fail closed for unsupported decisions."""
    claims = verify_claims(question, observation, evidence)
    accepted = [claim.text for claim in claims if claim.accepted]
    decision_requested = any(
        term in question.lower() for term in RECOMMENDATION_TERMS
    )
    decision_refused = (
        decision_requested
        and observation.verdict is not SemanticVerdict.APPROVE
    )
    lines = []
    if accepted:
        lines.append("ข้อเท็จจริงที่ผ่านการตรวจหลักฐาน:")
        lines.extend(f"- {claim}" for claim in accepted)
    if decision_refused or observation.verdict is SemanticVerdict.REFUSE_DECISION:
        lines.append(
            "หลักฐานที่มีไม่เพียงพอสำหรับการตัดสินใจหรือคำแนะนำที่ร้องขอ"
        )
    if not lines:
        lines.append(
            "ยังไม่มี claim ที่ผ่านเงื่อนไขการตรวจหลักฐานครบถ้วน"
        )
    return "\n".join(lines)
