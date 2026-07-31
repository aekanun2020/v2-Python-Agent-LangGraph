import json
import unittest
from pathlib import Path

from labs.lab6_todo.claim_gate import verify_then_emit
from labs.lab6_todo.evidence_contract import (
    contract_claims,
    metric_contract_status,
    select_metric_contract,
)
from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    ObservationState,
    SemanticVerdict,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "skills"
    / "finance-analytics"
    / "references"
    / "answer_contracts.json"
)

Q1 = (
    "พอร์ตสินเชื่อทั้งหมดมีกี่รายการ ยอดวงเงินที่ขอ loan_amnt "
    "และยอดที่ได้รับ funding funded_amnt รวมเท่าใด "
    "และค่าเฉลี่ยต่อรายการเท่าใด"
)


def contract(identifier: str) -> dict:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return next(
        item for item in payload["contracts"]
        if item["id"] == identifier
    )


class FinanceSkillContractTests(unittest.TestCase):
    def test_all_ten_finance_contracts_are_loaded(self):
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["contracts"]), 10)
        self.assertEqual(
            select_metric_contract(Q1)["id"],
            "finance_portfolio_totals",
        )

    def test_generic_emitter_preserves_every_required_metric(self):
        selected = contract("finance_portfolio_totals")
        query = selected["roles"][0]["query_template"]
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "finance-q1",
            "execute_query_tool",
            {"query": query},
            (
                " loan_count requested_total   funded_total requested_avg   funded_avg\n"
                "    1432440  22017159100.00 22017131100.00  15370.388358 15370.368811"
            ),
        ))
        status = metric_contract_status(Q1, evidence)
        self.assertTrue(status.satisfied)
        claims = contract_claims(Q1, evidence)
        emitted = "\n".join(claims)
        for expected in (
            "loan_count=1432440",
            "requested_total=22017159100.00",
            "funded_total=22017131100.00",
            "requested_avg=15370.388358",
            "funded_avg=15370.368811",
            "ไม่มี currency metadata",
        ):
            self.assertIn(expected, emitted)

    def test_contract_output_replaces_unsupported_agent_story(self):
        selected = contract("finance_application_mix")
        question = (
            "สัดส่วนจำนวนรายการระหว่าง application_type แบบ Individual "
            "และ Joint App เป็นเท่าใด รายงานร้อยละของพอร์ต"
        )
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "finance-q2",
            "execute_query_tool",
            {"query": selected["roles"][0]["query_template"]},
            (
                "application_type  loan_count  portfolio_pct\n"
                "Individual          1320357         92.1754\n"
                "Joint App            112083          7.8246"
            ),
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="unsupported recommendation",
        )
        answer = verify_then_emit(
            question,
            observation,
            evidence,
            proposed_answer=(
                "Joint App เป็นโอกาสพัฒนาผลิตภัณฑ์ "
                "และควรเพิ่มการตลาด"
            ),
        )
        self.assertIn("application_type=Individual", answer)
        self.assertIn("application_type=Joint App", answer)
        self.assertNotIn("โอกาส", answer)
        self.assertNotIn("ควร", answer)

    def test_missing_required_column_fails_closed(self):
        selected = contract("finance_portfolio_totals")
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "finance-q1-incomplete",
            "execute_query_tool",
            {"query": selected["roles"][0]["query_template"]},
            "loan_count  requested_total\n1432440  22017159100.00",
        ))
        self.assertFalse(metric_contract_status(Q1, evidence).satisfied)


if __name__ == "__main__":
    unittest.main()
