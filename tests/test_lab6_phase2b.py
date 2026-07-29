import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from labs.lab6_todo.agent_todo import dispatch_with_retry
from labs.lab6_todo.claim_ledger import (
    ClaimLedger,
    ClaimRequirement,
    ClaimStatus,
)
from labs.lab6_todo.dynamic_observer import (
    NextAction,
    observe_tool_result,
)
from labs.lab6_todo.evidence_state import EvidenceRecord, EvidenceState


def fake_response(payload: dict):
    message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class Phase2BTests(unittest.TestCase):
    @staticmethod
    def http_error(status: int) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "https://example.test/mcp")
        response = httpx.Response(status, request=request)
        return httpx.HTTPStatusError(
            f"status {status}",
            request=request,
            response=response,
        )

    def test_claim_ledger_tracks_proof_and_contradiction_by_known_id(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "count active employees by department",
                "department",
                ("department", "employee_count"),
            ),
            ClaimRequirement("claim_002", "approval decision exists", "metadata"),
        ])
        ledger.mark_proved(["claim_001", "unknown"], "call-1")
        ledger.mark_contradicted(
            {"claim_002": "schema has no decision field", "unknown": "ignored"},
            "call-2",
        )
        self.assertEqual(ledger.claims[0].status, ClaimStatus.PROVED)
        self.assertEqual(ledger.claims[0].evidence_ids, ["call-1"])
        self.assertEqual(ledger.claims[1].status, ClaimStatus.CONTRADICTED)
        self.assertEqual(ledger.claims[1].evidence_ids, ["call-2"])

    def test_claim_requirements_can_be_revised_from_schema(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "count employees",
                "entity",
                ("entity_id", "department_id"),
            )
        ])
        ledger.revise_requirements({
            "claim_001": (
                "employee",
                ("employee_id", "department"),
            )
        })
        self.assertEqual(ledger.claims[0].required_grain, "employee")
        self.assertEqual(
            ledger.claims[0].required_fields,
            ("employee_id", "department"),
        )

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_dynamic_observer_extracts_facts_and_filters_unknown_claims(
        self,
        chat,
    ):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": True,
            "grain": "department",
            "fields": ["department", "employee_count"],
            "canonical_labels": ["ผลิต"],
            "facts": [{
                "subject": "ผลิต",
                "predicate": "employee_count",
                "value": 3,
                "unit": "person",
                "grain": "department",
                "derivation": None,
            }],
            "proved_claim_ids": ["claim_001", "invented_claim"],
            "contradictions": [],
            "missing_evidence": [],
            "next_action": "accept",
            "reason": "grouped count returned",
        })
        ledger = ClaimLedger([
            ClaimRequirement("claim_001", "count by department", "department")
        ])
        record = EvidenceRecord.from_tool(
            "call-1",
            "execute_query_tool",
            {"query": "SELECT department, COUNT(*) FROM employees"},
            "department employee_count\nผลิต 3",
        )
        observation = observe_tool_result(
            "นับพนักงานแยกแผนก",
            "query grouped count",
            ledger,
            record,
        )
        self.assertEqual(observation.next_action, NextAction.ACCEPT)
        self.assertEqual(observation.proved_claim_ids, ("claim_001",))
        self.assertEqual(observation.facts[0].evidence_id, "call-1")
        self.assertEqual(observation.canonical_labels, ("ผลิต",))

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_query_more_names_specific_missing_evidence(self, chat):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": False,
            "grain": "record",
            "fields": ["review_id"],
            "canonical_labels": [],
            "facts": [],
            "proved_claim_ids": [],
            "contradictions": [],
            "missing_evidence": ["COUNT(DISTINCT employee_id) for 2023"],
            "next_action": "query_more",
            "reason": "record count cannot prove employee coverage",
        })
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001", "distinct employee coverage", "employee"
            )
        ])
        observation = observe_tool_result(
            "คำนวณ employee coverage",
            "count reviews",
            ledger,
            EvidenceRecord.from_tool(
                "call-2", "execute_query_tool", {}, "review_count=7"
            ),
        )
        self.assertEqual(observation.next_action, NextAction.QUERY_MORE)
        self.assertIn("COUNT(DISTINCT", observation.missing_evidence[0])

    def test_evidence_state_renders_structured_observation(self):
        state = EvidenceState()
        state.accept(EvidenceRecord.from_tool(
            "call-3", "query", {}, "department=ผลิต,n=3"
        ))
        # Reuse a minimal duck-typed observation to ensure storage stays
        # independent from the LLM orchestration module.
        fact = SimpleNamespace(
            subject="ผลิต",
            predicate="employee_count",
            value=3,
            unit="person",
            grain="department",
            evidence_id="call-3",
            derivation=None,
        )
        observation = SimpleNamespace(
            evidence_id="call-3",
            action_succeeded=True,
            supports_active_step=True,
            evidence_complete=True,
            grain="department",
            fields=("department", "employee_count"),
            canonical_labels=("ผลิต",),
            facts=(fact,),
            proved_claim_ids=("claim_001",),
            contradictions=(),
            missing_evidence=(),
            claim_updates=(),
            next_action=NextAction.ACCEPT,
            reason="complete",
        )
        state.add_observation(observation)
        rendered = state.render_structured()
        self.assertIn('"grain": "department"', rendered)
        self.assertIn('"evidence_id": "call-3"', rendered)

    @patch("labs.lab6_todo.agent_todo.time.sleep")
    def test_mcp_retry_recovers_from_transient_503(self, sleep):
        registry = SimpleNamespace()
        registry.dispatch = unittest.mock.Mock(side_effect=[
            self.http_error(503),
            "rows",
        ])
        result = dispatch_with_retry(registry, "query", {})
        self.assertEqual(result, "rows")
        self.assertEqual(registry.dispatch.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("labs.lab6_todo.agent_todo.time.sleep")
    def test_mcp_retry_does_not_retry_permanent_400(self, sleep):
        registry = SimpleNamespace()
        registry.dispatch = unittest.mock.Mock(
            side_effect=self.http_error(400)
        )
        with self.assertRaises(httpx.HTTPStatusError):
            dispatch_with_retry(registry, "query", {})
        self.assertEqual(registry.dispatch.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
