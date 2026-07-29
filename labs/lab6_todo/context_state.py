"""Pure Python context state and deterministic drift signals for Lab 6.

Phase 1 intentionally has no LLM, embedding, summarizer, or persistence.
It observes the existing agent loop without changing tool decisions.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentPhase(str, Enum):
    PLAN = "plan"
    ACT = "act"
    ANSWER = "answer"


class ActionKind(str, Enum):
    PLAN = "plan"
    STATE_UPDATE = "state_update"
    TOOL = "tool"
    ANSWER = "answer"


@dataclass(frozen=True)
class ActionSignature:
    tool_name: str
    arguments_hash: str


@dataclass
class BudgetState:
    steps: int = 0
    tool_calls: int = 0
    errors: int = 0


@dataclass
class DriftReport:
    repeated_action_result: bool = False
    repeated_error: bool = False
    phase_violation: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def alert(self) -> bool:
        return bool(self.reasons)


@dataclass
class ContextState:
    """Hot control state plus lightweight references needed by the loop."""

    original_goal: str
    phase: AgentPhase = AgentPhase.PLAN
    active_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    accepted_evidence_refs: list[str] = field(default_factory=list)
    budgets: BudgetState = field(default_factory=BudgetState)
    recent_action_results: deque[tuple[ActionSignature, str]] = field(
        default_factory=lambda: deque(maxlen=8)
    )
    recent_error_signatures: deque[str] = field(
        default_factory=lambda: deque(maxlen=8)
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "original_goal" and "original_goal" in self.__dict__:
            raise AttributeError("original_goal is immutable")
        super().__setattr__(name, value)

    @staticmethod
    def _stable_hash(value: Any) -> str:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def action_signature(
        cls,
        tool_name: str,
        arguments: dict,
    ) -> ActionSignature:
        return ActionSignature(tool_name, cls._stable_hash(arguments))

    @classmethod
    def result_signature(cls, result: Any) -> str:
        return cls._stable_hash(result)

    @classmethod
    def error_signature(cls, error: BaseException) -> str:
        return f"{type(error).__name__}:{cls._stable_hash(str(error))}"

    def set_phase(self, phase: AgentPhase) -> None:
        self.phase = phase

    def start_step(self, text: str) -> None:
        self.active_step = text
        self.phase = AgentPhase.ACT

    def complete_step(self, text: str) -> None:
        if text not in self.completed_steps:
            self.completed_steps.append(text)
        if self.active_step == text:
            self.active_step = None

    def add_evidence_ref(self, reference: str) -> None:
        if reference not in self.accepted_evidence_refs:
            self.accepted_evidence_refs.append(reference)

    def check_phase(self, kind: ActionKind) -> bool:
        allowed = {
            AgentPhase.PLAN: {ActionKind.PLAN, ActionKind.ANSWER},
            AgentPhase.ACT: {
                ActionKind.PLAN,
                ActionKind.STATE_UPDATE,
                ActionKind.TOOL,
                ActionKind.ANSWER,
            },
            AgentPhase.ANSWER: {ActionKind.ANSWER},
        }
        return kind in allowed[self.phase]

    def observe_action(
        self,
        tool_name: str,
        arguments: dict,
        result: Any,
        kind: ActionKind = ActionKind.TOOL,
        repeat_threshold: int = 2,
    ) -> DriftReport:
        """Record one successful action and report deterministic drift only."""
        self.budgets.steps += 1
        if kind is ActionKind.TOOL:
            self.budgets.tool_calls += 1
        signature = self.action_signature(tool_name, arguments)
        result_signature = self.result_signature(result)
        pair = (signature, result_signature)
        previous_count = Counter(self.recent_action_results)[pair]
        self.recent_action_results.append(pair)

        report = DriftReport()
        if previous_count + 1 >= repeat_threshold:
            report.repeated_action_result = True
            report.reasons.append(
                "repeated_action_result: tool, arguments, and result repeated"
            )
        if not self.check_phase(kind):
            report.phase_violation = True
            report.reasons.append(
                f"phase_violation: {kind.value} is not allowed in {self.phase.value}"
            )
        return report

    def observe_error(
        self,
        error: BaseException,
        repeat_threshold: int = 2,
    ) -> DriftReport:
        self.budgets.errors += 1
        signature = self.error_signature(error)
        previous_count = Counter(self.recent_error_signatures)[signature]
        self.recent_error_signatures.append(signature)
        report = DriftReport()
        if previous_count + 1 >= repeat_threshold:
            report.repeated_error = True
            report.reasons.append(
                "repeated_error: identical exception type and message repeated"
            )
        return report
