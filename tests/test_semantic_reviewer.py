import unittest

from labs.lab6_todo.observation_policy import ObservationState
from labs.lab6_todo.semantic_reviewer import (
    SemanticReview, _parse_json, hybrid_decision,
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


if __name__ == "__main__":
    unittest.main()
