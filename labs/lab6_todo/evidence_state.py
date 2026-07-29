"""Evidence and semantic-observation state for the Pure Python Lab 6 agent."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SemanticVerdict(str, Enum):
    APPROVE = "approve"
    REWRITE = "rewrite"
    QUERY_MORE = "query_more"
    REFUSE_DECISION = "refuse_decision"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    tool_name: str
    arguments: dict[str, Any]
    raw_result: str
    result_hash: str

    @classmethod
    def from_tool(
        cls,
        evidence_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> "EvidenceRecord":
        raw = result if isinstance(result, str) else json.dumps(
            result, ensure_ascii=False, default=str
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return cls(evidence_id, tool_name, arguments, raw, digest)


@dataclass
class EvidenceState:
    """Append-only accepted tool evidence; no domain-specific interpretation."""

    records: list[EvidenceRecord] = field(default_factory=list)

    def accept(self, record: EvidenceRecord) -> None:
        if all(item.evidence_id != record.evidence_id for item in self.records):
            self.records.append(record)

    def render_for_review(
        self,
        max_total_chars: int = 40_000,
        max_record_chars: int = 14_000,
    ) -> str:
        """Pack newest evidence first under a bounded reviewer context."""
        blocks: list[str] = []
        used = 0
        for record in reversed(self.records):
            result = record.raw_result[:max_record_chars]
            block = (
                f"EVIDENCE_ID: {record.evidence_id}\n"
                f"TOOL: {record.tool_name}\n"
                f"ARGUMENTS: {json.dumps(record.arguments, ensure_ascii=False, default=str)}\n"
                f"RESULT:\n{result}"
            )
            if used + len(block) > max_total_chars:
                continue
            blocks.append(block)
            used += len(block)
        blocks.reverse()
        return "\n\n---\n\n".join(blocks)


@dataclass(frozen=True)
class ObservationState:
    verdict: SemanticVerdict
    reason: str
    supported_claims: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    revised_answer: str | None = None

