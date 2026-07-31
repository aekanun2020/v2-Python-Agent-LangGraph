import json
import unittest
from pathlib import Path

from labs.lab6_todo.evidence_contract import (
    contract_claims,
    select_metric_contract,
)
from labs.lab6_todo.evidence_state import EvidenceRecord, EvidenceState


ROOT = Path(__file__).resolve().parents[1]


def payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class HRSkillIsolationTests(unittest.TestCase):
    def test_generic_runtime_contains_no_domain_contracts(self):
        generic = payload(
            ROOT
            / "labs"
            / "lab6_todo"
            / "executable_metric_contracts.json"
        )
        self.assertEqual(generic["contracts"], [])

    def test_hr_and_finance_contracts_are_isolated(self):
        hr = payload(
            ROOT
            / "skills"
            / "hr-analytics"
            / "references"
            / "answer_contracts.json"
        )
        finance = payload(
            ROOT
            / "skills"
            / "finance-analytics"
            / "references"
            / "answer_contracts.json"
        )
        self.assertEqual(len(hr["contracts"]), 10)
        self.assertEqual(len(finance["contracts"]), 10)
        hr_ids = {item["id"] for item in hr["contracts"]}
        finance_ids = {item["id"] for item in finance["contracts"]}
        self.assertFalse(hr_ids & finance_ids)

    def test_selector_discovers_both_skills(self):
        hr = select_metric_contract(
            "นับพนักงานที่มีสถานะปฏิบัติงานแยกตาม department"
        )
        finance = select_metric_contract(
            "พอร์ต loan_amnt และ funded_amnt รวมและค่าเฉลี่ยต่อรายการ"
        )
        self.assertEqual(
            hr["id"],
            "active_headcount_by_department",
        )
        self.assertEqual(
            finance["id"],
            "finance_portfolio_totals",
        )

    def test_hr_contract_declares_percentage_suffix(self):
        question = (
            "สำหรับพนักงานสถานะปฏิบัติงาน จงแสดงจำนวนพนักงานประจำ "
            "และสัญญาของแต่ละแผนก พร้อมคำนวณสัดส่วน"
        )
        selected = select_metric_contract(question)
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "hr-mix",
            "execute_query_tool",
            {"query": selected["roles"][0]["query_template"]},
            (
                "department  regular_count  contract_count  "
                "employee_count  contract_pct\n"
                "เทคโนโลยีสารสนเทศ  4  1  5  20.0\n"
                "การเงิน  3  0  3  0.0\n"
                "การตลาด  2  2  4  50.0\n"
                "ทรัพยากรบุคคล  1  3  4  75.0\n"
                "บริหารทั่วไป  1  0  1  0.0\n"
                "บัญชี  2  0  2  0.0\n"
                "ผลิต  3  0  3  0.0\n"
                "วิจัยและพัฒนา  3  0  3  0.0"
            ),
        ))
        self.assertIn(
            "contract_pct=50.0%",
            "\n".join(contract_claims(question, evidence)),
        )


if __name__ == "__main__":
    unittest.main()
