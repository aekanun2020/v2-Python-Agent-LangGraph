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
from labs.lab6_todo.evidence_contract import contract_claims, metric_contract_status


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
CURRENCY_TERMS = ("บาท", "ดอลลาร์", "$", "usd", "thb")
SEMANTIC_TARGET_TERMS = (
    "efficiency", "efficient", "productivity", "ประสิทธิภาพ",
    "พิสูจน์ได้หรือไม่", "prove whether", "ยืนยันได้หรือไม่",
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


def _units_supported(claim: str, evidence: EvidenceState) -> bool:
    """A unit is admissible only when accepted evidence names that unit."""
    lowered = claim.lower()
    used = tuple(term for term in CURRENCY_TERMS if term in lowered)
    if not used:
        return True
    evidence_text = "\n".join(
        (record.raw_result + "\n" + str(record.arguments)).lower()
        for record in evidence.records
    )
    return all(term in evidence_text for term in used)


def _qualitative_supported(claim: str, question: str) -> bool:
    """Allow a declared threshold verdict, never an inferred latent metric."""
    lowered_claim = claim.lower()
    lowered_question = question.lower()
    latent_metric = any(
        term in lowered_claim
        for term in (
            "efficiency", "efficient", "productivity",
            "ประสิทธิภาพ", "ผลิตภาพ",
        )
    )
    if latent_metric:
        return False
    policy_declared = any(
        term in lowered_question
        for term in ("กำหนดว่า", "policy", "นโยบาย", "เกณฑ์")
    )
    threshold_verdict = (
        policy_declared
        and bool(_numbers(claim))
        and any(
            term in lowered_claim
            for term in (
                "ผ่าน", "ไม่ผ่าน", "เกิน", "ต่ำกว่า",
                "risk", "ความเสี่ยง", "เข้าเกณฑ์",
            )
        )
    )
    return threshold_verdict


def _unit_sum_derivations(
    question: str,
    accepted_claims: list[str],
) -> list[str]:
    """Derive a total from unique, evidenced group values with one unit."""
    lowered_question = question.lower()
    unit = next(
        (
            candidate
            for candidate in ("ชั่วโมง", "hours", "hour")
            if candidate in lowered_question
        ),
        None,
    )
    if not unit or not any(
        term in lowered_question for term in ("ทั้งหมด", "total", "สัดส่วน")
    ):
        return []
    if any(
        unit in claim.lower()
        and any(term in claim.lower() for term in ("ทั้งหมด", "total"))
        and len(_numbers(claim)) == 1
        for claim in accepted_claims
    ):
        return []
    components = set()
    for claim in accepted_claims:
        lowered = claim.lower()
        if unit not in lowered or "%" not in claim:
            continue
        match = re.search(
            rf"(\d[\d,]*(?:\.\d+)?)\s*{re.escape(unit)}"
            rf"[^\n%]*\(\s*(\d+(?:\.\d+)?)\s*%",
            claim,
            flags=re.IGNORECASE,
        )
        if match:
            components.add(float(match.group(1).replace(",", "")))
    if len(components) < 2:
        return []
    total = sum(components)
    return [f"รวมทั้งหมด {total:g} {unit}"]


def _per_entity_ratio_derivations(
    question: str,
    accepted_claims: list[str],
) -> list[str]:
    """Compute a literal value/entity ratio without relabelling it."""
    if not any(
        term in question.lower()
        for term in ("ประสิทธิภาพ", "efficiency", "per employee", "ต่อพนักงาน")
    ):
        return []
    headcounts: dict[str, float] = {}
    values: dict[str, float] = {}
    for claim in accepted_claims:
        headcount = re.search(
            r"^[-* ]*(.+?)\s+มีพนักงาน(?:ปฏิบัติงาน)?\s+"
            r"(\d[\d,]*(?:\.\d+)?)\s*คน",
            claim,
            flags=re.IGNORECASE,
        )
        if headcount:
            headcounts[headcount.group(1).strip()] = float(
                headcount.group(2).replace(",", "")
            )
        value = re.search(
            r"^[-* ]*(.+?)\s+มี[^\n]*?(?:project value|มูลค่า)"
            r"\s+(\d[\d,]*(?:\.\d+)?)",
            claim,
            flags=re.IGNORECASE,
        )
        if value:
            values[value.group(1).strip()] = float(
                value.group(2).replace(",", "")
            )
    claims = []
    for label in headcounts.keys() & values.keys():
        count = headcounts[label]
        value = values[label]
        if count <= 0:
            continue
        ratio = value / count
        claims.append(
            f"project value ต่อพนักงานของ {label} = "
            f"{value:g} / {count:g} = {ratio:.2f}"
        )
    return claims


def _question_ratio_derivations(
    question: str,
    evidence: EvidenceState,
) -> list[str]:
    """Recover typed operands from the request only after MCP corroboration."""
    pattern = re.compile(
        r"`([^`]+)`\s*มีพนักงาน(?:ปฏิบัติงาน)?\s*"
        r"(\d[\d,]*(?:\.\d+)?)\s*คน\s*"
        r"และมีโครงการมูลค่า\s*(\d[\d,]*(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )
    evidence_numbers = []
    for record in evidence.records:
        evidence_numbers.extend(_numbers(record.raw_result))
    claims = []
    for label, count_text, value_text in pattern.findall(question):
        count = float(count_text.replace(",", ""))
        value = float(value_text.replace(",", ""))
        corroborated = all(
            any(
                math.isclose(number, expected, rel_tol=1e-9, abs_tol=0.001)
                for number in evidence_numbers
            )
            for expected in (count, value)
        )
        if count <= 0 or not corroborated:
            continue
        claims.append(
            f"project value ต่อพนักงานของ {label} = "
            f"{value:g} / {count:g} = {value / count:.2f}"
        )
    return claims


def _strict_threshold_derivations(
    question: str,
    accepted_claims: list[str],
) -> list[str]:
    """Preserve a strict policy boundary when the request declares one."""
    match = re.search(
        r"(?:มากกว่า|สูงกว่า|เกิน|>)\s*(\d+(?:\.\d+)?)\s*%",
        question,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    threshold = float(match.group(1))
    percentages = set()
    for claim in accepted_claims:
        for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", claim):
            percentage = float(value)
            if not math.isclose(percentage, threshold, abs_tol=0.001):
                percentages.add(percentage)
    return [
        f"อัตรา {value:g}% มากกว่าเกณฑ์ {threshold:g}%"
        for value in sorted(percentages)
        if value > threshold
    ]


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
        elif not _units_supported(claim, evidence):
            accepted = False
            reason = "unit is absent from accepted evidence"
        elif (
            claim_type is ClaimType.QUALITATIVE
            and not _qualitative_supported(claim, question)
        ):
            accepted = False
            reason = "qualitative claim lacks a declared metric or policy"
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
    contract = metric_contract_status(question, evidence)
    if not contract.satisfied:
        return (
            "หลักฐานยังไม่ครบตาม metric contract "
            f"{contract.contract_id}: ขาด "
            + ", ".join(contract.missing_roles)
        )
    claims = verify_claims(
        question,
        observation,
        evidence,
        proposed_answer=proposed_answer,
    )
    accepted = list(contract_claims(question, evidence))
    accepted.extend(claim.text for claim in claims if claim.accepted)
    accepted = list(dict.fromkeys(accepted))
    accepted.extend(
        claim for claim in _unit_sum_derivations(question, accepted)
        if claim not in accepted
    )
    accepted.extend(
        claim for claim in _per_entity_ratio_derivations(question, accepted)
        if claim not in accepted
    )
    accepted.extend(
        claim for claim in _question_ratio_derivations(question, evidence)
        if claim not in accepted
    )
    accepted.extend(
        claim for claim in _strict_threshold_derivations(question, accepted)
        if claim not in accepted
    )
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
    semantic_conclusion_refused = (
        any(term in question.lower() for term in SEMANTIC_TARGET_TERMS)
        and observation.verdict is not SemanticVerdict.APPROVE
    )
    lines = []
    if accepted:
        lines.append("ข้อเท็จจริงที่ผ่านการตรวจหลักฐาน:")
        lines.extend(f"- {claim}" for claim in accepted)
    if (
        decision_refused
        or semantic_conclusion_refused
        or observation.verdict is SemanticVerdict.REFUSE_DECISION
    ):
        lines.append(
            "หลักฐานที่มีไม่เพียงพอและไม่สามารถพิสูจน์ข้อสรุป "
            "การตัดสินใจ หรือคำแนะนำที่ร้องขอ"
        )
    if not lines:
        lines.append(
            "ยังไม่มี claim ที่ผ่านเงื่อนไขการตรวจหลักฐานครบถ้วน"
        )
    return "\n".join(lines)
