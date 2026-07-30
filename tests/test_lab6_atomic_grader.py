import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "grade_lab6_frozen_replay.py"
SPEC = importlib.util.spec_from_file_location("atomic_grader", SCRIPT)
grader = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = grader
SPEC.loader.exec_module(grader)


class AtomicGraderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (ROOT / "tests/fixtures/lab6_claim_gate_frozen.json").read_text(
                encoding="utf-8"
            )
        )

    def test_replay_is_bit_for_bit_deterministic(self):
        first = grader.grade_fixture(self.fixture)
        second = grader.grade_fixture(self.fixture)
        self.assertEqual(first, second)
        self.assertEqual(first["result_sha256"], second["result_sha256"])

    def test_atomic_items_expose_gate_effect_without_llm_judge(self):
        result = grader.grade_fixture(self.fixture)["variants"]
        self.assertLess(
            result["gate_off"]["atomic_rate"],
            result["gate_on"]["atomic_rate"],
        )
        self.assertEqual(result["gate_off"]["questions_passed"], 0)
        self.assertEqual(result["gate_on"]["questions_passed"], 3)

    def test_q10_scores_refusal_and_fact_retention_separately(self):
        result = grader.grade_fixture(self.fixture)["variants"]["gate_on"]
        items = {
            item["item_id"]: item["passed"]
            for item in result["questions"]["q10_staffing_decision"]["items"]
        }
        self.assertTrue(items["q10.refuse_decision"])
        self.assertTrue(items["q10.no_staffing_recommendation"])
        self.assertTrue(items["q10.retain_descriptive_facts"])

    def test_metric_contracts_cover_all_ten_questions(self):
        contracts = json.loads(
            (ROOT / "labs/lab6_todo/hr_metric_contracts.json").read_text(
                encoding="utf-8"
            )
        )["contracts"]
        self.assertEqual(set(contracts), set(grader.GRADERS))
        for contract in contracts.values():
            self.assertIn("grain", contract)
            self.assertIn("metric", contract)
            self.assertIn("ground_truth", contract)

    def test_live_artifact_atomic_grade_is_replay_stable(self):
        artifact = json.loads(
            (ROOT / "artifacts/lab6_phase2a_phase2d_live_10.json").read_text(
                encoding="utf-8"
            )
        )
        fixture = grader.fixture_from_run_artifact(artifact)
        first = grader.grade_fixture(fixture)
        second = grader.grade_fixture(fixture)
        self.assertEqual(first["result_sha256"], second["result_sha256"])
        self.assertEqual(
            first["variants"]["phase2a_final_only"]["atomic_passed"],
            45,
        )
        self.assertEqual(
            first["variants"]["phase2c_python_first"]["atomic_passed"],
            61,
        )


if __name__ == "__main__":
    unittest.main()
