import unittest

from labs.lab6_todo.planner_runtime import PlanStep, PlannerState
from labs.lab6_todo.agent_planner import (
    normalize_plan_descriptions, require_final_answer, validate_final_semantics,
)


class PurePythonPlannerTests(unittest.TestCase):
    def test_final_semantic_gate_rejects_status_as_approval_and_currency(self):
        with self.assertRaisesRegex(ValueError, "loan_status"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "อัตราการอนุมัติสูงสุด 88% และวงเงินเฉลี่ย 16,403 บาท",
            )

    def test_final_semantic_gate_accepts_funded_amount_proxy_without_currency(self):
        validate_final_semantics(
            "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
            "ค่าเฉลี่ย funded_amnt สูงขึ้นตามบางกลุ่มอายุงาน แต่เป็น association เท่านั้น",
        )

    def test_final_semantic_gate_rejects_false_missing_control_claim(self):
        with self.assertRaisesRegex(ValueError, "MCP schema"):
            validate_final_semantics(
                "ระยะเวลาการทำงานที่มีผลต่อการอนุมัติวงเงิน",
                "ข้อจำกัดคือไม่มีข้อมูล annual_inc, dti และ home_ownership",
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

    def test_plan_write_normalizes_qwen_object_steps(self):
        normalized = normalize_plan_descriptions([
            {"description": "ตรวจ schema"},
            {"text": "query ข้อมูล"},
            "ตรวจจำนวนแถว",
        ])
        self.assertEqual(normalized, ["ตรวจ schema", "query ข้อมูล", "ตรวจจำนวนแถว"])

    def test_plan_write_rejects_malformed_step_without_crashing(self):
        with self.assertRaisesRegex(ValueError, r"steps\[1\]"):
            normalize_plan_descriptions([{"status": "pending"}])

    def test_answer_gate_rejects_none_or_blank_content(self):
        for content in (None, "", "   "):
            with self.subTest(content=content):
                with self.assertRaisesRegex(ValueError, "final answer is empty"):
                    require_final_answer(content)

    def test_answer_gate_normalizes_nonempty_content(self):
        self.assertEqual(require_final_answer("  สรุปผลแล้ว  "), "สรุปผลแล้ว")


if __name__ == "__main__":
    unittest.main()
