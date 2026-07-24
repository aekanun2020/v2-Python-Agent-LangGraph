import unittest
from types import SimpleNamespace
from unittest.mock import patch

from labs.lab6_todo.observation_policy import ObservationState
from labs.lab6_todo.semantic_reviewer import (
    FINAL_SYSTEM, PLAN_SYSTEM, SYSTEM, SemanticReview, _parse_json, _validate_plan_review,
    hybrid_decision,
    review_final_answer, review_observation, review_plan,
)


class SemanticReviewerTests(unittest.TestCase):
    def test_plan_review_normalizes_qwen_verdict_alias(self):
        review = _validate_plan_review({
            "verdict": "incomplete", "explanation": "missing aggregation",
        }, elapsed_ms=1)
        self.assertEqual(review.decision, "query_more")

    def test_plan_review_missing_decision_fails_closed_without_exception(self):
        review = _validate_plan_review({"checks": []}, elapsed_ms=1)
        self.assertEqual(review.decision, "query_more")
        self.assertIn("no valid decision", review.reason)

    def test_text_confidence_is_normalized(self):
        review = _validate_plan_review({
            "decision": "accept", "confidence": "high",
        }, elapsed_ms=1)
        self.assertEqual(review.confidence, 0.85)

    def test_parse_json_allows_plain_or_fenced_object(self):
        self.assertEqual(_parse_json('{"decision":"accept"}')["decision"], "accept")
        self.assertEqual(_parse_json('```json\n{"decision":"retry"}\n```')["decision"], "retry")

    def test_hard_failure_vetoes_semantic_accept(self):
        hard = ObservationState("query_result", [], decision="retry")
        review = SemanticReview(decision="accept")
        self.assertEqual(hybrid_decision(hard, review), "retry")

    def test_semantic_failure_vetoes_hard_accept(self):
        hard = ObservationState("query_result", [], decision="accept")
        review = SemanticReview(decision="query_more")
        self.assertEqual(hybrid_decision(hard, review), "query_more")

    def test_both_layers_must_accept(self):
        hard = ObservationState("query_result", [], decision="accept")
        review = SemanticReview(decision="accept")
        self.assertEqual(hybrid_decision(hard, review), "accept")

    def test_final_reviewer_requires_derived_aggregates_to_be_grounded(self):
        self.assertIn("accepted MCP evidence", FINAL_SYSTEM)
        self.assertIn("formula and weighting", FINAL_SYSTEM)
        self.assertIn("title, headings", FINAL_SYSTEM)
        self.assertIn("disclaimer cannot repair", FINAL_SYSTEM)
        self.assertIn("merely lists schema", FINAL_SYSTEM)
        self.assertIn("fabricated step numbers", FINAL_SYSTEM)
        self.assertIn("schema-only evidence", PLAN_SYSTEM)
        self.assertIn("sum of numerators / sum of denominators", FINAL_SYSTEM)
        self.assertIn("Missing/NaN metrics", FINAL_SYSTEM)
        self.assertIn("every flag", FINAL_SYSTEM)
        self.assertIn("micro-averages", PLAN_SYSTEM)
        self.assertIn("pending steps have not executed yet", PLAN_SYSTEM)
        self.assertIn("AVG(group_rate)", SYSTEM)

    @patch("labs.lab6_todo.semantic_reviewer.llm.chat")
    def test_plan_reviewer_receives_goal_contract_and_typed_plan(self, chat):
        chat.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"derived_requirements":[],"checks":[],"supports_step":false,'
                '"sufficient":false,"decision":"query_more","confidence":1,'
                '"reason":"schema-only","suggested_next_action":"add aggregation"}'
            )))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        review = review_plan(
            goal="calculate grouped average", contract_context="metric must be verified",
            completion_mode="replan",
            proposed_plan=[{
                "id": 1, "required_capability": "schema_inspection",
                "required_resources": [{"kind": "table", "name": "facts"}],
            }],
        )
        self.assertEqual(review.decision, "query_more")
        payload = chat.call_args.kwargs["messages"][1]["content"]
        self.assertIn("calculate grouped average", payload)
        self.assertIn("schema_inspection", payload)
        self.assertIn("metric must be verified", payload)
        self.assertIn('"completion_mode": "replan"', payload)

    @patch("labs.lab6_todo.semantic_reviewer.llm.chat")
    def test_final_reviewer_receives_answer_and_accepted_evidence(self, chat):
        chat.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"derived_requirements":[],"checks":[],"supports_step":true,'
                '"sufficient":true,"decision":"accept","confidence":1,'
                '"reason":"grounded","suggested_next_action":""}'
            )))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        review = review_final_answer(
            goal="compare tenure",
            answer="# Funding by tenure\n10+ years = 16514.62",
            contract_context="Do not interpret status as approval.",
            accepted_evidence=[{
                "step_id": 1, "step_description": "aggregate", "tool": "execute_query_tool",
                "tool_arguments": {"query": "SELECT ..."},
                "result": '[{"emp_length":"10+ years","avg_funded":16514.62}]',
            }],
        )
        self.assertEqual(review.decision, "accept")
        payload = chat.call_args.kwargs["messages"][1]["content"]
        self.assertIn("16514.62", payload)
        self.assertIn("accepted_mcp_evidence", payload)
        self.assertIn("authoritative_runtime_contract", payload)
        self.assertIn('"answer_headings": ["# Funding by tenure"]', payload)
        self.assertIn("Do not interpret status as approval", payload)

    @patch("labs.lab6_todo.semantic_reviewer.llm.chat")
    def test_observation_reviewer_receives_typed_step_intent(self, chat):
        chat.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"derived_requirements":[],"checks":[],"supports_step":true,'
                '"sufficient":true,"decision":"accept","confidence":1,'
                '"reason":"aligned","suggested_next_action":""}'
            )))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
        review_observation(
            goal="aggregate workforce", active_step="calculate grouped average",
            analytical_contract="", tool="execute_query_tool",
            tool_arguments={"query": "SELECT department, AVG(score) FROM reviews GROUP BY department"},
            result='[{"department":"IT","avg_score":4.0}]',
            required_capability="aggregation",
            evidence_requirements=[{
                "claim_id": "grouped_average", "predicate": "aggregation_executed",
            }],
        )
        payload = chat.call_args.kwargs["messages"][1]["content"]
        self.assertIn('"declared_required_capability": "aggregation"', payload)
        self.assertIn("aggregation_executed", payload)


if __name__ == "__main__":
    unittest.main()
