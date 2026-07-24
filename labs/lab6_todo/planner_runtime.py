"""Pure Python planner runtime for Lab 6 — no LangGraph dependency.

The LLM may propose plans and reviews, but Python owns state transitions and the
evidence gate.  A step cannot become completed without an observed tool result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
import uuid

from labs.lab6_todo.observation_types import (
    EvidenceRecord, EvidenceRequirement, ResourceRequirement,
)
from labs.lab6_todo.capabilities import action_resource_error

StepStatus = Literal["pending", "in_progress", "completed", "blocked"]
CompletionMode = Literal["answer", "replan"]


@dataclass
class PlanStep:
    id: int
    description: str
    status: StepStatus = "pending"
    evidence: list[EvidenceRecord] = field(default_factory=list)
    required_capability: str | None = None
    evidence_requirements: list[EvidenceRequirement] = field(default_factory=list)
    required_resources: list[ResourceRequirement] = field(default_factory=list)


@dataclass
class PlannerState:
    goal: str
    steps: list[PlanStep]
    assumptions: list[str] = field(default_factory=list)
    revision: int = 1
    last_reason: str = "initial plan"
    answer_approved: bool = False
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    completion_mode: CompletionMode = "answer"

    def step(self, step_id: int) -> PlanStep:
        match = next((step for step in self.steps if step.id == step_id), None)
        if match is None:
            raise ValueError(f"unknown step id {step_id}; use a step id from current PlannerState")
        return match

    def start(self, step_id: int) -> bool:
        target = self.step(step_id)
        if target.status == "completed" and target.evidence:
            return False
        if target.status not in ("pending", "in_progress"):
            raise ValueError(f"step {step_id} cannot start from {target.status}")
        for step in self.steps:
            if step.status == "in_progress" and step.id != step_id:
                raise ValueError(f"step {step.id} is already in progress")
        reusable = self._reusable_evidence(target)
        if reusable is not None:
            source, derived = reusable
            target.evidence.append(EvidenceRecord(
                evidence_id=str(uuid.uuid4()), plan_id=self.plan_id,
                plan_revision=self.revision, step_id=target.id, tool=source.tool,
                tool_call_id=source.tool_call_id, action=dict(source.action),
                result=source.result,
                proven_claim_ids=(
                    [item.claim_id for item in target.evidence_requirements]
                    if derived else list(source.proven_claim_ids)
                ),
                claim_requirements=(
                    [item.as_dict() for item in target.evidence_requirements]
                    if derived else list(source.claim_requirements)
                ),
                bound_resources=(
                    [item.as_dict() for item in target.required_resources]
                    if derived else list(source.bound_resources)
                ),
                required_capability=target.required_capability,
                reused_from_evidence_id=source.evidence_id,
                observation=source.observation,
            ))
            target.status = "completed"
            return True
        target.status = "in_progress"
        return False

    def _reusable_evidence(self, target: PlanStep) -> tuple[EvidenceRecord, bool] | None:
        """Reuse only exact claims backed by compatible capability and resources."""
        claim_signatures = {
            (item.claim_id, item.predicate, item.target)
            for item in target.evidence_requirements
        }
        resources = {f"{item.kind}:{item.name.lower()}" for item in target.required_resources}
        if not claim_signatures or not resources:
            return None
        for evidence in self.accepted_evidence:
            bound = {
                f"{item.get('kind')}:{str(item.get('name', '')).lower()}"
                for item in evidence.bound_resources
            }
            proven_signatures = {
                (str(item.get("claim_id", "")), str(item.get("predicate", "")),
                 str(item.get("target", "")))
                for item in evidence.claim_requirements
                if item.get("claim_id") in evidence.proven_claim_ids
            }
            if (claim_signatures <= proven_signatures
                    and resources <= bound
                    and target.required_capability == evidence.required_capability):
                return evidence, False
        # A broad accepted schema payload may entail newly declared schema claims
        # after catalog discovery. This is structural rebinding, not text-intent guessing.
        if (target.required_capability == "schema_inspection"
                and all(item.predicate == "schema_inspected"
                        for item in target.evidence_requirements)):
            for evidence in self.accepted_evidence:
                if evidence.required_capability != "schema_inspection":
                    continue
                if action_resource_error(
                    evidence.tool, evidence.action, evidence.result,
                    target.required_resources,
                ) is None:
                    return evidence, True
        return None

    def reuse_pending_evidence(self) -> list[tuple[int, str]]:
        """Complete redundant pending steps from exact typed evidence signatures."""
        reused: list[tuple[int, str]] = []
        for target in self.steps:
            if target.status != "pending":
                continue
            reusable = self._reusable_evidence(target)
            if reusable is None:
                continue
            evidence, derived = reusable
            target.evidence.append(EvidenceRecord(
                evidence_id=str(uuid.uuid4()), plan_id=self.plan_id,
                plan_revision=self.revision, step_id=target.id, tool=evidence.tool,
                tool_call_id=evidence.tool_call_id, action=dict(evidence.action),
                result=evidence.result,
                proven_claim_ids=(
                    [item.claim_id for item in target.evidence_requirements]
                    if derived else list(evidence.proven_claim_ids)
                ),
                claim_requirements=(
                    [item.as_dict() for item in target.evidence_requirements]
                    if derived else list(evidence.claim_requirements)
                ),
                bound_resources=(
                    [item.as_dict() for item in target.required_resources]
                    if derived else list(evidence.bound_resources)
                ),
                required_capability=target.required_capability,
                reused_from_evidence_id=evidence.evidence_id,
                observation=evidence.observation,
            ))
            target.status = "completed"
            reused.append((target.id, evidence.evidence_id))
        return reused

    def observe(self, step_id: int, *, tool: str, tool_call_id: str, result: str,
                observation: dict | None = None, action: dict | None = None,
                proven_claim_ids: list[str] | None = None) -> None:
        target = self.step(step_id)
        if target.status != "in_progress":
            raise ValueError("tool evidence must belong to the in-progress step")
        if not result.strip():
            raise ValueError("empty tool results are not evidence")
        target.evidence.append(EvidenceRecord(
            evidence_id=str(uuid.uuid4()), plan_id=self.plan_id,
            plan_revision=self.revision, step_id=step_id, tool=tool,
            tool_call_id=tool_call_id, action=action or {}, result=result,
            proven_claim_ids=proven_claim_ids or [], observation=observation,
            claim_requirements=[item.as_dict() for item in target.evidence_requirements],
            bound_resources=[item.as_dict() for item in target.required_resources],
            required_capability=target.required_capability,
        ))

    @property
    def accepted_evidence(self) -> list[EvidenceRecord]:
        return [evidence for step in self.steps for evidence in step.evidence]

    def complete(self, step_id: int) -> None:
        target = self.step(step_id)
        if target.status == "completed" and target.evidence:
            return
        if target.status != "in_progress":
            raise ValueError("only an in-progress step can be completed")
        if not target.evidence:
            raise ValueError("cannot complete a step without tool evidence")
        target.status = "completed"

    def revise(self, steps: list[PlanStep], reason: str,
               completion_mode: CompletionMode = "answer") -> None:
        """Replace future work while preserving evidence for matching step ids."""
        old = {step.id: step for step in self.steps}
        proposed_ids = {step.id for step in steps}
        if len(proposed_ids) != len(steps):
            raise ValueError("revised plan contains duplicate step ids")
        for step in steps:
            previous = old.get(step.id)
            if previous and previous.evidence:
                step.evidence = list(previous.evidence)
            if previous and previous.status == "completed" and previous.evidence:
                # A model may revise future work, but cannot reopen accepted work.
                step.status = "completed"
                step.description = previous.description
                step.required_capability = previous.required_capability
                step.evidence_requirements = list(previous.evidence_requirements)
                step.required_resources = list(previous.required_resources)
            if step.status == "completed" and not step.evidence:
                step.status = "pending"
        for previous in old.values():
            if (previous.id not in proposed_ids and previous.status == "completed"
                    and previous.evidence):
                steps.append(PlanStep(
                    id=previous.id, description=previous.description,
                    status="completed", evidence=list(previous.evidence),
                    required_capability=previous.required_capability,
                    evidence_requirements=list(previous.evidence_requirements),
                    required_resources=list(previous.required_resources),
                ))
        active_seen = False
        for step in sorted(steps, key=lambda item: item.id):
            if step.status == "in_progress":
                if active_seen:
                    step.status = "pending"
                active_seen = True
        steps.sort(key=lambda item: item.id)
        self.steps = steps
        self.revision += 1
        self.last_reason = reason
        self.answer_approved = False
        self.completion_mode = completion_mode

    def approve_answer(self) -> None:
        if self.completion_mode != "answer":
            raise ValueError(
                "answer gate rejected: completion_mode=replan requires plan revision"
            )
        incomplete = [step.id for step in self.steps if step.status != "completed"]
        unsupported = [step.id for step in self.steps if not step.evidence]
        if incomplete or unsupported:
            raise ValueError(
                f"answer gate rejected: incomplete={incomplete}, unsupported={unsupported}"
            )
        self.answer_approved = True

    def render(self) -> str:
        lines = [f"Goal: {self.goal}", f"Revision: {self.revision}",
                 f"Completion mode: {self.completion_mode}"]
        for step in self.steps:
            lines.append(
                f"[{step.status}] {step.id}. {step.description} "
                f"(capability={step.required_capability or 'unspecified'}, "
                f"requirements={len(step.evidence_requirements)}, "
                f"resources={len(step.required_resources)}, "
                f"evidence={len(step.evidence)})"
            )
        return "\n".join(lines)
