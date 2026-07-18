import unittest

from labs.lab6_todo.planner_runtime import PlanStep, PlannerState


class PurePythonPlannerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
