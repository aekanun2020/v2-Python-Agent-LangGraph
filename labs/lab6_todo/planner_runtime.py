"""Pure Python planner runtime for Lab 6 — no LangGraph dependency.

The LLM may propose plans and reviews, but Python owns state transitions and the
evidence gate.  A step cannot become completed without an observed tool result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StepStatus = Literal["pending", "in_progress", "completed", "blocked"]


@dataclass
class Evidence:
    tool: str
    tool_call_id: str
    result: str
    observation: dict | None = None


@dataclass
class PlanStep:
    id: int
    description: str
    status: StepStatus = "pending"
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class PlannerState:
    goal: str
    steps: list[PlanStep]
    assumptions: list[str] = field(default_factory=list)
    revision: int = 1
    last_reason: str = "initial plan"
    answer_approved: bool = False

    def step(self, step_id: int) -> PlanStep:
        match = next((step for step in self.steps if step.id == step_id), None)
        if match is None:
            raise ValueError(f"unknown step id {step_id}; use a step id from current PlannerState")
        return match

    def start(self, step_id: int) -> None:
        target = self.step(step_id)
        if target.status == "completed" and target.evidence:
            return
        if target.status not in ("pending", "in_progress"):
            raise ValueError(f"step {step_id} cannot start from {target.status}")
        for step in self.steps:
            if step.status == "in_progress" and step.id != step_id:
                raise ValueError(f"step {step.id} is already in progress")
        target.status = "in_progress"

    def observe(self, step_id: int, *, tool: str, tool_call_id: str, result: str,
                observation: dict | None = None) -> None:
        target = self.step(step_id)
        if target.status != "in_progress":
            raise ValueError("tool evidence must belong to the in-progress step")
        if not result.strip():
            raise ValueError("empty tool results are not evidence")
        target.evidence.append(Evidence(tool, tool_call_id, result, observation))

    def complete(self, step_id: int) -> None:
        target = self.step(step_id)
        if target.status == "completed" and target.evidence:
            return
        if target.status != "in_progress":
            raise ValueError("only an in-progress step can be completed")
        if not target.evidence:
            raise ValueError("cannot complete a step without tool evidence")
        target.status = "completed"

    def revise(self, steps: list[PlanStep], reason: str) -> None:
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
            if step.status == "completed" and not step.evidence:
                step.status = "pending"
        for previous in old.values():
            if (previous.id not in proposed_ids and previous.status == "completed"
                    and previous.evidence):
                steps.append(PlanStep(
                    previous.id, previous.description, "completed", list(previous.evidence)
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

    def approve_answer(self) -> None:
        incomplete = [step.id for step in self.steps if step.status != "completed"]
        unsupported = [step.id for step in self.steps if not step.evidence]
        if incomplete or unsupported:
            raise ValueError(
                f"answer gate rejected: incomplete={incomplete}, unsupported={unsupported}"
            )
        self.answer_approved = True

    def render(self) -> str:
        lines = [f"Goal: {self.goal}", f"Revision: {self.revision}"]
        for step in self.steps:
            lines.append(
                f"[{step.status}] {step.id}. {step.description} "
                f"(evidence={len(step.evidence)})"
            )
        return "\n".join(lines)
