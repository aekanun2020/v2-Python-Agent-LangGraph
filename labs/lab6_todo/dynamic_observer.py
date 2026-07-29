"""LLM-assisted claim planning and post-tool dynamic observation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from labs.core import llm
from labs.lab6_todo.claim_ledger import ClaimLedger, ClaimRequirement
from labs.lab6_todo.evidence_state import EvidenceRecord


class NextAction(str, Enum):
    ACCEPT = "accept"
    QUERY_MORE = "query_more"
    REPLAN = "replan"
    STOP = "stop"


@dataclass(frozen=True)
class EvidenceFact:
    subject: str
    predicate: str
    value: Any
    unit: str | None
    grain: str
    evidence_id: str
    derivation: str | None = None


@dataclass(frozen=True)
class MissingEvidenceRequest:
    claim_id: str
    grain: str
    fields: tuple[str, ...]
    operation: str
    reason: str

    def render(self) -> str:
        return (
            f"claim={self.claim_id} grain={self.grain} "
            f"fields={list(self.fields)} operation={self.operation} "
            f"reason={self.reason}"
        )


@dataclass(frozen=True)
class DynamicObservation:
    evidence_id: str
    action_succeeded: bool
    supports_active_step: bool
    evidence_complete: bool
    grain: str
    fields: tuple[str, ...]
    canonical_labels: tuple[str, ...]
    facts: tuple[EvidenceFact, ...]
    proved_claim_ids: tuple[str, ...]
    contradictions: tuple[tuple[str, str], ...]
    missing_evidence: tuple[MissingEvidenceRequest, ...]
    claim_updates: tuple[tuple[str, str, tuple[str, ...]], ...]
    next_action: NextAction
    reason: str


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
        raise ValueError("expected a JSON object")
    return value


def _appears_in_evidence(value: Any, evidence_text: str) -> bool:
    if value is None:
        return True
    rendered = str(value)
    if rendered in evidence_text:
        return True
    if isinstance(value, (int, float)):
        compact_evidence = evidence_text.replace(",", "")
        return rendered in compact_evidence
    return False


CLAIM_PLANNER_SYSTEM = """Create a minimal claim ledger for a tool-using agent.
Claims are evidence requirements, not answers. Be domain-neutral.
Split only claims that need distinct evidence. Preserve the user's threshold,
comparison operator and requested decision exactly.
For coverage/rate claims, numerator and denominator must have the same grain.
If the prompt gives record count over entity count, add a claim that verifies
the numerator as COUNT(DISTINCT entity_id), unless the user explicitly requests
a record-to-entity ratio.

Return JSON only:
{"claims":[
  {"claim_id":"claim_001","description":"...",
   "required_grain":"record|entity|group|aggregate|metadata",
   "required_fields":["..."]}
]}
"""


def build_claim_ledger(question: str, timeout: float = 45) -> ClaimLedger:
    response = llm.chat(
        messages=[
            {"role": "system", "content": CLAIM_PLANNER_SYSTEM},
            {"role": "user", "content": question},
        ],
        temperature=0,
        timeout=timeout,
        client_max_retries=0,
    )
    data = _json_object(response.choices[0].message.content or "")
    claims = []
    for index, item in enumerate(data.get("claims", []), start=1):
        claim_id = str(item.get("claim_id") or f"claim_{index:03d}")
        claims.append(ClaimRequirement(
            claim_id=claim_id,
            description=str(item.get("description", "")),
            required_grain=str(item.get("required_grain", "unknown")),
            required_fields=tuple(map(str, item.get("required_fields", []))),
        ))
    return ClaimLedger(claims)


DYNAMIC_OBSERVER_SYSTEM = """Observe one completed tool action against the active
step and claim ledger. Extract only facts explicitly present in the tool result.
Do not use outside knowledge. Do not infer people from record counts. Preserve
labels exactly. A missing row is not proof that an entity lacks something.
Never mark a coverage/rate claim complete when numerator and denominator have
different grains. Record count cannot prove entity coverage; request a distinct
entity count. A difference between percentages is expressed in percentage
points, not percent.

Decisions:
- accept: result supports one or more claims and those claims are complete
- query_more: result is useful but a specific field/grain/aggregate is missing
- replan: active step/tool direction cannot satisfy the required claims
- stop: tool result proves the requested decision is unsupported or impossible

Return JSON only:
{
 "action_succeeded":true,
 "supports_active_step":true,
 "evidence_complete":false,
 "grain":"...",
 "fields":["..."],
 "canonical_labels":["..."],
 "facts":[
   {"subject":"...","predicate":"...","value":0,"unit":null,
    "grain":"...","derivation":null}
 ],
 "proved_claim_ids":["claim_001"],
 "contradictions":[{"claim_id":"claim_002","reason":"..."}],
 "missing_evidence":[{
   "claim_id":"claim_001",
   "grain":"entity",
   "fields":["entity_id"],
   "operation":"COUNT(DISTINCT entity_id)",
   "reason":"record count cannot prove entity coverage"
 }],
 "claim_updates":[
   {"claim_id":"claim_001","required_grain":"entity",
    "required_fields":["actual_schema_field"]}
 ],
 "next_action":"accept|query_more|replan|stop",
 "reason":"short reason"
}
"""


def observe_tool_result(
    question: str,
    active_step: str | None,
    ledger: ClaimLedger,
    evidence: EvidenceRecord,
    timeout: float = 45,
) -> DynamicObservation:
    payload = (
        f"USER QUESTION:\n{question}\n\n"
        f"ACTIVE STEP:\n{active_step or '[none]'}\n\n"
        f"CLAIM LEDGER:\n{ledger.render()}\n\n"
        f"EVIDENCE ID: {evidence.evidence_id}\n"
        f"TOOL: {evidence.tool_name}\n"
        f"ARGUMENTS: {json.dumps(evidence.arguments, ensure_ascii=False)}\n"
        f"RESULT:\n{evidence.raw_result[:16_000]}"
    )
    response = llm.chat(
        messages=[
            {"role": "system", "content": DYNAMIC_OBSERVER_SYSTEM},
            {"role": "user", "content": payload},
        ],
        temperature=0,
        timeout=timeout,
        client_max_retries=0,
    )
    data = _json_object(response.choices[0].message.content or "")
    source_text = (
        evidence.raw_result
        + "\n"
        + json.dumps(evidence.arguments, ensure_ascii=False, default=str)
    )
    known_ids = ledger.known_ids
    proved = tuple(
        claim_id for claim_id in map(str, data.get("proved_claim_ids", []))
        if claim_id in known_ids
    )
    contradictions = tuple(
        (str(item.get("claim_id")), str(item.get("reason", "")))
        for item in data.get("contradictions", [])
        if str(item.get("claim_id")) in known_ids
    )
    claim_updates = tuple(
        (
            str(item.get("claim_id")),
            str(item.get("required_grain", "unknown")),
            tuple(map(str, item.get("required_fields", []))),
        )
        for item in data.get("claim_updates", [])
        if str(item.get("claim_id")) in known_ids
    )
    facts = []
    for item in data.get("facts", []):
        subject = str(item.get("subject", ""))
        value = item.get("value")
        derivation = (
            str(item["derivation"])
            if item.get("derivation") is not None
            else None
        )
        if not derivation and (
            not _appears_in_evidence(subject, source_text)
            or not _appears_in_evidence(value, source_text)
        ):
            continue
        proposed_unit = (
            str(item["unit"])
            if item.get("unit") is not None
            else None
        )
        grounded_unit = (
            proposed_unit
            if _appears_in_evidence(proposed_unit, source_text)
            else None
        )
        facts.append(EvidenceFact(
            subject=subject,
            predicate=str(item.get("predicate", "")),
            value=value,
            unit=grounded_unit,
            grain=str(item.get("grain", data.get("grain", "unknown"))),
            evidence_id=evidence.evidence_id,
            derivation=derivation,
        ))
    grounded_fields = tuple(
        field for field in map(str, data.get("fields", []))
        if _appears_in_evidence(field, source_text)
    )
    grounded_labels = tuple(
        label for label in map(str, data.get("canonical_labels", []))
        if _appears_in_evidence(label, evidence.raw_result)
    )
    missing_requests = []
    for item in data.get("missing_evidence", []):
        if isinstance(item, str):
            missing_requests.append(MissingEvidenceRequest(
                claim_id="",
                grain="unknown",
                fields=(),
                operation=item,
                reason=item,
            ))
            continue
        claim_id = str(item.get("claim_id", ""))
        if claim_id and claim_id not in known_ids:
            continue
        missing_requests.append(MissingEvidenceRequest(
            claim_id=claim_id,
            grain=str(item.get("grain", "unknown")),
            fields=tuple(map(str, item.get("fields", []))),
            operation=str(item.get("operation", "")),
            reason=str(item.get("reason", "")),
        ))
    next_action = NextAction(data.get("next_action", "query_more"))
    reason = str(data.get("reason", ""))
    if next_action is NextAction.QUERY_MORE and not missing_requests:
        next_action = NextAction.REPLAN
        reason = (
            "query_more rejected because no structured missing-evidence "
            "request was supplied"
        )
    return DynamicObservation(
        evidence_id=evidence.evidence_id,
        action_succeeded=bool(data.get("action_succeeded")),
        supports_active_step=bool(data.get("supports_active_step")),
        evidence_complete=bool(data.get("evidence_complete")),
        grain=str(data.get("grain", "unknown")),
        fields=grounded_fields,
        canonical_labels=grounded_labels,
        facts=tuple(facts),
        proved_claim_ids=proved,
        contradictions=contradictions,
        missing_evidence=tuple(missing_requests),
        claim_updates=claim_updates,
        next_action=next_action,
        reason=reason,
    )
