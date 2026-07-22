import unittest
from types import SimpleNamespace
from unittest.mock import patch

from labs.lab6_todo.observation_policy import ObservationState
from labs.lab6_todo.semantic_reviewer import (
    FINAL_SYSTEM, SemanticReview, _parse_json, hybrid_decision,
    review_final_answer, review_observation,
)


class SemanticReviewerTests(unittest.TestCase):
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
            answer="10+ years = 16514.62",
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
