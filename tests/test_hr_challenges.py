import unittest

from scripts.hr_challenges import HR_CHALLENGES


class HRChallengeTests(unittest.TestCase):
    def test_every_challenge_has_schema_contract_and_sources(self):
        self.assertGreaterEqual(len(HR_CHALLENGES), 3)
        for challenge_id, challenge in HR_CHALLENGES.items():
            with self.subTest(challenge=challenge_id):
                self.assertGreaterEqual(len(challenge["required_fields"]), 5)
                self.assertEqual(len(challenge["required_fields"]), len(set(challenge["required_fields"])))
                self.assertGreaterEqual(len(challenge["sources"]), 2)
                self.assertTrue(all(url.startswith("https://") for url in challenge["sources"]))
                self.assertIn("SELECT", challenge["preflight_sql"].upper())


if __name__ == "__main__":
    unittest.main()
