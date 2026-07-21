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

    def test_successful_query_with_wrong_population_and_grain_is_retried(self):
        obs = observe_result(
            step_description="นับพนักงานที่ปฏิบัติงานแยกแผนก",
            tool="execute_query_tool",
            tool_arguments={"query": "SELECT COUNT(*) AS headcount FROM employees"},
            result='[{"headcount":100}]',
            semantic_checks=True,
        )
        self.assertEqual(obs.result_type, "query_result")
        self.assertEqual(obs.decision, "retry")
        self.assertIn("semantic:active_employee_population", obs.failed)
        self.assertIn("semantic:department_grain", obs.failed)

    def test_correct_population_and_grain_are_accepted(self):
        obs = observe_result(
            step_description="นับพนักงานที่ปฏิบัติงานแยกแผนก",
            tool="execute_query_tool",
            tool_arguments={"query": (
                "SELECT department_id, COUNT(*) AS headcount FROM employees "
                "WHERE status = N'ปฏิบัติงาน' GROUP BY department_id"
            )},
            result='[{"department_id":1,"headcount":10}]',
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "accept")
        self.assertIn("semantic:active_employee_population", obs.passed)
        self.assertIn("semantic:department_grain", obs.passed)

    def test_percentage_without_denominator_is_retried(self):
        obs = observe_result(
            step_description="คำนวณเปอร์เซ็นต์ skill coverage",
            tool="execute_query_tool", result='[{"skilled":20}]',
            tool_arguments={"query": "SELECT COUNT(*) AS skilled FROM skills"},
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "retry")
        self.assertIn("semantic:explicit_denominator", obs.failed)

    def test_training_without_latest_pre_review_window_is_retried(self):
        obs = observe_result(
            step_description="รวมชั่วโมงอบรมก่อน review ล่าสุด",
            tool="execute_query_tool", result='[{"hours":40}]',
            tool_arguments={"query": "SELECT SUM(hours) AS hours FROM training_records"},
            semantic_checks=True,
        )
        self.assertEqual(obs.decision, "retry")
        self.assertIn("semantic:pre_review_time_window", obs.failed)
        self.assertIn("semantic:latest_review_anchor", obs.failed)

    def test_raw_multi_satellite_join_is_retried(self):
        obs = observe_result(
            step_description="join skills และ projects โดยป้องกันยอดซ้ำ",
            tool="execute_query_tool", result='[{"rows":100}]',
            tool_arguments={"query": (
                "SELECT COUNT(*) rows FROM employees e JOIN skills s ON e.employee_id=s.employee_id "
                "JOIN projects p ON e.employee_id=p.employee_id"
            )}, semantic_checks=True,
        )
        self.assertEqual(obs.decision, "retry")
        self.assertIn("semantic:safe_join_cardinality", obs.failed)

    def test_cross_evidence_contradiction_is_retried(self):
        obs = observe_result(
            step_description="ยืนยัน active headcount กับหลักฐานก่อนหน้า",
            tool="execute_query_tool", result='{"active_headcount":100}',
            tool_arguments={"query": "SELECT COUNT(*) active_headcount FROM employees"},
            semantic_checks=True, prior_facts={"active_headcount": 88},
        )
        self.assertEqual(obs.decision, "retry")
        self.assertIn("semantic:cross_evidence_consistency", obs.failed)


if __name__ == "__main__":
    unittest.main()
