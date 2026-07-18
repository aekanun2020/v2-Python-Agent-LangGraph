import unittest

from langchain_core.messages import AIMessage, HumanMessage

from scripts.compare_lab8 import count_tool_calls, render_comparison_html


class Lab8ComparisonTests(unittest.TestCase):
    def test_count_tool_calls(self):
        messages = [
            HumanMessage(content="question"),
            AIMessage(content="", tool_calls=[{"name": "a", "args": {}, "id": "1", "type": "tool_call"}]),
            AIMessage(content="done"),
        ]
        self.assertEqual(count_tool_calls(messages), 1)

    def test_render_html_is_compact_and_excludes_full_answers(self):
        summary = {
            "model": "model",
            "baseline": {"tool_calls": 1, "elapsed_ms": 10, "answer": "<unsafe>"},
            "planner_v2": {
                "tool_calls": 2, "elapsed_ms": 20, "revisions": 3,
                "completed_steps": 4, "total_steps": 4, "approved": True,
                "answer": "safe",
            },
        }
        rendered = render_comparison_html(summary)
        self.assertNotIn("<unsafe>", rendered)
        self.assertNotIn("&lt;unsafe&gt;", rendered)
        self.assertIn("KEY EVIDENCE FROM THIS RUN", rendered)
        self.assertIn("APPROVED", rendered)


if __name__ == "__main__":
    unittest.main()
