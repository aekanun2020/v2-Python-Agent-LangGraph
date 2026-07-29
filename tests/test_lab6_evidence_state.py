import unittest

from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    SemanticVerdict,
)
from labs.lab6_todo.semantic_observer import parse_observation


class EvidenceStateTests(unittest.TestCase):
    def test_accept_is_append_only_and_deduplicates_by_evidence_id(self):
        state = EvidenceState()
        first = EvidenceRecord.from_tool(
            "call-1", "query", {"sql": "SELECT 1"}, "value=1"
        )
        state.accept(first)
        state.accept(first)
        self.assertEqual(len(state.records), 1)
        self.assertEqual(state.records[0].result_hash, first.result_hash)

    def test_review_pack_contains_tool_arguments_and_result(self):
        state = EvidenceState()
        state.accept(EvidenceRecord.from_tool(
            "call-2",
            "execute_query_tool",
            {"query": "SELECT department, COUNT(*) AS n FROM employees"},
            "department n\nผลิต 3",
        ))
        packed = state.render_for_review()
        self.assertIn("execute_query_tool", packed)
        self.assertIn("ผลิต 3", packed)
        self.assertIn("SELECT department", packed)

    def test_parse_rewrite_requires_complete_revised_answer(self):
        observation = parse_observation("""{
          "verdict": "rewrite",
          "reason": "unsupported currency",
          "supported_claims": ["total is 28"],
          "unsupported_claims": ["currency is THB"],
          "contradictions": [],
          "revised_answer": "มูลค่ารวม 28 โดย schema ไม่ระบุสกุลเงิน"
        }""")
        self.assertEqual(observation.verdict, SemanticVerdict.REWRITE)
        self.assertIn("ไม่ระบุสกุลเงิน", observation.revised_answer)

        with self.assertRaisesRegex(ValueError, "requires revised_answer"):
            parse_observation("""{
              "verdict": "rewrite",
              "reason": "bad",
              "revised_answer": null
            }""")

    def test_parse_query_more_accepts_fenced_json(self):
        observation = parse_observation("""```json
        {
          "verdict": "query_more",
          "reason": "need distinct employee count",
          "supported_claims": [],
          "unsupported_claims": [],
          "contradictions": [],
          "revised_answer": null
        }
        ```""")
        self.assertEqual(observation.verdict, SemanticVerdict.QUERY_MORE)


if __name__ == "__main__":
    unittest.main()
