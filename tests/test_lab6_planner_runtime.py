import unittest

from labs.lab6_todo.observation_types import Claim
from labs.lab6_todo.planner_runtime import PlanStep, PlannerState
from labs.lab6_todo.agent_planner import (
    build_goal_contract, normalize_typed_plan_steps, require_final_answer,
    planner_tools, select_available_tools, semantic_recovery_hint,
    validate_final_semantics,
)


class PurePythonPlannerTests(unittest.TestCase):
    def test_tool_visibility_follows_runtime_phase(self):
        management = planner_tools()
        mcp = [{"type": "function", "function": {"name": "query"}}]
        self.assertEqual(
            [item["function"]["name"] for item in
             select_available_tools(None, management, mcp)],
            ["plan_write"],
        )
        active = PlannerState("goal", [PlanStep(1, "work")])
        self.assertIn("query", [item["function"]["name"] for item in
                               select_available_tools(active, management, mcp)])
        active.start(1)
        active.observe(1, tool="query", tool_call_id="one", result="rows")
        active.complete(1)
        self.assertEqual(select_available_tools(active, management, mcp), [])
        self.assertEqual(
            [item["function"]["name"] for item in select_available_tools(
                active, management, mcp, replan_authorized=True
            )],
            ["plan_revise"],
        )
    def test_dynamic_goal_contract_names_required_fields_and_forbidden_status(self):
        contract = build_goal_contract("ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน")
        self.assertIn("emp_length_dim", contract)
        self.assertIn("funded_amnt", contract)
        self.assertIn("do not JOIN or filter loan_status", contract)

    def test_semantic_failure_has_executable_recovery_hint(self):
        hint = semantic_recovery_hint([], [
            Claim("dimension", "grouped_dimension", "dimension", "unsupported",
                  "JOIN dimension table and GROUP BY its label."),
            Claim("metric", "metric", "metric", "unsupported",
                  "SELECT or aggregate the configured metric."),
        ])
        self.assertIn("GROUP BY", hint)
        self.assertIn("configured metric", hint)
    def test_typed_plan_does_not_infer_capability_from_description(self):
        step = normalize_typed_plan_steps([{
            "description": "ข้อความนี้จะเขียนว่าอะไรก็ได้",
            "required_capability": "aggregation",
            "evidence_requirements": [{
                "claim_id": "aggregate_ready",
                "predicate": "aggregation_executed",
            }],
            "required_resources": [{"kind": "table", "name": "facts"}],
        }])[0]
        self.assertEqual(step.required_capability, "aggregation")

    def test_final_gate_rejects_status_filtered_approved_population(self):
        with self.assertRaisesRegex(ValueError, "loan_status"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "วงเงินกู้ที่มีการอนุมัติ (loan_status = Current หรือ Fully Paid)",
            )
    def test_final_semantic_gate_rejects_status_as_approval_and_currency(self):
        with self.assertRaisesRegex(ValueError, "Approval rate"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "อัตราการอนุมัติสูงสุด 88% และวงเงินเฉลี่ย 16,403 บาท",
            )

    def test_final_semantic_gate_accepts_funded_amount_proxy_without_currency(self):
        validate_final_semantics(
            "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            "รายงานค่าเฉลี่ย funded_amnt แยกตามกลุ่มอายุงาน เป็น association เท่านั้น",
        )

    def test_final_gate_rejects_monotonic_claim_without_explicit_numeric_proof(self):
        grouped_rows = [{"result": '[{"tenure":1,"avg_value":10},{"tenure":2,"avg_value":9}]'}]
        with self.assertRaisesRegex(ValueError, "monotonic_increase_violations"):
            validate_final_semantics(
                "เปรียบเทียบค่าเฉลี่ยตามอายุงาน",
                "ค่าเฉลี่ยเพิ่มขึ้นตามระยะเวลาการทำงาน",
                grouped_rows,
            )

    def test_final_gate_rejects_soft_trend_claim_without_trend_statistic(self):
        grouped_rows = [{"result": '[{"tenure":1,"avg_value":10},{"tenure":2,"avg_value":11}]'}]
        with self.assertRaisesRegex(ValueError, "trend_slope"):
            validate_final_semantics(
                "เปรียบเทียบค่าเฉลี่ยตามอายุงาน",
                "โดยทั่วไป อายุงานที่ยาวนานกว่ามีแนวโน้มค่าเฉลี่ยสูงขึ้น",
                grouped_rows,
            )

    def test_final_gate_accepts_monotonic_claim_with_zero_violation_evidence(self):
        evidence = [{"result": '[{"monotonic_increase_violations":0}]'}]
        validate_final_semantics(
            "เปรียบเทียบค่าเฉลี่ยตามอายุงาน",
            "ค่าเฉลี่ยเพิ่มขึ้นตามระยะเวลาการทำงาน",
            evidence,
        )

    def test_final_gate_marks_monotonic_claim_contradicted_by_violation_count(self):
        evidence = [{"result": '[{"monotonic_increase_violations":2}]'}]
        with self.assertRaisesRegex(ValueError, "contradicted"):
            validate_final_semantics(
                "เปรียบเทียบค่าเฉลี่ยตามอายุงาน",
                "ค่าเฉลี่ยเพิ่มขึ้นตามระยะเวลาการทำงาน",
                evidence,
            )

    def test_final_semantic_gate_rejects_false_missing_control_claim(self):
        with self.assertRaisesRegex(ValueError, "MCP schema"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "ข้อจำกัดคือไม่มีข้อมูล annual_inc, dti และ home_ownership",
            )

    def test_final_gate_rejects_loan_amount_as_approved_amount(self):
        with self.assertRaisesRegex(ValueError, "loan_amnt"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "ข้อมูลนี้เป็นวงเงินกู้ที่อนุมัติ (loan_amnt)",
            )

    def test_final_gate_requires_row_level_evidence_for_majority_claim(self):
        answer = "ค่าเฉลี่ยใกล้กัน แสดงว่าคำขอส่วนใหญ่ได้รับการอนุมัติเต็มจำนวน"
        aggregate_only = [{"tool_arguments": {"query": (
            "SELECT AVG(loan_amnt), AVG(funded_amnt) FROM loans_fact"
        )}}]
        with self.assertRaisesRegex(ValueError, "row-level proportion"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                answer,
                aggregate_only,
            )

    def test_final_gate_accepts_majority_claim_with_direct_ratio_evidence(self):
        ratio = [{"tool_arguments": {"query": (
            "SELECT AVG(CASE WHEN funded_amnt = loan_amnt THEN 1.0 ELSE 0 END) "
            "AS fully_funded_ratio FROM loans_fact"
        )}}]
        validate_final_semantics(
            "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            "หลักฐาน row-level แสดงว่าคำขอส่วนใหญ่ได้รับ funding เต็มจำนวน",
            ratio,
        )

    def test_final_gate_rejects_fabricated_step_reference(self):
        evidence = [{"step_id": 1, "result": "schema"}]
        with self.assertRaisesRegex(ValueError, "unknown step references"):
            validate_final_semantics(
                "inspect data", "Step 2 verified the metric", evidence,
            )

    def test_final_gate_rejects_unproven_evidence_status(self):
        evidence = [{
            "step_id": 1,
            "proven_claim_ids": ["schema"],
            "claim_requirements": [{
                "claim_id": "schema", "predicate": "schema_inspected",
            }],
            "result": "schema",
        }]
        with self.assertRaisesRegex(ValueError, "existence_checked"):
            validate_final_semantics(
                "inspect data", "schema_inspected and existence_checked", evidence,
            )
    def setUp(self):
        self.plan = PlannerState("goal", [PlanStep(1, "query")])
        self.plan.start(1)

    def test_cannot_self_report_done_without_evidence(self):
        with self.assertRaisesRegex(ValueError, "without tool evidence"):
            self.plan.complete(1)

    def test_observed_tool_result_unlocks_completion_and_answer(self):
        self.plan.observe(1, tool="sql", tool_call_id="1", result="one row")
        self.plan.complete(1)
        self.plan.approve_answer()
        self.assertTrue(self.plan.answer_approved)

    def test_start_and_complete_are_idempotent_after_evidence_completion(self):
        self.plan.observe(1, tool="sql", tool_call_id="1", result="one row")
        self.plan.complete(1)
        self.plan.start(1)
        self.plan.complete(1)
        self.assertEqual(self.plan.step(1).status, "completed")

    def test_replan_cannot_reopen_completed_evidence(self):
        self.plan.observe(1, tool="sql", tool_call_id="1", result="one row")
        self.plan.complete(1)
        self.plan.revise([PlanStep(1, "query again", "pending")], "model changed its mind")
        self.assertEqual(self.plan.step(1).status, "completed")
        self.assertEqual(len(self.plan.step(1).evidence), 1)

    def test_replan_cannot_drop_completed_evidence(self):
        self.plan.observe(1, tool="sql", tool_call_id="1", result="one row")
        self.plan.complete(1)
        self.plan.revise([PlanStep(2, "future query", "pending")], "replace future work")
        self.assertEqual(self.plan.step(1).status, "completed")
        self.assertEqual(self.plan.step(2).status, "pending")

    def test_evidence_must_bind_to_active_step(self):
        other = PlannerState("goal", [PlanStep(1, "a"), PlanStep(2, "b")])
        other.start(1)
        with self.assertRaisesRegex(ValueError, "in-progress step"):
            other.observe(2, tool="sql", tool_call_id="2", result="row")

    def test_replan_increments_revision_and_preserves_evidence(self):
        self.plan.observe(1, tool="schema", tool_call_id="1", result="fields")
        self.plan.revise([PlanStep(1, "query revised", "in_progress"), PlanStep(2, "verify")], "schema changed")
        self.assertEqual(self.plan.revision, 2)
        self.assertEqual(len(self.plan.step(1).evidence), 1)

    def test_replan_cannot_smuggle_unsupported_completed_step(self):
        self.plan.revise([PlanStep(1, "query", "completed")], "model claimed done")
        self.assertEqual(self.plan.step(1).status, "pending")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.plan.approve_answer()

    def test_unknown_step_id_is_feedback_not_stop_iteration(self):
        with self.assertRaisesRegex(ValueError, "unknown step id 99"):
            self.plan.start(99)

    def test_plan_write_normalizes_typed_qwen_steps(self):
        normalized = normalize_typed_plan_steps([{
            "description": "ตรวจ schema",
            "required_capability": "schema_inspection",
            "evidence_requirements": [{
                "claim_id": "schema_seen", "predicate": "schema_inspected",
            }],
            "required_resources": [{"kind": "table", "name": "employees"}],
        }])
        self.assertEqual(normalized[0].description, "ตรวจ schema")
        self.assertEqual(normalized[0].required_capability, "schema_inspection")

    def test_plan_write_rejects_malformed_step_without_crashing(self):
        with self.assertRaisesRegex(ValueError, r"steps\[1\]"):
            normalize_typed_plan_steps([{"status": "pending"}])

    def test_plan_write_rejects_free_text_steps(self):
        with self.assertRaisesRegex(ValueError, "typed object"):
            normalize_typed_plan_steps(["ตรวจ schema"])

    def test_generic_payload_cannot_fake_declared_aggregation(self):
        with self.assertRaisesRegex(ValueError, "aggregation_executed"):
            normalize_typed_plan_steps([{
                "description": "aggregate data",
                "required_capability": "aggregation",
                "evidence_requirements": [{
                    "claim_id": "anything", "predicate": "inspectable_payload",
                }],
                "required_resources": [{"kind": "table", "name": "facts"}],
            }])

    def test_answer_gate_rejects_none_or_blank_content(self):
        for content in (None, "", "   "):
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, "final answer is empty"):
                    require_final_answer(content)

    def test_answer_gate_normalizes_nonempty_content(self):
        self.assertEqual(require_final_answer("  สรุปผลแล้ว  "), "สรุปผลแล้ว")


if __name__ == "__main__":
    unittest.main()
