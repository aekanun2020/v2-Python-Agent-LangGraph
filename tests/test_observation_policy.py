import unittest

from labs.lab6_todo.observation_policy import observe_result


class DynamicObservationPolicyTests(unittest.TestCase):
    def test_error_payload_requests_retry(self):
        obs = observe_result(step_description="query จำนวนพนักงาน", tool="execute_query_tool",
                             result="[MCP ERROR] 502 Bad Gateway")
        self.assertEqual(obs.result_type, "error")
        self.assertEqual(obs.decision, "retry")
        self.assertFalse(obs.supports_step)

    def test_nonempty_but_missing_payload_is_not_evidence(self):
        obs = observe_result(step_description="query metrics", tool="execute_query_tool",
                             result='{"message":"Query executed successfully, but rows omitted"}')
        self.assertEqual(obs.decision, "query_more")
        self.assertFalse(obs.sufficient)

    def test_policy_changes_with_schema_result(self):
        obs = observe_result(step_description="ตรวจ schema employees", tool="list_tables_tool",
                             result='{"tables":["employees","departments"]}')
        self.assertIn("schema_coverage", obs.policy_modules)
        self.assertEqual(obs.decision, "accept")

    def test_database_context_supports_schema_step(self):
        obs = observe_result(step_description="ตรวจ schema และ relationship",
                             tool="get_database_context",
                             result='{"tables":{"employees":["employee_id"]}}')
        self.assertEqual(obs.result_type, "schema")
        self.assertEqual(obs.decision, "accept")

    def test_schema_preview_cannot_complete_query_step(self):
        obs = observe_result(step_description="query aggregate metric",
                             tool="preview_table", result='{"rows":[{"id":1}]}')
        self.assertEqual(obs.decision, "reject")

    def test_truncated_population_result_is_not_sufficient(self):
        obs = observe_result(step_description="query aggregate metric", tool="execute_query_tool",
                             result='{"rows":[{"department":"IT"}],"truncated":true}')
        self.assertEqual(obs.decision, "query_more")
        self.assertIn("completeness", obs.policy_modules)


if __name__ == "__main__":
    unittest.main()
