"""Generic repeated-observation failure breaker."""

from __future__ import annotations

import json
from collections import Counter


class FailureCircuitBreaker:
    def __init__(self, replan_after: int = 3, stop_after: int = 5):
        self.replan_after = replan_after
        self.stop_after = stop_after
        self._counts: Counter[str] = Counter()

    @staticmethod
    def signature(step_id: int, tool: str, decision: str, failed: list[str]) -> str:
        return json.dumps([step_id, tool, decision, sorted(failed)], ensure_ascii=False)

    def record(self, *, step_id: int, tool: str, decision: str,
               failed: list[str]) -> tuple[int, str | None]:
        signature = self.signature(step_id, tool, decision, failed)
        self._counts[signature] += 1
        count = self._counts[signature]
        if count >= self.stop_after:
            return count, "stop"
        if count >= self.replan_after:
            return count, "replan"
        return count, None

    def clear_step(self, step_id: int) -> None:
        prefix = f"[{step_id},"
        for signature in list(self._counts):
            if signature.startswith(prefix):
                del self._counts[signature]
