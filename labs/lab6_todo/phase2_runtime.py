"""Deterministic budgets and termination for the Phase 2B orchestration."""
from __future__ import annotations

import time
from dataclasses import dataclass


class RuntimeBudgetExhausted(RuntimeError):
    pass


@dataclass
class Phase2Budget:
    max_seconds: float = 240.0
    max_agent_calls: int = 18
    max_observer_calls: int = 6
    max_final_reviews: int = 2
    max_mcp_calls: int = 12
    started_at: float = 0.0
    agent_calls: int = 0
    observer_calls: int = 0
    final_reviews: int = 0
    mcp_calls: int = 0

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - self.elapsed)

    def _consume(self, field: str, maximum: int, phase: str) -> None:
        self.check_time()
        value = getattr(self, field)
        if value >= maximum:
            raise RuntimeBudgetExhausted(f"{phase} budget exhausted")
        setattr(self, field, value + 1)

    def check_time(self) -> None:
        if self.remaining_seconds <= 0:
            raise RuntimeBudgetExhausted("whole-run deadline exhausted")

    def consume_agent(self) -> None:
        self._consume("agent_calls", self.max_agent_calls, "agent LLM")

    def consume_observer(self) -> None:
        self._consume(
            "observer_calls",
            self.max_observer_calls,
            "dynamic observer",
        )

    def consume_final_review(self) -> None:
        self._consume(
            "final_reviews",
            self.max_final_reviews,
            "final observer",
        )

    def consume_mcp(self) -> None:
        self._consume("mcp_calls", self.max_mcp_calls, "MCP")

    def call_timeout(self, cap: float = 60.0) -> float:
        self.check_time()
        return max(1.0, min(cap, self.remaining_seconds))

    def render(self) -> str:
        return (
            f"elapsed={self.elapsed:.1f}/{self.max_seconds:.1f}s "
            f"agent={self.agent_calls}/{self.max_agent_calls} "
            f"observer={self.observer_calls}/{self.max_observer_calls} "
            f"final={self.final_reviews}/{self.max_final_reviews} "
            f"mcp={self.mcp_calls}/{self.max_mcp_calls}"
        )
