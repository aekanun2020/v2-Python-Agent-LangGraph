import unittest

from scripts.evaluate_skill_routing import evaluate_routing, load_cases


class UnseenBoundaryEvaluationTests(unittest.TestCase):
    def test_suite_has_ten_cases_per_domain_and_kind(self):
        cases = load_cases()
        counts = {}
        for item in cases:
            key = (item["domain"], item["kind"])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(counts, {
            ("hr", "paraphrase"): 10,
            ("hr", "boundary"): 10,
            ("finance", "paraphrase"): 10,
            ("finance", "boundary"): 10,
        })

    def test_identifiers_are_unique(self):
        identifiers = [item["id"] for item in load_cases()]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_routing_evaluator_is_deterministic(self):
        cases = load_cases()
        first = evaluate_routing(cases)
        second = evaluate_routing(cases)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
