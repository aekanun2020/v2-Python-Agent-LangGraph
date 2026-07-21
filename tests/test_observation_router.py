import unittest

from labs.lab6_todo.observation_policy import ObservationState
from labs.lab6_todo.observation_router import (
    assess_observation_risk, routed_decision, validate_routing_mode,
)
from labs.lab6_todo.semantic_reviewer import SemanticReview


class ObservationRouterTests(unittest.TestCase):
    def test_temporal_contract_is_high_risk_and_routes_after_accept(self):
        hard = ObservationState(
            "query_result", [], semantic_requirements=["pre_review_time_window"],
            decision="accept",
        )
        risk = assess_observation_risk(
            hard=hard, step_description="training ก่อน review", tool="execute_query_tool",
            tool_arguments={"query": "SELECT SUM(hours) FROM training_records"},
        )
        self.assertEqual(risk.level, "high")
        self.assertTrue(risk.reviewer_required)

    def test_hard_failure_never_requires_reviewer(self):
        hard = ObservationState(
            "query_result", [], semantic_requirements=["safe_join_cardinality"],
            decision="retry",
        )
        risk = assess_observation_risk(
            hard=hard, step_description="fan-out", tool="execute_query_tool",
            tool_arguments={"query": "SELECT 1"},
        )
        self.assertEqual(risk.level, "high")
        self.assertFalse(risk.reviewer_required)

    def test_denominator_is_medium_and_does_not_route(self):
        hard = ObservationState(
            "query_result", [], semantic_requirements=["explicit_denominator"],
            decision="accept",
        )
        risk = assess_observation_risk(
            hard=hard, step_description="percentage", tool="execute_query_tool",
            tool_arguments={"query": "SELECT 100.0 * SUM(x) / COUNT(*) FROM t"},
        )
        self.assertEqual(risk.level, "medium")
        self.assertFalse(risk.reviewer_required)

    def test_shadow_never_changes_hard_decision(self):
        hard = ObservationState("query_result", [], decision="accept")
        review = SemanticReview(decision="reject")
        self.assertEqual(routed_decision("shadow", hard, review), "accept")

    def test_enforce_applies_reviewer_veto(self):
        hard = ObservationState("query_result", [], decision="accept")
        review = SemanticReview(decision="reject")
        self.assertEqual(routed_decision("enforce", hard, review), "reject")

    def test_rules_mode_is_backward_compatible(self):
        hard = ObservationState("query_result", [], decision="accept")
        self.assertEqual(routed_decision("rules", hard), "accept")
        self.assertEqual(validate_routing_mode("RULES"), "rules")


if __name__ == "__main__":
    unittest.main()
