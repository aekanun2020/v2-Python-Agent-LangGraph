import json
import time
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
from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    ObservationState,
    SemanticVerdict,
    SemanticViolation,
)
from labs.lab6_todo.phase2_runtime import (
    Phase2Budget,
    RuntimeBudgetExhausted,
    hard_deadline,
)
from labs.lab6_todo.semantic_observer import (
    apply_bounded_rewrite,
    enforce_claim_alignment,
)


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

    def test_user_input_constraints_are_preproved_with_provenance(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_policy",
                "threshold and comparison supplied by user",
                "metadata",
                ("threshold", "comparison_operator"),
                evidence_source="user_input",
            ),
            ClaimRequirement(
                "claim_data",
                "retrieved aggregate",
                "aggregate",
                ("total",),
            ),
        ])
        ledger.accept_user_input_claims()
        self.assertEqual(
            ledger.claims[0].status,
            ClaimStatus.PROVED,
        )
        self.assertEqual(
            ledger.claims[0].evidence_ids,
            ["user_question"],
        )
        self.assertEqual(
            ledger.claims[1].status,
            ClaimStatus.REQUIRED,
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
            "missing_evidence": [{
                "claim_id": "claim_001",
                "grain": "employee",
                "fields": ["employee_id"],
                "operation": "COUNT(DISTINCT employee_id)",
                "reason": "record count cannot prove employee coverage",
            }],
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
        request = observation.missing_evidence[0]
        self.assertEqual(request.claim_id, "claim_001")
        self.assertEqual(request.grain, "employee")
        self.assertIn("COUNT(DISTINCT", request.operation)

    def test_claim_proof_requires_matching_grain_and_fields(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "distinct employee coverage",
                "employee",
                ("employee_id", "coverage"),
            )
        ])
        rejected = ledger.mark_proved_if_covered(
            ["claim_001"],
            "call-records",
            "record",
            ("review_id", "coverage"),
        )
        self.assertEqual(rejected, ())
        self.assertEqual(ledger.claims[0].status, ClaimStatus.REQUIRED)

        accepted = ledger.mark_proved_if_covered(
            ["claim_001"],
            "call-employees",
            "employee",
            ("employee_id", "coverage"),
        )
        self.assertEqual(accepted, ("claim_001",))
        self.assertTrue(ledger.complete)

    def test_bounded_rewrite_applies_exact_violations_once(self):
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="unsupported currency",
            violations=(
                SemanticViolation("unit", " บาท", ""),
            ),
            revised_answer="มูลค่ารวม 28,000,000 บาท",
        )
        result = apply_bounded_rewrite("ignored", observation)
        self.assertEqual(result, "มูลค่ารวม 28,000,000")

    def test_final_approval_is_downgraded_for_unresolved_claims(self):
        ledger = ClaimLedger([
            ClaimRequirement("claim_001", "needs evidence", "entity")
        ])
        approved = ObservationState(
            verdict=SemanticVerdict.APPROVE,
            reason="looks correct",
        )
        aligned = enforce_claim_alignment(approved, ledger)
        self.assertEqual(aligned.verdict, SemanticVerdict.QUERY_MORE)
        self.assertIn("claim_001", aligned.reason)

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_extractor_drops_ungrounded_labels_values_and_units(self, chat):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": True,
            "grain": "project",
            "fields": ["project_name", "project_value"],
            "canonical_labels": ["โครงการจริง", "โครงการแต่ง"],
            "facts": [{
                "subject": "โครงการจริง",
                "predicate": "project_value",
                "value": 100,
                "unit": "บาท",
                "grain": "project",
                "derivation": None,
            }, {
                "subject": "โครงการแต่ง",
                "predicate": "project_value",
                "value": 999,
                "unit": "บาท",
                "grain": "project",
                "derivation": None,
            }],
            "proved_claim_ids": ["claim_001"],
            "contradictions": [],
            "missing_evidence": [],
            "claim_updates": [],
            "next_action": "accept",
            "reason": "complete",
        })
        observation = observe_tool_result(
            "project value",
            "query projects",
            ClaimLedger([
                ClaimRequirement(
                    "claim_001",
                    "project values",
                    "project",
                    ("project_name", "project_value"),
                )
            ]),
            EvidenceRecord.from_tool(
                "call-project",
                "execute_query_tool",
                {},
                "project_name project_value\nโครงการจริง 100",
            ),
        )
        self.assertEqual(observation.canonical_labels, ("โครงการจริง",))
        self.assertEqual(len(observation.facts), 1)
        self.assertIsNone(observation.facts[0].unit)

    @patch("labs.lab6_todo.phase2_runtime.time.monotonic")
    def test_whole_run_budget_and_call_budgets_are_enforced(self, monotonic):
        monotonic.side_effect = [100.0, 101.0, 101.0, 106.0]
        budget = Phase2Budget(max_seconds=5, max_agent_calls=1)
        budget.consume_agent()
        with self.assertRaises(RuntimeBudgetExhausted):
            budget.consume_agent()
        with self.assertRaises(RuntimeBudgetExhausted):
            budget.check_time()

    def test_hard_deadline_interrupts_blocking_work(self):
        with self.assertRaises(RuntimeBudgetExhausted):
            with hard_deadline(0.02):
                time.sleep(0.2)

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
