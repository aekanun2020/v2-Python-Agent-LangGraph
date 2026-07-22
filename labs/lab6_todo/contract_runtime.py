"""Load small declarative domain contracts without teaching the core their vocabulary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from labs.lab6_todo.observation_types import Claim

CONTRACT_DIR = Path(__file__).with_name("contracts")


@dataclass(frozen=True)
class ResolvedContract:
    id: str
    prompt_rules: list[str] = field(default_factory=list)
    observation_claims: list[dict] = field(default_factory=list)
    final_rules: list[dict] = field(default_factory=list)

    @property
    def system_context(self) -> str:
        if not self.prompt_rules:
            return ""
        return "[DYNAMIC GOAL CONTRACT — runtime authority]\n" + "\n".join(
            f"- {rule}" for rule in self.prompt_rules
        )


def _contract_files() -> list[Path]:
    return sorted(CONTRACT_DIR.glob("*.json")) if CONTRACT_DIR.exists() else []


def resolve_contract(question: str) -> ResolvedContract | None:
    lowered = question.lower()
    for path in _contract_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        match = data.get("match", {})
        any_groups = match.get("all_groups", [])
        if any_groups and all(any(alias.lower() in lowered for alias in group) for group in any_groups):
            return ResolvedContract(
                id=str(data["id"]),
                prompt_rules=list(data.get("prompt_rules", [])),
                observation_claims=list(data.get("observation_claims", [])),
                final_rules=list(data.get("final_rules", [])),
            )
    return None


def evaluate_action_claims(contract: ResolvedContract | None, *, sql: str) -> list[Claim]:
    if contract is None:
        return []
    normalized = re.sub(r"\s+", " ", sql).lower()
    claims: list[Claim] = []
    for spec in contract.observation_claims:
        checks = spec.get("checks", {})
        ok = all(token.lower() in normalized for token in checks.get("contains_all", []))
        ok = ok and all(
            any(token.lower() in normalized for token in group)
            for group in checks.get("contains_any_groups", [])
        )
        ok = ok and all(token.lower() not in normalized for token in checks.get("excludes_all", []))
        ok = ok and all(re.search(pattern, normalized) for pattern in checks.get("regex_all", []))
        claims.append(Claim(
            id=str(spec["id"]),
            type=str(spec.get("type", "action_contract")),
            description=str(spec.get("description", spec["id"])),
            status="proven" if ok else "unsupported",
            basis="declarative action checks passed" if ok else str(spec.get("hint", "contract check failed")),
        ))
    return claims


def validate_final_contract(contract: ResolvedContract | None, answer: str,
                            evidence_queries: str = "") -> list[str]:
    if contract is None:
        return []
    text = answer.lower()
    failures: list[str] = []
    for rule in contract.final_rules:
        pattern = str(rule.get("pattern", ""))
        if pattern and re.search(pattern, text, re.IGNORECASE):
            required = rule.get("requires_query", {})
            if required:
                contains = all(token.lower() in evidence_queries for token in required.get("contains_all", []))
                contains = contains and all(
                    any(token.lower() in evidence_queries for token in group)
                    for group in required.get("contains_any_groups", [])
                )
                if contains:
                    continue
            failures.append(str(rule.get("message", "final claim violates contract")))
    return failures


def validate_reviewer_action(
    contract: ResolvedContract | None, *, decision: str, reason: str,
    suggested_next_action: str,
) -> list[str]:
    """Reject a non-accept reviewer instruction that violates runtime authority."""
    if decision == "accept" or contract is None:
        return []
    instruction = suggested_next_action.strip() or reason.strip()
    if not instruction:
        return []
    return validate_final_contract(contract, instruction)
