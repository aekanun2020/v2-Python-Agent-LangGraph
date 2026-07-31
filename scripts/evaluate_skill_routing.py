"""Evaluate frozen unseen paraphrases and boundary cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from labs.core import config
from labs.core.registry import ToolRegistry
from labs.lab6_todo.evidence_contract import (
    metric_contract_status,
    select_metric_contract,
)
from labs.lab6_todo.evidence_state import EvidenceRecord, EvidenceState


SUITE_DIR = ROOT / "tests" / "evaluation"
SUITE_FILES = (
    "hr_unseen_paraphrases.json",
    "hr_boundaries.json",
    "finance_unseen_paraphrases.json",
    "finance_boundaries.json",
)


def load_cases() -> list[dict]:
    cases: list[dict] = []
    for name in SUITE_FILES:
        payload = json.loads((SUITE_DIR / name).read_text(encoding="utf-8"))
        if payload.get("frozen_before_first_run") is not True:
            raise ValueError(f"suite is not frozen: {name}")
        kind = "boundary" if "boundaries" in name else "paraphrase"
        domain = "hr" if name.startswith("hr_") else "finance"
        for item in payload["cases"]:
            cases.append({**item, "kind": kind, "domain": domain})
    return cases


def evaluate_routing(cases: list[dict]) -> tuple[list[dict], dict]:
    results = []
    for item in cases:
        selected = select_metric_contract(item["question"])
        actual = selected["id"] if selected else None
        passed = actual == item["expected_contract"]
        results.append({
            **item,
            "actual_contract": actual,
            "passed": passed,
        })

    paraphrases = [item for item in results if item["kind"] == "paraphrase"]
    boundaries = [item for item in results if item["kind"] == "boundary"]
    recall_hits = sum(item["passed"] for item in paraphrases)
    protected = sum(item["passed"] for item in boundaries)
    false_matches = sum(item["actual_contract"] is not None for item in boundaries)
    metrics = {
        "paraphrases_total": len(paraphrases),
        "paraphrases_correct": recall_hits,
        "contract_recall": recall_hits / len(paraphrases),
        "boundaries_total": len(boundaries),
        "boundaries_protected": protected,
        "boundary_precision": protected / len(boundaries),
        "false_matches": false_matches,
        "false_match_rate": false_matches / len(boundaries),
    }
    return results, metrics


def evaluate_live(routing_results: list[dict]) -> list[dict]:
    representatives: dict[str, dict] = {}
    for item in routing_results:
        if (
            item["kind"] == "paraphrase"
            and item["passed"]
            and item["actual_contract"]
        ):
            representatives.setdefault(item["actual_contract"], item)

    registry = ToolRegistry()
    discovered = registry.add_server(config.MCP_SERVER_URL)
    live_results = []
    try:
        for contract_id, item in representatives.items():
            contract = select_metric_contract(item["question"])
            evidence = EvidenceState()
            started = time.monotonic()
            role_results = []
            for role in contract["roles"]:
                query = role["query_template"]
                raw = registry.dispatch("execute_query_tool", {"query": query})
                evidence.accept(EvidenceRecord.from_tool(
                    f"{item['id']}:{role['id']}",
                    "execute_query_tool",
                    {"query": query},
                    raw,
                ))
                role_results.append({
                    "role_id": role["id"],
                    "query": query,
                    "result": raw,
                })
            status = metric_contract_status(item["question"], evidence)
            live_results.append({
                "case_id": item["id"],
                "contract_id": contract_id,
                "mcp_tools_discovered": discovered,
                "satisfied": status.satisfied,
                "missing_roles": list(status.missing_roles),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "roles": role_results,
            })
    finally:
        registry.close()
    return live_results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = load_cases()
    routing, metrics = evaluate_routing(cases)
    live = evaluate_live(routing) if args.live else []
    normalized_live = [
        {
            "contract_id": item["contract_id"],
            "satisfied": item["satisfied"],
            "missing_roles": item["missing_roles"],
            "roles": item["roles"],
        }
        for item in live
    ]
    live_evidence_hash = (
        hashlib.sha256(
            json.dumps(
                normalized_live,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if live else None
    )
    report = {
        "suite_version": "unseen-boundary-v1",
        "selector": "literal question_terms_all/any",
        "metrics": metrics,
        "routing_results": routing,
        "live_results": live,
        "live_evidence_hash": live_evidence_hash,
        "live_contract_completion": (
            sum(item["satisfied"] for item in live) / len(live)
            if live else None
        ),
    }

    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    for item in routing:
        marker = "PASS" if item["passed"] else "FAIL"
        print(
            f"{marker} {item['id']}: expected={item['expected_contract']} "
            f"actual={item['actual_contract']}"
        )
    if live:
        passed = sum(item["satisfied"] for item in live)
        print(f"LIVE {passed}/{len(live)} contracts complete")
        print(f"LIVE evidence hash {live_evidence_hash}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
