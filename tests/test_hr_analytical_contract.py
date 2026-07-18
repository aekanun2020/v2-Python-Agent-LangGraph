import unittest

from scripts.hr_analytical_contract import validate_sql


class HRAnalyticalContractTests(unittest.TestCase):
    def test_rejects_raw_multi_satellite_join(self):
        query = "SELECT * FROM employees e JOIN skills s ON s.employee_id=e.employee_id JOIN projects p ON p.employee_id=e.employee_id"
        reason = validate_sql("skills_project_risk", "execute_query_tool", {"query": query})
        self.assertIn("fan-out", reason)

    def test_accepts_separate_employee_aggregates(self):
        query = """WITH s AS (SELECT employee_id, COUNT(*) n FROM skills GROUP BY employee_id),
        t AS (SELECT employee_id, SUM(hours) h FROM training_records GROUP BY employee_id),
        p AS (SELECT employee_id, SUM(project_value) v FROM projects GROUP BY employee_id)
        SELECT * FROM employees e LEFT JOIN s ON s.employee_id=e.employee_id
        LEFT JOIN t ON t.employee_id=e.employee_id LEFT JOIN p ON p.employee_id=e.employee_id"""
        self.assertIsNone(validate_sql("skills_project_risk", "execute_query_tool", {"query": query}))


if __name__ == "__main__":
    unittest.main()
