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
    "สามารถนำไปใช้", "เหมาะสม", "สอดคล้อง", "แนวโน้ม", "ส่งผล",
    "ยุติธรรม", "กลยุทธ์", "strategic", "trend",
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
    if any(term in lowered for term in QUALITATIVE_TERMS):
        return ClaimType.QUALITATIVE
    if _numbers(text):
        return ClaimType.NUMERIC
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
    lowered = claim.lower()
    derived = (
        "%" in claim
        or any(
            term in lowered
            for term in (
                "coverage", "ratio", "rate", "average", "avg",
                "shortfall", "percentage point", "÷", "/", "×",
                "สัดส่วน", "อัตรา", "เฉลี่ย", "ต่ำกว่า",
            )
        )
    )
    if derived:
        allowed = _numeric_closure(question, evidence)
    else:
        direct = list(_numbers(question))
        for record in evidence.records:
            direct.extend(_numbers(record.raw_result))
        allowed = tuple(direct)
    return all(
        any(math.isclose(value, item, rel_tol=1e-4, abs_tol=0.011)
            for item in allowed)
        for value in _numbers(claim)
    )


def _draft_candidates(proposed_answer: str) -> tuple[str, ...]:
    """Extract only bounded factual candidates; prose remains LLM-reviewed."""
    candidates = []
    for raw in proposed_answer.splitlines():
        text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s*", "", raw).strip()
        text = text.strip("| ").strip()
        if not text or not _numbers(text):
            continue
        lowered = text.lower()
        if any(term in lowered for term in QUALITATIVE_TERMS):
            continue
        if len(text) > 500:
            continue
        candidates.append(text)
    return tuple(dict.fromkeys(candidates))


def _grain_supported(
    claim: str,
    evidence: EvidenceState,
    allowlist_preserves_grain: bool = False,
) -> bool:
    lowered = claim.lower()
    if not any(term in lowered for term in ("coverage", "ความครอบคลุม")):
        return True
    review_queries = [
        str(record.arguments).lower()
        for record in evidence.records
        if "performance_review" in str(record.arguments).lower()
    ]
    evidence_proves_grain = any(
        "distinct" in query and "employee_id" in query
        for query in review_queries
    )
    claim_preserves_grain = any(
        term in lowered
        for term in (
            "distinct",
            "พนักงานที่มี",
            "employees with",
            "employee with",
        )
    )
    return evidence_proves_grain and (
        claim_preserves_grain or allowlist_preserves_grain
    )


def _coverage_derivation(
    question: str,
    accepted_claims: list[str],
    evidence: EvidenceState,
) -> list[str]:
    lowered_question = question.lower()
    if not any(term in lowered_question for term in ("coverage", "ความครอบคลุม")):
        return []
    total_match = None
    reviewed_match = None
    for claim in accepted_claims:
        lowered_claim = claim.lower()
        if (
            ("ทั้งหมด" in lowered_claim or "total" in lowered_claim)
            and "review" not in lowered_claim
        ):
            total_match = re.search(r"(\d+)", claim)
        if (
            any(term in lowered_claim for term in ("พนักงานที่มี", "employees with", "employee with"))
            and any(term in lowered_claim for term in ("review", "performance"))
        ):
            reviewed_match = re.search(r"(\d+)", claim)
    threshold_match = re.search(r"(\d+(?:\.\d+)?)\s*%", question)
    if not (total_match and reviewed_match and threshold_match):
        return []
    total = float(total_match.group(1))
    reviewed = float(reviewed_match.group(1))
    threshold = float(threshold_match.group(1))
    if total <= 0 or reviewed < 0 or reviewed > total:
        return []
    if not _grain_supported(
        "coverage of distinct employees",
        evidence,
        allowlist_preserves_grain=True,
    ):
        return []
    coverage = reviewed / total * 100
    shortfall = max(threshold - coverage, 0)
    verdict = "ผ่าน" if coverage >= threshold else "ไม่ผ่าน"
    return [
        (
            "Evidence coverage ของพนักงานที่มี review เท่ากับ "
            f"{reviewed:g} / {total:g} = {coverage:g}%"
        ),
        (
            f"{verdict}เกณฑ์ขั้นต่ำ {threshold:g}%"
            + (
                f" โดยต่ำกว่า {shortfall:g} percentage points"
                if shortfall
                else ""
            )
        ),
    ]


def verify_claims(
    question: str,
    observation: ObservationState,
    evidence: EvidenceState,
    proposed_answer: str = "",
) -> tuple[GatedClaim, ...]:
    """Verify the Observer allowlist; never edit the Agent draft."""
    results = []
    allowlist_preserves_grain = any(
        any(
            term in str(raw).lower()
            for term in (
                "distinct",
                "พนักงานที่มี",
                "employees with",
                "employee with",
            )
        )
        for raw in observation.supported_claims
    )
    observer_claims = tuple(observation.supported_claims)
    draft_claims = tuple(
        claim for claim in _draft_candidates(proposed_answer)
        if claim not in observer_claims
    )
    for raw in observer_claims + draft_claims:
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
        elif (
            any(term in question.lower() for term in ("coverage", "ความครอบคลุม"))
            and any(term in claim.lower() for term in ("ขาด", "shortfall"))
            and "%" in claim
            and "point" not in claim.lower()
        ):
            accepted = False
            reason = "percentage shortfall must use percentage points"
        elif not _grain_supported(
            claim,
            evidence,
            allowlist_preserves_grain=allowlist_preserves_grain,
        ):
            accepted = False
            reason = "grain contract failed"
        results.append(GatedClaim(claim, claim_type, accepted, reason))
    return tuple(results)


def verify_then_emit(
    question: str,
    observation: ObservationState,
    evidence: EvidenceState,
    proposed_answer: str = "",
) -> str:
    """Compose only verified claims; fail closed for unsupported decisions."""
    claims = verify_claims(
        question,
        observation,
        evidence,
        proposed_answer=proposed_answer,
    )
    accepted = [claim.text for claim in claims if claim.accepted]
    derived = _coverage_derivation(question, accepted, evidence)
    if derived:
        accepted = [
            claim for claim in accepted
            if not any(
                term in claim.lower()
                for term in ("coverage", "ความครอบคลุม", "shortfall", "ขาด")
            )
        ]
        accepted.extend(derived)
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
