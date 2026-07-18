import unittest

from labs.lab8_langgraph.agent_langgraph import (
    PlanReview,
    PlannerState,
    apply_review,
    render_plan,
)


class PlannerStateTests(unittest.TestCase):
    def test_apply_review_increments_revision_when_plan_changes(self):
        old: PlannerState = {
        "goal": "หาจำนวนพนักงาน",
        "steps": [
            {"id": 1, "description": "ค้น schema", "status": "in_progress", "evidence": []},
            {"id": 2, "description": "query จำนวน", "status": "pending", "evidence": []},
        ],
        "assumptions": [],
        "revision": 1,
        "last_reason": "สร้างแผนเริ่มต้น",
        "ready_to_answer": False,
        }
        review = PlanReview.model_validate({
            "sufficient": False,
            "reason": "พบว่าต้อง join departments จึงเพิ่มขั้นตรวจ relationship",
            "steps": [
                {"id": 1, "description": "ค้น schema", "status": "completed", "evidence": ["พบ Employees"]},
                {"id": 2, "description": "ตรวจ relationship Employees-Departments", "status": "in_progress"},
                {"id": 3, "description": "query จำนวน", "status": "pending"},
            ],
        })

        updated = apply_review(old, review)

        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(updated["steps"]), 3)
        self.assertEqual(updated["steps"][0]["evidence"], ["พบ Employees"])
        self.assertIn("join departments", updated["last_reason"])
        self.assertFalse(updated["ready_to_answer"])

    def test_render_plan_exposes_status_evidence_and_revision(self):
        planner: PlannerState = {
        "goal": "ตอบคำถาม",
        "steps": [{"id": 1, "description": "ตรวจ schema", "status": "completed", "evidence": ["Employees"]}],
        "assumptions": ["status=ปฏิบัติงาน"],
        "revision": 3,
        "last_reason": "ผลใหม่",
        "ready_to_answer": False,
        }

        rendered = render_plan(planner)

        self.assertIn("revision 3", rendered)
        self.assertIn("completed", rendered)
        self.assertIn("Employees", rendered)
        self.assertIn("status=ปฏิบัติงาน", rendered)


if __name__ == "__main__":
    unittest.main()
