import unittest

from labs.lab6_todo.agent_planner import (
    ObservationState,
    PlanStep,
    PlannerState,
    visible_tools,
)


class FakeRegistry:
    openai_tools = [{
        "type": "function",
        "function": {
            "name": "mcp_query",
            "description": "query",
            "parameters": {"type": "object", "properties": {}},
        },
    }]


class PurePythonPlannerTests(unittest.TestCase):
    def setUp(self):
        self.state = PlannerState("goal", [
            PlanStep(1, "inspect schema"),
            PlanStep(2, "query evidence"),
        ])
        self.state.activate_next()

    def test_mcp_result_must_be_observed_before_next_action(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        with self.assertRaisesRegex(ValueError, "observe"):
            self.state.record_action("mcp_query", {}, "again", "call-2")

    def test_accept_requires_all_three_conditions(self):
        self.state.record_action("mcp_query", {}, "rows", "call-1")
        with self.assertRaisesRegex(ValueError, "accept"):
            self.state.observe(ObservationState(
                action_succeeded=True,
                supports_step=False,
                evidence_complete=True,
                proven_claims=[],
                contradicted_claims=[],
                decision="accept",
                reason="wrong result",
            ))

    def test_accept_attaches_evidence_and_advances_plan(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(ObservationState(
            action_succeeded=True,
            supports_step=True,
            evidence_complete=True,
            proven_claims=["schema discovered"],
            contradicted_claims=[],
            decision="accept",
            reason="result proves the active step",
        ))
        self.assertEqual(self.state.steps[0].status, "completed")
        self.assertEqual(self.state.steps[1].status, "active")
        self.assertEqual(
            self.state.steps[0].evidence[0]["proven_claims"],
            ["schema discovered"],
        )

    def test_retry_keeps_active_step_without_accepting_evidence(self):
        self.state.record_action("mcp_query", {}, "error", "call-1")
        self.state.observe(ObservationState(
            action_succeeded=False,
            supports_step=False,
            evidence_complete=False,
            proven_claims=[],
            contradicted_claims=[],
            decision="retry",
            reason="transport error",
        ))
        self.assertEqual(self.state.steps[0].status, "active")
        self.assertFalse(self.state.steps[0].evidence)
        self.assertFalse(self.state.awaiting_observation)

    def test_replan_preserves_completed_evidence(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(ObservationState(
            True, True, True, ["schema"], [], "accept", "enough",
        ))
        self.state.record_action("mcp_query", {}, "unexpected", "call-2")
        self.state.observe(ObservationState(
            True, False, False, [], ["expected field exists"], "replan", "field absent",
        ))
        self.state.revise("use available field", ["query available metric"])
        self.assertEqual(self.state.revision, 2)
        self.assertEqual(self.state.steps[0].status, "completed")
        self.assertEqual(len(self.state.steps[0].evidence), 1)
        self.assertEqual(self.state.steps[1].task, "query available metric")

    def test_tool_visibility_follows_tao_phase(self):
        registry = FakeRegistry()
        self.assertEqual(
            [tool["function"]["name"] for tool in visible_tools(None, registry)],
            ["plan_write"],
        )
        self.assertIn(
            "mcp_query",
            [tool["function"]["name"] for tool in visible_tools(self.state, registry)],
        )
        self.state.record_action("mcp_query", {}, "rows", "call-1")
        self.assertEqual(
            [tool["function"]["name"] for tool in visible_tools(self.state, registry)],
            ["observe"],
        )

    def test_prompt_requires_one_action_at_a_time(self):
        from labs.lab6_todo.agent_planner import SYSTEM

        self.assertIn("ครั้งละหนึ่งรายการ", SYSTEM)
        self.assertIn("Action → Observation", SYSTEM)


if __name__ == "__main__":
    unittest.main()
