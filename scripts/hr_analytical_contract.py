"""Deterministic analytical contract shared by HR benchmark agents."""

from __future__ import annotations

import re


SKILLS_PROJECT_RISK_CONTRACT = """
[ANALYTICAL CONTRACT — ต้องใช้เหมือนกันทุก Agent]
1. Population: employees.status = N'ปฏิบัติงาน'.
2. Grain: aggregate skills, training_records, latest performance review และ projects
   ให้เหลือหนึ่งแถวต่อ employee_id ใน CTE แยกกันก่อน join employees.
3. Department metrics: headcount, pct_skill_coverage, avg_skill_count,
   avg_training_hours, avg_latest_review_score, project_value_per_head.
4. Risk flags จาก SQL จริงเท่านั้น:
   f1 = project_value_per_head > median ของทุกแผนก
   f2 = pct_skill_coverage < 40
   f3 = avg_skill_count < 1.0
   f4 = avg_training_hours < 10
   f5 = ไม่มี latest review
   risk_score = f1+f2+f3+f4+f5; HIGH >=4, MEDIUM 2-3, LOW <=1.
5. ห้ามสร้างสูตรหรือน้ำหนักใหม่ และต้องรายงานว่า missing record ไม่เท่ากับไม่มีทักษะ/อบรม.
""".strip()


def contract_for(challenge_id: str) -> str:
    return SKILLS_PROJECT_RISK_CONTRACT if challenge_id == "skills_project_risk" else ""


def validate_sql(challenge_id: str, tool_name: str, arguments: dict) -> str | None:
    """Return a rejection reason, or None when the call satisfies the contract."""
    if challenge_id != "skills_project_risk" or tool_name != "execute_query_tool":
        return None
    sql = str(arguments.get("query", ""))
    lowered = re.sub(r"\s+", " ", sql.lower())
    satellite_joins = sum(
        f"join {table}" in lowered
        for table in ("skills", "training_records", "performance_reviews", "projects")
    )
    if satellite_joins >= 2:
        employee_aggregates = len(re.findall(r"group by\s+(?:\w+\.)?employee_id", lowered))
        if "with " not in lowered or employee_aggregates < 3:
            return (
                "fan-out risk: aggregate satellite tables in separate CTEs to one row "
                "per employee_id before joining employees"
            )
    if "risk_score" in lowered:
        required = ("project_value_per_head", "pct_skill", "avg_skill", "avg_training")
        missing = [token for token in required if token not in lowered]
        if missing:
            return "risk_score query is missing contract inputs: " + ", ".join(missing)
    return None

