"""Typed claims and evidence shared by the generic TAO observation runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

ClaimStatus = Literal["proven", "contradicted", "unsupported"]


@dataclass(frozen=True)
class ResourceRequirement:
    """A model-declared database resource, independent of domain vocabulary."""

    kind: Literal["table", "field"]
    name: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRequirement:
    """A typed, model-declared condition that accepted evidence must satisfy."""

    claim_id: str
    predicate: str
    target: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Claim:
    id: str
    type: str
    description: str
    status: ClaimStatus
    basis: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceRecord:
    evidence_id: str
    plan_id: str
    plan_revision: int
    step_id: int
    tool: str
    tool_call_id: str
    action: dict
    result: str
    proven_claim_ids: list[str] = field(default_factory=list)
    claim_requirements: list[dict] = field(default_factory=list)
    bound_resources: list[dict] = field(default_factory=list)
    required_capability: str | None = None
    reused_from_evidence_id: str | None = None
    observation: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ActionHint:
    kind: Literal["retry", "query_more", "replan", "stop"]
    instruction: str
    forbidden_action_signature: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)
