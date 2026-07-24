import unittest

from labs.lab6_todo.agent_planner import (
    FinalReview,
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


def observation(
    *,
    evidence_status="accept",
    next_action="continue",
    satisfied=None,
    missing=None,
    action_succeeded=True,
    supports_step=True,
    evidence_complete=True,
):
    return ObservationState(
        action_succeeded=action_succeeded,
        supports_step=supports_step,
        evidence_complete=evidence_complete,
        proven_claims=["claim"],
        contradicted_claims=[],
        satisfied_requirement_ids=satisfied or ["schema"],
        missing_requirement_ids=missing or [],
        evidence_status=evidence_status,
        next_action=next_action,
        reason="test",
    )


class PurePythonPlannerTests(unittest.TestCase):
    def setUp(self):
        self.state = PlannerState("goal", [
            PlanStep(1, "inspect schema", [{"id": "schema", "description": "schema is known"}]),
            PlanStep(2, "query evidence", [{"id": "metric", "description": "metric is calculated"}]),
        ])
        self.state.activate_next()

    def test_mcp_result_must_be_observed_before_next_action(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        with self.assertRaisesRegex(ValueError, "observe"):
            self.state.record_action("mcp_query", {}, "again", "call-2")

    def test_accept_requires_every_declared_requirement(self):
        self.state.record_action("mcp_query", {}, "rows", "call-1")
        with self.assertRaisesRegex(ValueError, "requirements"):
            self.state.observe(observation(
                satisfied=["different"],
                missing=["schema"],
            ))

    def test_accept_and_continue_attaches_evidence(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(observation())
        self.assertEqual(self.state.steps[0].status, "completed")
        self.assertEqual(self.state.steps[1].status, "active")
        self.assertEqual(
            self.state.steps[0].evidence[0]["satisfied_requirement_ids"],
            ["schema"],
        )

    def test_accept_and_replan_are_independent_axes(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(observation(next_action="replan"))
        self.assertEqual(self.state.steps[0].status, "completed")
        self.assertTrue(self.state.replan_authorized)
        self.assertIsNone(self.state.active_step)

    def test_replan_requires_observer_authorization_and_preserves_evidence(self):
        with self.assertRaisesRegex(ValueError, "next_action=replan"):
            self.state.revise("guess", [{
                "task": "new",
                "acceptance_requirements": [{"id": "new", "description": "new proof"}],
            }])
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(observation(next_action="replan"))
        self.state.revise("schema changed plan", [{
            "task": "query available metric",
            "acceptance_requirements": [{"id": "metric", "description": "metric is calculated"}],
        }])
        self.assertEqual(self.state.revision, 2)
        self.assertEqual(len(self.state.steps[0].evidence), 1)
        self.assertEqual(self.state.steps[1].task, "query available metric")

    def test_replan_phase_blocks_mcp_action(self):
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(observation(next_action="replan"))
        with self.assertRaisesRegex(ValueError, "plan_revise"):
            self.state.record_action("mcp_query", {}, "rows", "call-2")

    def test_query_more_accumulates_partial_evidence(self):
        self.state.steps[0].acceptance_requirements = [
            {"id": "schema", "description": "schema"},
            {"id": "rows", "description": "rows"},
        ]
        self.state.record_action("mcp_query", {}, "schema", "call-1")
        self.state.observe(observation(
            evidence_status="reject",
            next_action="query_more",
            satisfied=["schema"],
            missing=["rows"],
            evidence_complete=False,
        ))
        self.state.record_action("mcp_query", {}, "rows", "call-2")
        self.state.observe(observation(
            satisfied=["rows"],
            missing=[],
        ))
        self.assertEqual(self.state.steps[0].status, "completed")
        self.assertEqual(len(self.state.steps[0].evidence), 2)

    def test_reject_cannot_continue(self):
        self.state.record_action("mcp_query", {}, "error", "call-1")
        with self.assertRaisesRegex(ValueError, "continue"):
            self.state.observe(observation(
                evidence_status="reject",
                next_action="continue",
                action_succeeded=False,
                supports_step=False,
                evidence_complete=False,
            ))

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
            [],
        )

    def test_final_review_shape_keeps_verdict_separate(self):
        review = FinalReview(
            verdict="query_more",
            supported_claims=[],
            unsupported_claims=["organization metric"],
            missing_requirements=["weighted denominator"],
            reason="missing proof",
        )
        self.assertEqual(review.verdict, "query_more")
        self.assertIn("weighted denominator", review.missing_requirements)


if __name__ == "__main__":
    unittest.main()
