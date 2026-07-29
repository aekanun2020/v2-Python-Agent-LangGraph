"""Generic claim requirements and evidence status for Phase 2B."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaimStatus(str, Enum):
    REQUIRED = "required"
    PROVED = "proved"
    CONTRADICTED = "contradicted"


@dataclass
class ClaimRequirement:
    claim_id: str
    description: str
    required_grain: str
    required_fields: tuple[str, ...] = ()
    status: ClaimStatus = ClaimStatus.REQUIRED
    evidence_ids: list[str] = field(default_factory=list)
    contradiction: str | None = None


@dataclass
class ClaimLedger:
    claims: list[ClaimRequirement] = field(default_factory=list)

    @property
    def known_ids(self) -> set[str]:
        return {claim.claim_id for claim in self.claims}

    def mark_proved(self, claim_ids: list[str], evidence_id: str) -> None:
        for claim in self.claims:
            if claim.claim_id not in claim_ids:
                continue
            claim.status = ClaimStatus.PROVED
            if evidence_id not in claim.evidence_ids:
                claim.evidence_ids.append(evidence_id)

    def mark_contradicted(
        self,
        contradictions: dict[str, str],
        evidence_id: str,
    ) -> None:
        for claim in self.claims:
            reason = contradictions.get(claim.claim_id)
            if reason is None:
                continue
            claim.status = ClaimStatus.CONTRADICTED
            claim.contradiction = reason
            if evidence_id not in claim.evidence_ids:
                claim.evidence_ids.append(evidence_id)

    def revise_requirements(
        self,
        updates: dict[str, tuple[str, tuple[str, ...]]],
    ) -> None:
        """Apply schema-grounded grain/field corrections to existing claims."""
        for claim in self.claims:
            update = updates.get(claim.claim_id)
            if update is None or claim.status is not ClaimStatus.REQUIRED:
                continue
            grain, fields = update
            claim.required_grain = grain
            claim.required_fields = fields

    def render(self) -> str:
        if not self.claims:
            return "[no claims]"
        lines = []
        for claim in self.claims:
            lines.append(
                f"- {claim.claim_id} [{claim.status.value}] "
                f"{claim.description} | grain={claim.required_grain} | "
                f"fields={list(claim.required_fields)} | "
                f"evidence={claim.evidence_ids}"
                + (
                    f" | contradiction={claim.contradiction}"
                    if claim.contradiction
                    else ""
                )
            )
        return "\n".join(lines)
