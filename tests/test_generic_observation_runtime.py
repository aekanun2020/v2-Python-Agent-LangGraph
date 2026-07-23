import unittest

from labs.lab6_todo.capabilities import action_capability_error, infer_action_capabilities
from labs.lab6_todo.circuit_breaker import FailureCircuitBreaker
from labs.lab6_todo.contract_runtime import (
    evaluate_action_claims, resolve_contract, validate_reviewer_action,
)
from labs.lab6_todo.observation_policy import observe_result
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState
from labs.lab6_todo.observation_types import EvidenceRequirement, ResourceRequirement
from labs.lab6_todo.capabilities import action_resource_error


class GenericObservationRuntimeTests(unittest.TestCase):
    def test_resource_binding_rejects_wrong_table_even_when_query_succeeds(self):
        error = action_resource_error(
            "execute_query_tool", {"query": "SELECT COUNT(*) FROM projects"}, "[{\"count\": 2}]",
            [ResourceRequirement("table", "employees")],
        )
        self.assertIn("table:employees", error)

    def test_resource_binding_uses_identifier_boundaries(self):
        error = action_resource_error(
            "execute_query_tool", {"query": "SELECT * FROM employees_archive"}, "rows",
            [ResourceRequirement("table", "employees")],
        )
        self.assertIn("table:employees", error)

    def test_resource_binding_accepts_table_and_aliased_field(self):
        error = action_resource_error(
            "execute_query_tool",
            {"query": "SELECT e.department_id, COUNT(*) FROM employees e GROUP BY e.department_id"},
            "rows",
            [ResourceRequirement("table", "employees"),
             ResourceRequirement("field", "employees.department_id")],
        )
        self.assertIsNone(error)

    def test_schema_context_binds_resources_from_payload(self):
        error = action_resource_error(
            "get_database_context", {}, "employees(employee_id, department_id)",
            [ResourceRequirement("table", "employees"),
             ResourceRequirement("field", "employees.employee_id")],
        )
        self.assertIsNone(error)

    def test_claim_evidence_reuse_preserves_provenance_without_new_tool_call(self):
        requirement = EvidenceRequirement("headcount", "aggregation_executed", "headcount")
        resources = [ResourceRequirement("table", "employees")]
        plan = PlannerState("goal", [
            PlanStep(1, "first", required_capability="aggregation",
                     evidence_requirements=[requirement], required_resources=resources),
            PlanStep(2, "same claim", required_capability="aggregation",
                     evidence_requirements=[requirement], required_resources=resources),
        ])
        plan.start(1)
        plan.observe(1, tool="execute_query_tool", tool_call_id="call-1", result="rows",
                     action={"query": "SELECT COUNT(*) FROM employees"},
                     proven_claim_ids=["headcount"])
        plan.complete(1)
        source = plan.step(1).evidence[0]
        self.assertTrue(plan.start(2))
        reused = plan.step(2).evidence[0]
        self.assertEqual(plan.step(2).status, "completed")
        self.assertEqual(reused.reused_from_evidence_id, source.evidence_id)
        self.assertEqual(reused.tool_call_id, "call-1")

    def test_claim_id_collision_cannot_reuse_different_resource(self):
        requirement = EvidenceRequirement("count", "aggregation_executed")
        plan = PlannerState("goal", [
            PlanStep(1, "employees", required_capability="aggregation",
                     evidence_requirements=[requirement],
                     required_resources=[ResourceRequirement("table", "employees")]),
            PlanStep(2, "projects", required_capability="aggregation",
                     evidence_requirements=[requirement],
                     required_resources=[ResourceRequirement("table", "projects")]),
        ])
        plan.start(1)
        plan.observe(1, tool="query", tool_call_id="one", result="rows",
                     proven_claim_ids=["count"])
        plan.complete(1)
        self.assertFalse(plan.start(2))
        self.assertEqual(plan.step(2).status, "in_progress")

    def test_claim_id_collision_cannot_reuse_different_predicate(self):
        resources = [ResourceRequirement("table", "employees")]
        plan = PlannerState("goal", [
            PlanStep(1, "schema", required_capability="schema_inspection",
                     evidence_requirements=[EvidenceRequirement("same", "schema_inspected")],
                     required_resources=resources),
            PlanStep(2, "rows", required_capability="schema_inspection",
                     evidence_requirements=[EvidenceRequirement("same", "rows_returned")],
                     required_resources=resources),
        ])
        plan.start(1)
        plan.observe(1, tool="schema", tool_call_id="one", result="employees",
                     proven_claim_ids=["same"])
        plan.complete(1)
        self.assertFalse(plan.start(2))

    def test_information_schema_query_has_schema_capability(self):
        capabilities = infer_action_capabilities(
            "execute_query_tool",
            {"query": "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"},
        )
        self.assertIn("schema_inspection", capabilities)
        obs = observe_result(
            step_description="ตรวจ schema ของตาราง",
            tool="execute_query_tool",
            tool_arguments={"query": "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"},
            result='[{"COLUMN_NAME":"employee_id"}]',
            goal_description="ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            semantic_checks=True,
            required_capability="schema_inspection",
            evidence_requirements=[EvidenceRequirement(
                "schema_seen", "schema_inspected", "database columns"
            )],
        )
        self.assertEqual(obs.decision, "accept")
        self.assertTrue(obs.execution_ok)
        self.assertTrue(obs.supports_step)
        self.assertTrue(obs.evidence_sufficient)
        self.assertEqual(obs.proven_claims[0].id, "schema_seen")

    def test_description_keywords_cannot_override_typed_capability(self):
        obs = observe_result(
            step_description="ตรวจ schema และ column แต่ typed intent คือ aggregation",
            required_capability="aggregation",
            evidence_requirements=[EvidenceRequirement(
                "aggregate_ready", "aggregation_executed"
            )],
            tool="preview_table",
            result='[{"column":"employee_id"}]',
        )
        self.assertEqual(obs.decision, "reject")
        self.assertIn("step_tool_alignment", obs.failed)

    def test_schema_existence_action_is_not_forced_through_analytical_contract(self):
        obs = observe_result(
            step_description="ตรวจว่ามี decision field หรือไม่",
            required_capability="existence_check",
            evidence_requirements=[EvidenceRequirement(
                "decision_field_checked", "existence_checked"
            )],
            tool="execute_query_tool",
            tool_arguments={"query": (
                "SELECT COUNT(*) AS field_count FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE COLUMN_NAME = 'approval_decision'"
            )},
            result='[{"field_count":0}]',
            goal_description="ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "accept")
        self.assertEqual(obs.proven_claims[0].id, "decision_field_checked")

    def test_typed_plan_is_not_reclassified_by_legacy_description_keywords(self):
        obs = observe_result(
            step_description="นับพนักงานที่ปฏิบัติงานแยกแผนก",
            required_capability="query_execution",
            evidence_requirements=[EvidenceRequirement(
                "rows_observed", "rows_returned"
            )],
            tool="execute_query_tool",
            tool_arguments={"query": "SELECT TOP 1 employee_id FROM employees"},
            result='[{"employee_id":100}]',
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "accept")
        self.assertNotIn("active_employee_population", obs.semantic_requirements)

    def test_filtered_catalog_query_supports_existence_without_count(self):
        args = {"query": (
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE COLUMN_NAME = 'decision_field'"
        )}
        self.assertIsNone(action_capability_error(
            "existence_check", "execute_query_tool", args
        ))

    def test_aggregation_cannot_hide_behind_broad_query_execution(self):
        error = action_capability_error(
            "query_execution", "execute_query_tool",
            {"query": "SELECT department, AVG(score) FROM reviews GROUP BY department"},
        )
        self.assertIn("too broad", error)

    def test_aggregation_declared_specifically_is_accepted(self):
        error = action_capability_error(
            "aggregation", "execute_query_tool",
            {"query": "SELECT department, AVG(score) FROM reviews GROUP BY department"},
        )
        self.assertIsNone(error)

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

    def test_reviewer_cannot_recommend_action_forbidden_by_runtime_contract(self):
        contract = resolve_contract("ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน")
        failures = validate_reviewer_action(
            contract, decision="query_more",
            reason="loan_status_id might contain approval information",
            suggested_next_action=(
                "Join loan_status_dim and calculate approval rate by emp_length"
            ),
        )
        self.assertTrue(failures)
        self.assertIn("approval", " ".join(failures).lower())

    def test_reviewer_may_recommend_action_inside_runtime_contract(self):
        contract = resolve_contract("ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน")
        failures = validate_reviewer_action(
            contract, decision="query_more", reason="need funding evidence",
            suggested_next_action="Aggregate funded_amnt by emp_length",
        )
        self.assertEqual(failures, [])

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
