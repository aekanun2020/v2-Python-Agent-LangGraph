"""Generic final-claim adjudication against explicit accepted evidence."""

from __future__ import annotations

import json
import re

from labs.lab6_todo.observation_types import Claim

STRICT_INCREASE = re.compile(
    r"เพิ่มขึ้นตาม|สูงขึ้นตาม|\bincreases?\s+with\b|\bmonotonic(?:ally)?\s+increas",
    re.IGNORECASE,
)
STRICT_DECREASE = re.compile(
    r"ลดลงตาม|ต่ำลงตาม|\bdecreases?\s+with\b|\bmonotonic(?:ally)?\s+decreas",
    re.IGNORECASE,
)
SOFT_INCREASE = re.compile(
    r"แนวโน้ม[^.\n]{0,100}(?:สูงขึ้น|เพิ่มขึ้น)|(?:สูงขึ้น|เพิ่มขึ้น)[^.\n]{0,100}แนวโน้ม|"
    r"\b(?:upward|increasing|positive)\s+trend\b|\btends?\s+to\s+increase\b",
    re.IGNORECASE,
)
SOFT_DECREASE = re.compile(
    r"แนวโน้ม[^.\n]{0,100}(?:ต่ำลง|ลดลง)|(?:ต่ำลง|ลดลง)[^.\n]{0,100}แนวโน้ม|"
    r"\b(?:downward|decreasing|negative)\s+trend\b|\btends?\s+to\s+decrease\b",
    re.IGNORECASE,
)


def _numeric_values(evidence: list[dict], keys: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for item in evidence:
        result = str(item.get("result", ""))
        try:
            parsed = json.loads(result)
            rows = parsed if isinstance(parsed, list) else parsed.get("rows", parsed.get("data", [parsed]))
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict):
                    lowered = {str(key).lower(): value for key, value in row.items()}
                    for key in keys:
                        value = lowered.get(key)
                        if isinstance(value, (int, float)):
                            values.append(float(value))
        except (json.JSONDecodeError, AttributeError):
            for key in keys:
                match = re.search(
                    rf"\b{re.escape(key)}\b\s*[:=|]?\s*(-?\d+(?:\.\d+)?)",
                    result, re.IGNORECASE,
                )
                if match:
                    values.append(float(match.group(1)))
    return values


def adjudicate_final_claims(answer: str, accepted_evidence: list[dict]) -> list[Claim]:
    """Adjudicate only claims with a bounded, auditable numeric proof contract."""
    claims: list[Claim] = []
    direction: str | None = None
    strict = False
    if STRICT_INCREASE.search(answer):
        direction, strict = "increase", True
    elif STRICT_DECREASE.search(answer):
        direction, strict = "decrease", True
    elif SOFT_INCREASE.search(answer):
        direction = "increase"
    elif SOFT_DECREASE.search(answer):
        direction = "decrease"
    if direction is None:
        return claims

    if strict:
        key = f"monotonic_{direction}_violations"
        values = _numeric_values(accepted_evidence, (key,))
        if not values:
            status, basis = "unsupported", f"strict trend needs numeric evidence field {key}=0"
        elif values[-1] == 0:
            status, basis = "proven", f"accepted evidence reports {key}=0"
        else:
            status, basis = "contradicted", f"accepted evidence reports {key}={values[-1]:g}"
    else:
        values = _numeric_values(
            accepted_evidence, ("trend_slope", "spearman_rho", "correlation"),
        )
        expected_positive = direction == "increase"
        if not values:
            status, basis = (
                "unsupported",
                "trend claim needs an explicit numeric trend_slope, spearman_rho, or correlation",
            )
        else:
            supports = values[-1] > 0 if expected_positive else values[-1] < 0
            status = "proven" if supports else "contradicted"
            basis = f"accepted numeric trend evidence={values[-1]:g}"
    claims.append(Claim(
        id="final_trend_claim", type="trend", description="trend asserted in final answer",
        status=status, basis=basis,
    ))
    return claims


def validate_final_claims(answer: str, accepted_evidence: list[dict]) -> None:
    failed = [
        claim for claim in adjudicate_final_claims(answer, accepted_evidence)
        if claim.status != "proven"
    ]
    if failed:
        details = "; ".join(f"{claim.status}: {claim.basis}" for claim in failed)
        raise ValueError("final claim adjudication rejected: " + details)
