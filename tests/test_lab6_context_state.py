import unittest

from labs.lab6_todo.context_state import (
    ActionKind,
    AgentPhase,
    ContextState,
)


class ContextStateTests(unittest.TestCase):
    def test_signature_is_stable_across_argument_order(self):
        left = ContextState.action_signature("query", {"b": 2, "a": 1})
        right = ContextState.action_signature("query", {"a": 1, "b": 2})
        self.assertEqual(left, right)

    def test_different_arguments_or_results_do_not_count_as_same_loop(self):
        state = ContextState("goal", phase=AgentPhase.ACT)
        self.assertFalse(
            state.observe_action("query", {"page": 1}, "rows-1").alert
        )
        self.assertFalse(
            state.observe_action("query", {"page": 2}, "rows-2").alert
        )

    def test_same_action_and_result_twice_detects_loop(self):
        state = ContextState("goal", phase=AgentPhase.ACT)
        state.observe_action("query", {"sql": "SELECT 1"}, "1")
        report = state.observe_action("query", {"sql": "SELECT 1"}, "1")
        self.assertTrue(report.repeated_action_result)

    def test_repeated_error_uses_type_and_message(self):
        state = ContextState("goal")
        state.observe_error(TimeoutError("MCP timeout"))
        report = state.observe_error(TimeoutError("MCP timeout"))
        self.assertTrue(report.repeated_error)
        self.assertEqual(state.budgets.errors, 2)

    def test_phase_violation_is_reported_without_mutating_phase(self):
        state = ContextState("goal", phase=AgentPhase.PLAN)
        report = state.observe_action(
            "execute_query",
            {},
            "rows",
            kind=ActionKind.TOOL,
        )
        self.assertTrue(report.phase_violation)
        self.assertEqual(state.phase, AgentPhase.PLAN)

    def test_control_state_tracks_step_evidence_and_budget(self):
        state = ContextState("immutable goal")
        state.start_step("inspect schema")
        state.add_evidence_ref("call-123")
        state.complete_step("inspect schema")
        self.assertEqual(state.original_goal, "immutable goal")
        self.assertEqual(state.completed_steps, ["inspect schema"])
        self.assertEqual(state.accepted_evidence_refs, ["call-123"])
        self.assertIsNone(state.active_step)
        with self.assertRaisesRegex(AttributeError, "immutable"):
            state.original_goal = "changed"


if __name__ == "__main__":
    unittest.main()
