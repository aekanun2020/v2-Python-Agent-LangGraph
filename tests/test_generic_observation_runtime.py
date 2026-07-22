import unittest

from labs.lab6_todo.capabilities import infer_action_capabilities
from labs.lab6_todo.circuit_breaker import FailureCircuitBreaker
from labs.lab6_todo.contract_runtime import evaluate_action_claims, resolve_contract
from labs.lab6_todo.observation_policy import observe_result
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState


class GenericObservationRuntimeTests(unittest.TestCase):
    def test_information_schema_query_has_schema_capability(self):
        capabilities = infer_action_capabilities(
            "execute_query_tool",
            {"query": "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"},
        )
        self.assertIn("schema_presence", capabilities)
        obs = observe_result(
            step_description="ตรวจ schema ของตาราง",
            tool="execute_query_tool",
            tool_arguments={"query": "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"},
            result='[{"COLUMN_NAME":"employee_id"}]',
            goal_description="ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "accept")
        self.assertTrue(obs.execution_ok)
        self.assertTrue(obs.supports_step)
        self.assertTrue(obs.evidence_sufficient)

    def test_cross_evidence_conflict_becomes_typed_contradicted_claim(self):
        obs = observe_result(
            step_description="ตรวจ cross evidence consistency จากหลักฐานก่อนหน้า",
            tool="execute_query_tool",
            tool_arguments={"query": "SELECT 2 AS employee_count"},
            result='[{"employee_count":2}]',
            prior_facts={"employee_count": 1.0},
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "retry")
        self.assertEqual(obs.contradicted_claims[0].status, "contradicted")

    def test_contract_is_loaded_outside_python_core(self):
        contract = resolve_contract("ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน")
        self.assertIsNotNone(contract)
        claims = evaluate_action_claims(
            contract,
            sql=("SELECT d.emp_length, AVG(f.funded_amnt) FROM loans_fact f "
                 "JOIN emp_length_dim d ON f.emp_length_id=d.emp_length_id "
                 "GROUP BY d.emp_length"),
        )
        self.assertTrue(all(claim.status == "proven" for claim in claims))

    def test_circuit_breaker_replans_then_stops_repeated_signature(self):
        breaker = FailureCircuitBreaker(replan_after=3, stop_after=5)
        escalations = [
            breaker.record(step_id=2, tool="query", decision="reject",
                           failed=["step_tool_alignment"])[1]
            for _ in range(5)
        ]
        self.assertEqual(escalations, [None, None, "replan", "replan", "stop"])

    def test_evidence_provenance_belongs_to_plan_revision_and_step(self):
        plan = PlannerState("goal", [PlanStep(1, "query")])
        plan.start(1)
        plan.observe(
            1, tool="query", tool_call_id="call-1", result="rows",
            action={"query": "SELECT 1"}, proven_claim_ids=["claim-1"],
        )
        evidence = plan.accepted_evidence[0]
        self.assertEqual(evidence.plan_id, plan.plan_id)
        self.assertEqual(evidence.plan_revision, 1)
        self.assertEqual(evidence.step_id, 1)
        self.assertEqual(evidence.proven_claim_ids, ["claim-1"])


if __name__ == "__main__":
    unittest.main()
