"""LLM semantic observer grounded only in accepted tool evidence."""
from __future__ import annotations

import json
import re
from typing import Any

from labs.core import config, llm
from labs.lab6_todo.claim_ledger import ClaimLedger
from labs.lab6_todo.evidence_state import (
    EvidenceState,
    ObservationState,
    SemanticViolation,
    SemanticVerdict,
)


OBSERVER_SYSTEM = """You are the final semantic observer of a tool-using agent.
Evaluate the proposed answer only against the user question and ACCEPTED EVIDENCE.
Do not add outside knowledge and do not solve the database task yourself.

Generic evidence rules:
1. Numbers, identifiers, labels, units, status values and categories must be
   directly supported by evidence or by transparent arithmetic over evidence.
2. Preserve data grain. A record count is not a distinct entity count unless
   the query/result proves distinctness.
   Coverage/rate numerator and denominator must share a grain. Otherwise label
   it explicitly as a record-to-entity ratio and do not call it entity coverage.
3. Do not turn missing records into proof that an entity lacks something.
4. Do not turn association, proxy, project value or per-head arithmetic into
   causation, efficiency, productivity, revenue, profit or staffing need.
   A computed ratio may be reported only by its literal arithmetic name (for
   example "project_value per active employee"). If the user asks which entity
   is more efficient but no efficiency definition and required inputs are
   evidenced, choose refuse_decision.
5. Do not invent units or currency when metadata does not provide them.
   This rule also applies to revised_answer. Never copy an unsupported unit
   merely because it appears in the proposed answer or user question.
   Percentage subtraction is reported in percentage points.
   Keep threshold shortfall separate from uncovered share. For example, if
   coverage is C and threshold is T, shortfall is (T-C) percentage points,
   while uncovered share is (100-C) percent.
6. Recommendations and decisions require their necessary business evidence.
   If the requested decision cannot be supported, refuse that decision while
   still reporting supported descriptive facts.
   If the user did not ask for recommendations, rewrite unsupported
   prescriptive additions out of the answer. Missing records alone never prove
   that training, hiring, replacement, renewal, or process change is necessary.
7. Preserve canonical labels exactly as evidence shows them.
   Minimize data: do not expose person-level identifiers or examples when an
   aggregate answer is sufficient for the question.
8. If evidence is complete but wording/claims are wrong, choose rewrite.
9. Choose query_more only when a specific additional tool fact could answer the
   user question. Do not query again merely to repair wording.

Return one JSON object only:
{
  "verdict": "approve|rewrite|query_more|refuse_decision",
  "reason": "short reason",
  "supported_claims": ["..."],
  "unsupported_claims": ["..."],
  "contradictions": ["..."],
  "violations": [
    {"kind":"label|unit|number|grain|unsupported_claim",
     "text":"exact offending text","replacement":"grounded replacement or empty"}
  ],
  "revised_answer": "complete grounded answer or null"
}

For rewrite/refuse_decision, revised_answer must be a complete answer to show
the user and must itself obey every rule above. For approve it may be null.
For query_more it must be null.
"""


def _json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("semantic observer must return a JSON object")
    return value


def parse_observation(text: str) -> ObservationState:
    data = _json_object(text)
    verdict = SemanticVerdict(data["verdict"])
    revised = data.get("revised_answer")
    if verdict in {SemanticVerdict.REWRITE, SemanticVerdict.REFUSE_DECISION}:
        if not isinstance(revised, str) or not revised.strip():
            raise ValueError(f"{verdict.value} requires revised_answer")
    return ObservationState(
        verdict=verdict,
        reason=str(data.get("reason", "")),
        supported_claims=tuple(map(str, data.get("supported_claims", []))),
        unsupported_claims=tuple(map(str, data.get("unsupported_claims", []))),
        contradictions=tuple(map(str, data.get("contradictions", []))),
        violations=tuple(
            SemanticViolation(
                kind=str(item.get("kind", "unsupported_claim")),
                text=str(item.get("text", "")),
                replacement=str(item.get("replacement", "")),
            )
            for item in data.get("violations", [])
            if isinstance(item, dict) and str(item.get("text", ""))
        ),
        revised_answer=revised,
    )


def apply_bounded_rewrite(
    proposed_answer: str,
    observation: ObservationState,
) -> str:
    """Apply one observer rewrite and deterministic exact-span corrections."""
    candidate = observation.revised_answer or proposed_answer
    for violation in observation.violations:
        if violation.text:
            candidate = candidate.replace(
                violation.text,
                violation.replacement,
            )
    return candidate.strip()


def enforce_claim_alignment(
    observation: ObservationState,
    ledger: ClaimLedger,
) -> ObservationState:
    """Python owns completion: unresolved claims cannot receive approval."""
    if (
        observation.verdict is SemanticVerdict.APPROVE
        and ledger.unresolved
    ):
        unresolved = ", ".join(
            claim.claim_id for claim in ledger.unresolved
        )
        return ObservationState(
            verdict=SemanticVerdict.QUERY_MORE,
            reason=f"unresolved claim requirements: {unresolved}",
            supported_claims=observation.supported_claims,
            unsupported_claims=observation.unsupported_claims,
            contradictions=observation.contradictions,
            violations=observation.violations,
        )
    return observation


def review_final_answer(
    question: str,
    proposed_answer: str,
    evidence: EvidenceState,
    claim_ledger: str = "[not provided]",
    timeout: float = 60,
) -> ObservationState:
    payload = (
        f"USER QUESTION:\n{question}\n\n"
        f"CLAIM LEDGER:\n{claim_ledger}\n\n"
        f"STRUCTURED OBSERVATIONS:\n{evidence.render_structured()}\n\n"
        f"ACCEPTED EVIDENCE:\n{evidence.render_for_review() or '[none]'}\n\n"
        f"PROPOSED ANSWER:\n{proposed_answer}"
    )
    response = llm.chat(
        messages=[
            {"role": "system", "content": OBSERVER_SYSTEM},
            {"role": "user", "content": payload},
        ],
        temperature=0,
        model=config.OBSERVER_MODEL,
        timeout=timeout,
        client_max_retries=0,
    )
    content = response.choices[0].message.content or ""
    return parse_observation(content)
