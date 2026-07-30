import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from labs.core import config
from labs.lab6_todo.agent_todo import dispatch_with_retry
from labs.lab6_todo.claim_ledger import (
    ClaimLedger,
    ClaimRequirement,
    ClaimStatus,
)
from labs.lab6_todo.claim_gate import (
    ClaimType,
    classify_claim,
    verify_then_emit,
)
from labs.lab6_todo.dynamic_observer import (
    NextAction,
    observe_tool_result,
)
from labs.lab6_todo.evidence_state import (
    EvidenceRecord,
    EvidenceState,
    ObservationState,
    SemanticVerdict,
    SemanticViolation,
)
from labs.lab6_todo.evidence_contract import (
    ContractDecision,
    contract_claims,
    metric_contract_status,
    missing_role_queries,
    repair_query_arguments,
    terminal_contract_verdict,
    validate_evidence_contract,
)
from labs.lab6_todo.phase2_runtime import (
    Phase2Budget,
    RuntimeBudgetExhausted,
    hard_deadline,
)
from labs.lab6_todo.semantic_observer import (
    apply_bounded_rewrite,
    enforce_claim_alignment,
    parse_observation,
    review_final_answer,
)
from labs.lab6_todo.risk_router import (
    DeterministicDecision,
    final_semantic_risk,
    observe_deterministically,
)


def fake_response(payload: dict):
    message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


class Phase2BTests(unittest.TestCase):
    @staticmethod
    def http_error(status: int) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "https://example.test/mcp")
        response = httpx.Response(status, request=request)
        return httpx.HTTPStatusError(
            f"status {status}",
            request=request,
            response=response,
        )

    def test_claim_ledger_tracks_proof_and_contradiction_by_known_id(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "count active employees by department",
                "department",
                ("department", "employee_count"),
            ),
            ClaimRequirement("claim_002", "approval decision exists", "metadata"),
        ])
        ledger.mark_proved(["claim_001", "unknown"], "call-1")
        ledger.mark_contradicted(
            {"claim_002": "schema has no decision field", "unknown": "ignored"},
            "call-2",
        )
        self.assertEqual(ledger.claims[0].status, ClaimStatus.PROVED)
        self.assertEqual(ledger.claims[0].evidence_ids, ["call-1"])
        self.assertEqual(ledger.claims[1].status, ClaimStatus.CONTRADICTED)
        self.assertEqual(ledger.claims[1].evidence_ids, ["call-2"])

    def test_claim_requirements_can_be_revised_from_schema(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "count employees",
                "entity",
                ("entity_id", "department_id"),
            )
        ])
        ledger.revise_requirements({
            "claim_001": (
                "employee",
                ("employee_id", "department"),
            )
        })
        self.assertEqual(ledger.claims[0].required_grain, "employee")
        self.assertEqual(
            ledger.claims[0].required_fields,
            ("employee_id", "department"),
        )

    def test_user_input_constraints_are_preproved_with_provenance(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_policy",
                "threshold and comparison supplied by user",
                "metadata",
                ("threshold", "comparison_operator"),
                evidence_source="user_input",
            ),
            ClaimRequirement(
                "claim_data",
                "retrieved aggregate",
                "aggregate",
                ("total",),
            ),
        ])
        ledger.accept_user_input_claims()
        self.assertEqual(
            ledger.claims[0].status,
            ClaimStatus.PROVED,
        )
        self.assertEqual(
            ledger.claims[0].evidence_ids,
            ["user_question"],
        )
        self.assertEqual(
            ledger.claims[1].status,
            ClaimStatus.REQUIRED,
        )

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_dynamic_observer_extracts_facts_and_filters_unknown_claims(
        self,
        chat,
    ):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": True,
            "grain": "department",
            "fields": ["department", "employee_count"],
            "canonical_labels": ["ผลิต"],
            "facts": [{
                "subject": "ผลิต",
                "predicate": "employee_count",
                "value": 3,
                "unit": "person",
                "grain": "department",
                "derivation": None,
            }],
            "proved_claim_ids": ["claim_001", "invented_claim"],
            "contradictions": [],
            "missing_evidence": [],
            "next_action": "accept",
            "reason": "grouped count returned",
        })
        ledger = ClaimLedger([
            ClaimRequirement("claim_001", "count by department", "department")
        ])
        record = EvidenceRecord.from_tool(
            "call-1",
            "execute_query_tool",
            {"query": "SELECT department, COUNT(*) FROM employees"},
            "department employee_count\nผลิต 3",
        )
        observation = observe_tool_result(
            "นับพนักงานแยกแผนก",
            "query grouped count",
            ledger,
            record,
        )
        self.assertEqual(observation.next_action, NextAction.ACCEPT)
        self.assertEqual(observation.proved_claim_ids, ("claim_001",))
        self.assertEqual(observation.facts[0].evidence_id, "call-1")
        self.assertEqual(observation.canonical_labels, ("ผลิต",))
        self.assertEqual(chat.call_args.kwargs["model"], config.OBSERVER_MODEL)

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_query_more_names_specific_missing_evidence(self, chat):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": False,
            "grain": "record",
            "fields": ["review_id"],
            "canonical_labels": [],
            "facts": [],
            "proved_claim_ids": [],
            "contradictions": [],
            "missing_evidence": [{
                "claim_id": "claim_001",
                "grain": "employee",
                "fields": ["employee_id"],
                "operation": "COUNT(DISTINCT employee_id)",
                "reason": "record count cannot prove employee coverage",
            }],
            "next_action": "query_more",
            "reason": "record count cannot prove employee coverage",
        })
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001", "distinct employee coverage", "employee"
            )
        ])
        observation = observe_tool_result(
            "คำนวณ employee coverage",
            "count reviews",
            ledger,
            EvidenceRecord.from_tool(
                "call-2", "execute_query_tool", {}, "review_count=7"
            ),
        )
        self.assertEqual(observation.next_action, NextAction.QUERY_MORE)
        request = observation.missing_evidence[0]
        self.assertEqual(request.claim_id, "claim_001")
        self.assertEqual(request.grain, "employee")
        self.assertIn("COUNT(DISTINCT", request.operation)

    def test_claim_proof_requires_matching_grain_and_fields(self):
        ledger = ClaimLedger([
            ClaimRequirement(
                "claim_001",
                "distinct employee coverage",
                "employee",
                ("employee_id", "coverage"),
            )
        ])
        rejected = ledger.mark_proved_if_covered(
            ["claim_001"],
            "call-records",
            "record",
            ("review_id", "coverage"),
        )
        self.assertEqual(rejected, ())
        self.assertEqual(ledger.claims[0].status, ClaimStatus.REQUIRED)

        accepted = ledger.mark_proved_if_covered(
            ["claim_001"],
            "call-employees",
            "employee",
            ("employee_id", "coverage"),
        )
        self.assertEqual(accepted, ("claim_001",))
        self.assertTrue(ledger.complete)

    def test_bounded_rewrite_applies_exact_violations_once(self):
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="unsupported currency",
            violations=(
                SemanticViolation("unit", " บาท", ""),
            ),
            revised_answer="มูลค่ารวม 28,000,000 บาท",
        )
        result = apply_bounded_rewrite("ignored", observation)
        self.assertEqual(result, "มูลค่ารวม 28,000,000")

    @patch("labs.lab6_todo.semantic_observer.llm.chat")
    def test_final_observer_uses_configured_observer_model(self, chat):
        chat.return_value = fake_response({
            "verdict": "approve",
            "reason": "grounded",
            "supported_claims": [],
            "unsupported_claims": [],
            "contradictions": [],
            "violations": [],
            "revised_answer": None,
        })
        review_final_answer(
            "นับพนักงาน",
            "มี 25 คน",
            EvidenceState(),
        )
        self.assertEqual(chat.call_args.kwargs["model"], config.OBSERVER_MODEL)

    def test_semantic_observer_accepts_literal_control_character_in_json(self):
        observation = parse_observation(
            '{"verdict":"approve","reason":"line one\nline two",'
            '"supported_claims":[],"unsupported_claims":[],'
            '"contradictions":[],"violations":[],"revised_answer":null}'
        )
        self.assertEqual(observation.verdict, SemanticVerdict.APPROVE)

    def test_final_approval_is_downgraded_for_unresolved_claims(self):
        ledger = ClaimLedger([
            ClaimRequirement("claim_001", "needs evidence", "entity")
        ])
        approved = ObservationState(
            verdict=SemanticVerdict.APPROVE,
            reason="looks correct",
        )
        aligned = enforce_claim_alignment(approved, ledger)
        self.assertEqual(aligned.verdict, SemanticVerdict.QUERY_MORE)
        self.assertIn("claim_001", aligned.reason)

    @patch("labs.lab6_todo.dynamic_observer.llm.chat")
    def test_extractor_drops_ungrounded_labels_values_and_units(self, chat):
        chat.return_value = fake_response({
            "action_succeeded": True,
            "supports_active_step": True,
            "evidence_complete": True,
            "grain": "project",
            "fields": ["project_name", "project_value"],
            "canonical_labels": ["โครงการจริง", "โครงการแต่ง"],
            "facts": [{
                "subject": "โครงการจริง",
                "predicate": "project_value",
                "value": 100,
                "unit": "บาท",
                "grain": "project",
                "derivation": None,
            }, {
                "subject": "โครงการแต่ง",
                "predicate": "project_value",
                "value": 999,
                "unit": "บาท",
                "grain": "project",
                "derivation": None,
            }],
            "proved_claim_ids": ["claim_001"],
            "contradictions": [],
            "missing_evidence": [],
            "claim_updates": [],
            "next_action": "accept",
            "reason": "complete",
        })
        observation = observe_tool_result(
            "project value",
            "query projects",
            ClaimLedger([
                ClaimRequirement(
                    "claim_001",
                    "project values",
                    "project",
                    ("project_name", "project_value"),
                )
            ]),
            EvidenceRecord.from_tool(
                "call-project",
                "execute_query_tool",
                {},
                "project_name project_value\nโครงการจริง 100",
            ),
        )
        self.assertEqual(observation.canonical_labels, ("โครงการจริง",))
        self.assertEqual(len(observation.facts), 1)
        self.assertIsNone(observation.facts[0].unit)

    @patch("labs.lab6_todo.phase2_runtime.time.monotonic")
    def test_whole_run_budget_and_call_budgets_are_enforced(self, monotonic):
        monotonic.side_effect = [100.0, 101.0, 101.0, 106.0]
        budget = Phase2Budget(max_seconds=5, max_agent_calls=1)
        budget.consume_agent()
        with self.assertRaises(RuntimeBudgetExhausted):
            budget.consume_agent()
        with self.assertRaises(RuntimeBudgetExhausted):
            budget.check_time()

    def test_hard_deadline_interrupts_blocking_work(self):
        with self.assertRaises(RuntimeBudgetExhausted):
            with hard_deadline(0.02):
                time.sleep(0.2)

    def test_python_observer_accepts_simple_result_without_llm_risk(self):
        record = EvidenceRecord.from_tool(
            "call-simple",
            "execute_query_tool",
            {"query": "SELECT department, COUNT(*) AS n FROM employees GROUP BY department"},
            "department  n\nผลิต  3",
        )
        result = observe_deterministically("นับแยกแผนก", record)
        self.assertEqual(result.decision, DeterministicDecision.ACCEPT)
        self.assertFalse(result.semantic_risk)

    def test_python_observer_routes_distinct_ratio_to_llm(self):
        record = EvidenceRecord.from_tool(
            "call-risk",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(DISTINCT employee_id) * 100.0 / "
                    "COUNT(*) AS coverage FROM reviews"
                )
            },
            "coverage\n28.0",
        )
        result = observe_deterministically("คำนวณ coverage", record)
        self.assertTrue(result.semantic_risk)
        self.assertIn("distinct-grain", result.risk_reasons)
        self.assertIn("derived-ratio", result.risk_reasons)

    def test_python_observer_retries_error_payload(self):
        record = EvidenceRecord.from_tool(
            "call-error",
            "execute_query_tool",
            {},
            '{"status": "error", "message": "syntax error"}',
        )
        result = observe_deterministically("query", record)
        self.assertEqual(result.decision, DeterministicDecision.RETRY)
        self.assertFalse(result.semantic_risk)

    def test_final_router_detects_unsupported_number_and_decision(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-final",
            "execute_query_tool",
            {},
            "department n\nผลิต 3",
        ))
        risks = final_semantic_risk(
            "แผนกใดควรเพิ่มคน",
            "ผลิตมี 9 คน จึงควรเพิ่มคน",
            evidence,
        )
        self.assertTrue(any(item.startswith("unsupported-numbers:") for item in risks))
        self.assertIn("semantic-decision", risks)

    def test_final_router_detects_unsupported_qualitative_interpretation(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-qualitative",
            "execute_query_tool",
            {},
            "department n\nเทคโนโลยีสารสนเทศ 5",
        ))
        risks = final_semantic_risk(
            "นับพนักงานแยกแผนก",
            "มี 5 คน สะท้อนถึงความสำคัญของการลงทุนด้านไอที",
            evidence,
        )
        self.assertIn("qualitative-interpretation", risks)

    def test_claim_gate_emits_allowlist_not_revised_draft(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-count",
            "execute_query_tool",
            {},
            "active_count\n25",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="remove unsupported interpretation",
            supported_claims=("พนักงานที่ปฏิบัติงานมี 25 คน",),
            unsupported_claims=("องค์กรให้ความสำคัญกับไอที",),
            revised_answer="องค์กรควรลงทุนด้านไอที",
        )
        emitted = verify_then_emit(
            "นับพนักงานที่ปฏิบัติงาน",
            observation,
            evidence,
        )
        self.assertIn("25", emitted)
        self.assertNotIn("ลงทุน", emitted)

    def test_claim_gate_recovers_grounded_numeric_lines_from_agent_draft(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-department",
            "execute_query_tool",
            {},
            "department employee_count\nผลิต 3\nบัญชี 2",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="observer omitted facts",
            supported_claims=(),
            revised_answer="ignored",
        )
        emitted = verify_then_emit(
            "นับพนักงานแยกแผนก",
            observation,
            evidence,
            proposed_answer=(
                "- ผลิต: 3 คน\n"
                "- บัญชี: 2 คน\n"
                "- ผลิตมี 3 คน สะท้อนถึงความสำคัญของฝ่ายผลิต"
            ),
        )
        self.assertIn("ผลิต: 3 คน", emitted)
        self.assertIn("บัญชี: 2 คน", emitted)
        self.assertNotIn("สะท้อน", emitted)

    def test_direct_zero_claim_cannot_pass_via_arithmetic_closure(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-total",
            "execute_query_tool",
            {},
            "employee_count\n25",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.APPROVE,
            reason="incorrect observer claim",
            supported_claims=("There are 0 active employees.",),
        )
        emitted = verify_then_emit(
            "นับพนักงานที่ปฏิบัติงาน",
            observation,
            evidence,
        )
        self.assertNotIn("0 active employees", emitted)

    def test_claim_gate_rejects_currency_absent_from_evidence(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-project",
            "execute_query_tool",
            {},
            "project_value\n28000000",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="remove unsupported unit",
            supported_claims=("มูลค่าโครงการรวม 28,000,000 บาท",),
        )
        emitted = verify_then_emit(
            "ตรวจ project concentration",
            observation,
            evidence,
        )
        self.assertNotIn("บาท", emitted)

    def test_claim_gate_rejects_efficiency_relabelling_and_refuses(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-ratio",
            "execute_query_tool",
            {},
            "department project_value_per_employee\n"
            "วิจัยและพัฒนา 3333333.33\n"
            "เทคโนโลยีสารสนเทศ 1000000",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="ratio is not efficiency",
            supported_claims=(
                "วิจัยและพัฒนามี project value ต่อพนักงาน 3333333.33",
                "เทคโนโลยีสารสนเทศมี project value ต่อพนักงาน 1000000",
                "วิจัยและพัฒนามีประสิทธิภาพสูงกว่า",
            ),
        )
        emitted = verify_then_emit(
            "จงสรุปว่าแผนกใดมีประสิทธิภาพกว่ากัน",
            observation,
            evidence,
        )
        self.assertIn("3333333.33", emitted)
        self.assertIn("1000000", emitted)
        self.assertNotIn("มีประสิทธิภาพสูงกว่า", emitted)
        self.assertIn("ไม่เพียงพอ", emitted)

    def test_claim_gate_derives_literal_per_employee_ratio(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-ratio-inputs",
            "execute_query_tool",
            {},
            "department employee_count project_value\n"
            "วิจัยและพัฒนา 3 10000000\n"
            "เทคโนโลยีสารสนเทศ 5 5000000",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="retain inputs but refuse efficiency",
            supported_claims=(
                "วิจัยและพัฒนา มีพนักงาน 3 คน",
                "วิจัยและพัฒนา มีโครงการรวมมูลค่า 10,000,000",
                "เทคโนโลยีสารสนเทศ มีพนักงาน 5 คน",
                "เทคโนโลยีสารสนเทศ มีโครงการรวมมูลค่า 5,000,000",
            ),
        )
        emitted = verify_then_emit(
            "แผนกใดมีประสิทธิภาพกว่ากัน",
            observation,
            evidence,
        )
        self.assertIn("3333333.33", emitted)
        self.assertIn("1000000.00", emitted)
        self.assertIn("ไม่เพียงพอ", emitted)

    def test_question_operands_require_mcp_corroboration_before_ratio(self):
        question = (
            "พบว่า `วิจัยและพัฒนา` มีพนักงาน 3 คน และมีโครงการมูลค่า "
            "10,000,000 ส่วน `เทคโนโลยีสารสนเทศ` มีพนักงาน 5 คน"
            "และมีโครงการมูลค่า 5,000,000 compare efficiency"
        )
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="observer omitted descriptive operands",
        )
        empty = verify_then_emit(
            question,
            observation,
            EvidenceState(),
        )
        self.assertNotIn("3333333.33", empty)

        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-corroboration",
            "execute_query_tool",
            {},
            "department employees project_value\n"
            "วิจัยและพัฒนา 3 10000000\n"
            "เทคโนโลยีสารสนเทศ 5 5000000",
        ))
        emitted = verify_then_emit(question, observation, evidence)
        self.assertIn("3333333.33", emitted)
        self.assertIn("1000000.00", emitted)

    def test_claim_gate_retains_declared_strict_threshold(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-policy",
            "execute_query_tool",
            {},
            "department numerator denominator pct\n"
            "ทรัพยากรบุคคล 3 4 75",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="observer omitted boundary wording",
            supported_claims=(
                "ทรัพยากรบุคคลมีพนักงานสัญญา 3 จาก 4 คน เท่ากับ 75%",
            ),
        )
        emitted = verify_then_emit(
            "เข้าเกณฑ์เมื่อพนักงานสัญญามากกว่า 50%",
            observation,
            evidence,
        )
        self.assertIn("75% มากกว่าเกณฑ์ 50%", emitted)

    def test_claim_gate_derives_total_for_evidenced_unit_components(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-hours",
            "execute_query_tool",
            {},
            "training_type hours pct\n"
            "ภายนอก 152 60.32\nออนไลน์ 92 36.51\nภายใน 8 3.17",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="grounded components",
            supported_claims=(
                "ภายนอก 152 ชั่วโมง (60.32%)",
                "ออนไลน์ 92 ชั่วโมง (36.51%)",
                "ภายใน 8 ชั่วโมง (3.17%)",
            ),
        )
        emitted = verify_then_emit(
            "ชั่วโมงอบรมทั้งหมดมีสัดส่วนตามประเภทอย่างไร",
            observation,
            evidence,
        )
        self.assertIn("รวมทั้งหมด 252 ชั่วโมง", emitted)

    def test_existing_total_prevents_duplicate_component_sum(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-hours-total",
            "execute_query_tool",
            {},
            "training_type hours pct\n"
            "ภายนอก 152 60.32\nออนไลน์ 92 36.51\nภายใน 8 3.17",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="grounded total and components",
            supported_claims=(
                "ชั่วโมงอบรมทั้งหมดคือ 252 ชั่วโมง",
                "ภายนอก 152 ชั่วโมง (60.32%)",
                "ออนไลน์ 92 ชั่วโมง (36.51%)",
                "ภายใน 8 ชั่วโมง (3.17%)",
            ),
        )
        emitted = verify_then_emit(
            "ชั่วโมงอบรมทั้งหมดมีสัดส่วนตามประเภทอย่างไร",
            observation,
            evidence,
        )
        self.assertNotIn("312.32", emitted)

    def test_certificate_contract_requires_both_evidence_roles(self):
        question = (
            "ทุกรายการมี certificate_obtained หรือไม่ และพิสูจน์ได้หรือไม่"
            "ว่าทุกคนมี certification ที่ยังใช้ได้"
        )
        evidence = EvidenceState()
        missing = dict(missing_role_queries(question, evidence))
        self.assertEqual(
            set(missing),
            {"training_certificate_flags", "certification_entity_records"},
        )
        for role_id, query in missing.items():
            if role_id == "training_certificate_flags":
                result = (
                    "training_record_count obtained_true_count\n"
                    "11 11"
                )
            else:
                result = (
                    "certification_record_count certified_employee_count\n"
                    "7 7"
                )
            evidence.accept(EvidenceRecord.from_tool(
                f"contract_{role_id}",
                "execute_query_tool",
                {"query": query},
                result,
            ))
        self.assertTrue(metric_contract_status(question, evidence).satisfied)
        claims = contract_claims(question, evidence)
        self.assertTrue(any("11 รายการ" in claim for claim in claims))
        self.assertTrue(
            any("ไม่ใช่หลักฐาน" in claim for claim in claims)
        )
        self.assertEqual(
            terminal_contract_verdict(question),
            "refuse_decision",
        )

    def test_training_hours_contract_composes_total_shares_and_policy(self):
        question = (
            "ชั่วโมงอบรมกระจายตาม training_type อย่างไร และประเภทใด"
            "เกิน concentration limit 50%"
        )
        evidence = EvidenceState()
        ((role_id, query),) = missing_role_queries(question, evidence)
        self.assertEqual(role_id, "hours_by_training_type")
        evidence.accept(EvidenceRecord.from_tool(
            "contract_hours_by_training_type",
            "execute_query_tool",
            {"query": query},
            (
                "training_type  training_hours share_pct\n"
                "ภายนอก        152 60.32\n"
                "ออนไลน์        92 36.51\n"
                "ภายใน          8 3.17"
            ),
        ))
        claims = contract_claims(question, evidence)
        self.assertIn("ชั่วโมงอบรมทั้งหมดคือ 252 ชั่วโมง", claims)
        self.assertTrue(
            any(
                "ภายนอก 152 ชั่วโมง (60.32%)" in claim
                and "เกินนโยบาย" in claim
                for claim in claims
            )
        )

    def test_staffing_contract_is_terminal_fail_closed(self):
        question = (
            "จาก headcount และ project value จงเลือกแผนกที่ควรลดคน "
            "และแผนกที่ควรเพิ่มคน พร้อมเหตุผลเชิงธุรกิจ"
        )
        self.assertEqual(
            terminal_contract_verdict(question),
            "refuse_decision",
        )

    def test_efficiency_contract_emits_literal_ratios_and_refuses_label(self):
        question = (
            "จากข้อมูล `วิจัยและพัฒนา` มีพนักงาน 3 คน และมีโครงการมูลค่า "
            "10,000,000 ส่วน `เทคโนโลยีสารสนเทศ` มีพนักงาน 5 คน "
            "และมีโครงการมูลค่า 5,000,000 แผนกใดมีประสิทธิภาพกว่า"
        )
        evidence = EvidenceState()
        ((role_id, query),) = missing_role_queries(question, evidence)
        self.assertEqual(role_id, "department_value_and_headcount")
        evidence.accept(EvidenceRecord.from_tool(
            "contract_department_value_and_headcount",
            "execute_query_tool",
            {"query": query},
            (
                "department            active_employee_count project_value\n"
                "วิจัยและพัฒนา                           3      10000000\n"
                "เทคโนโลยีสารสนเทศ                       5       5000000"
            ),
        ))
        claims = contract_claims(question, evidence)
        self.assertTrue(any("3333333.33" in claim for claim in claims))
        self.assertTrue(any("1000000.00" in claim for claim in claims))
        self.assertEqual(
            terminal_contract_verdict(question),
            "refuse_decision",
        )

    def test_expert_skill_contract_preserves_record_grain_and_totals(self):
        question = (
            "จาก skill records วิเคราะห์ระดับ เชี่ยวชาญ เทียบเป้าหมาย 50% "
            "แยกตาม skill_category"
        )
        evidence = EvidenceState()
        ((role_id, query),) = missing_role_queries(question, evidence)
        self.assertEqual(role_id, "expert_share_by_category")
        evidence.accept(EvidenceRecord.from_tool(
            "contract_expert_share_by_category",
            "execute_query_tool",
            {"query": query},
            (
                "skill_category  total_skills expert_count\n"
                "การสื่อสาร                  1 0\n"
                "คอมพิวเตอร์                 3 1\n"
                "บริหาร                      3 1\n"
                "รวมทั้งหมด                 15 6\n"
                "เทคนิค                      8 4"
            ),
        ))
        claims = contract_claims(question, evidence)
        self.assertTrue(
            any(
                "รวมทั้งหมด" in claim
                and "15 รายการ" in claim
                and "6 รายการ" in claim
                and "40.00%" in claim
                for claim in claims
            )
        )
        self.assertEqual(terminal_contract_verdict(question), "approve")

    def test_project_concentration_contract_composes_policy_verdict(self):
        question = (
            "มี concentration risk หากมูลค่าสูงสุดสองอันดับเกิน 60% "
            "จงตรวจตามนโยบาย"
        )
        evidence = EvidenceState()
        ((role_id, query),) = missing_role_queries(question, evidence)
        self.assertEqual(role_id, "portfolio_total_and_top_two")
        evidence.accept(EvidenceRecord.from_tool(
            "contract_portfolio_total_and_top_two",
            "execute_query_tool",
            {"query": query},
            "total_project_value top_two_project_value\n28000000 18000000",
        ))
        claims = contract_claims(question, evidence)
        self.assertTrue(any("28000000" in claim for claim in claims))
        self.assertTrue(any("18000000" in claim for claim in claims))
        self.assertTrue(any("64.29%" in claim for claim in claims))
        self.assertIn("มี concentration risk", claims)
        self.assertTrue(all("บาท" not in claim for claim in claims))
        self.assertEqual(terminal_contract_verdict(question), "approve")

    def test_review_coverage_contract_rejects_review_date_proxy(self):
        question = (
            "performance review ปี 2023 คำนวณ evidence coverage "
            "และตรวจเกณฑ์ 80%"
        )
        record = EvidenceRecord.from_tool(
            "call-wrong-year",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(DISTINCT employee_id) "
                    "FROM performance_reviews "
                    "WHERE YEAR(review_date) = 2023"
                )
            },
            "reviewed_employee_count\n0",
        )
        result = validate_evidence_contract(question, record)
        self.assertEqual(result.decision, ContractDecision.QUERY_MORE)

    def test_claim_gate_refuses_decision_and_drops_recommendation(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-staff",
            "execute_query_tool",
            {},
            "department headcount\nการตลาด 4",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REFUSE_DECISION,
            reason="missing workload and demand evidence",
            supported_claims=(
                "การตลาดมีพนักงาน 4 คน",
                "ควรลดพนักงานการตลาด",
            ),
            revised_answer="ควรลดพนักงานการตลาด",
        )
        emitted = verify_then_emit(
            "ควรเพิ่มหรือลดคนในแผนกใด",
            observation,
            evidence,
        )
        self.assertIn("การตลาดมีพนักงาน 4 คน", emitted)
        self.assertIn("ไม่เพียงพอ", emitted)
        self.assertNotIn("ควรลดพนักงาน", emitted)
        self.assertEqual(
            classify_claim("ควรลดพนักงานการตลาด"),
            ClaimType.RECOMMENDATION,
        )

    def test_numeric_gate_accepts_transparent_percentage_arithmetic(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-coverage",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(DISTINCT employee_id) "
                    "FROM performance_reviews"
                )
            },
            "employees reviews\n25 7",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="grounded arithmetic",
            supported_claims=(
                "Coverage ของ distinct employees เท่ากับ 28%",
                "Coverage ของ distinct employees ต่ำกว่าเกณฑ์ 80% อยู่ 52 percentage points",
            ),
            revised_answer="ignored",
        )
        emitted = verify_then_emit(
            "ตรวจเกณฑ์ขั้นต่ำ 80%",
            observation,
            evidence,
        )
        self.assertIn("28%", emitted)
        self.assertIn("52 percentage points", emitted)

    def test_coverage_is_composed_from_distinct_numerator_and_denominator(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-distinct-coverage",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(DISTINCT employee_id) "
                    "FROM performance_reviews"
                )
            },
            "distinct_reviewed\n7",
        ))
        evidence.accept(EvidenceRecord.from_tool(
            "call-active-total",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(*) FROM employees "
                    "WHERE status = N'ปฏิบัติงาน'"
                )
            },
            "active_total\n25",
        ))
        observation = ObservationState(
            verdict=SemanticVerdict.REWRITE,
            reason="compose coverage",
            supported_claims=(
                "จำนวนพนักงานที่ปฏิบัติงานทั้งหมดคือ 25 คน",
                "จำนวนพนักงานที่มี performance review คือ 7 คน",
                "ขาด 52% จากเกณฑ์",
            ),
            revised_answer="ignored",
        )
        emitted = verify_then_emit(
            "คำนวณ evidence coverage และตรวจเกณฑ์ 80%",
            observation,
            evidence,
        )
        self.assertIn("7 / 25 = 28%", emitted)
        self.assertIn("52 percentage points", emitted)
        self.assertNotIn("ขาด 52%", emitted)

    def test_final_router_ignores_ordered_list_numbers(self):
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-list",
            "execute_query_tool",
            {},
            "department n\nผลิต 3\nบัญชี 2",
        ))
        risks = final_semantic_risk(
            "นับแยกแผนก",
            "1. ผลิต 3 คน\n2. บัญชี 2 คน",
            evidence,
        )
        self.assertEqual(risks, ())

    def test_final_router_rejects_empty_answer(self):
        self.assertEqual(
            final_semantic_risk("นับพนักงาน", " \n", EvidenceState()),
            ("empty-answer",),
        )

    def test_evidence_contract_rejects_unsafe_mssql_unicode_filter(self):
        record = EvidenceRecord.from_tool(
            "call-unicode",
            "execute_query_tool",
            {"query": "SELECT COUNT(*) FROM employees WHERE status = 'ปฏิบัติงาน'"},
            "employee_count\n0",
        )
        result = validate_evidence_contract("นับพนักงาน", record)
        self.assertEqual(result.decision, ContractDecision.REJECT)

    def test_evidence_contract_accepts_mssql_unicode_filter_with_n_prefix(self):
        record = EvidenceRecord.from_tool(
            "call-unicode-safe",
            "execute_query_tool",
            {"query": "SELECT COUNT(*) FROM employees WHERE status = N'ปฏิบัติงาน'"},
            "employee_count\n25",
        )
        result = validate_evidence_contract("นับพนักงาน", record)
        self.assertEqual(result.decision, ContractDecision.ACCEPT)

    def test_evidence_contract_requires_distinct_entity_for_coverage(self):
        record = EvidenceRecord.from_tool(
            "call-coverage-grain",
            "execute_query_tool",
            {"query": "SELECT COUNT(*) FROM performance_reviews WHERE review_period = '2023'"},
            "review_count\n7",
        )
        result = validate_evidence_contract(
            "คำนวณ evidence coverage",
            record,
        )
        self.assertEqual(result.decision, ContractDecision.QUERY_MORE)

    def test_headcount_contract_rejects_incomplete_max_only_query(self):
        question = (
            "พนักงานที่มีสถานะ `ปฏิบัติงาน` มีกี่คน "
            "และแยกตาม `department` อย่างไร"
        )
        record = EvidenceRecord.from_tool(
            "call-max-only",
            "execute_query_tool",
            {
                "query": (
                    "SELECT TOP 1 department, COUNT(*) AS employee_count "
                    "FROM employees WHERE status = N'ปฏิบัติงาน' "
                    "GROUP BY department ORDER BY employee_count DESC"
                )
            },
            "department employee_count\nเทคโนโลยีสารสนเทศ 5",
        )
        result = validate_evidence_contract(question, record)
        self.assertEqual(result.decision, ContractDecision.QUERY_MORE)

    def test_metric_contract_status_requires_every_query_role(self):
        question = (
            "มีพนักงาน 25 คนและ performance review 7 รายการ "
            "จงคำนวณ evidence coverage เทียบเกณฑ์ 80%"
        )
        evidence = EvidenceState()
        evidence.accept(EvidenceRecord.from_tool(
            "call-denominator",
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(*) AS active_count FROM employees "
                    "WHERE status = N'ปฏิบัติงาน'"
                )
            },
            "active_count\n25",
        ))
        status = metric_contract_status(question, evidence)
        self.assertFalse(status.satisfied)
        self.assertIn(
            "distinct_reviewed_employee_numerator",
            status.missing_roles,
        )

    def test_query_contract_repairs_unicode_and_coverage_grain(self):
        question = (
            "performance review evidence coverage เทียบเกณฑ์ 80%"
        )
        repaired, changes = repair_query_arguments(
            question,
            "execute_query_tool",
            {
                "query": (
                    "SELECT COUNT(*) FROM performance_reviews "
                    "WHERE review_period = 'ปี 2023'"
                )
            },
        )
        self.assertIn("COUNT(DISTINCT employee_id)", repaired["query"])
        self.assertIn("N'ปี 2023'", repaired["query"])
        self.assertIn("coverage-distinct-employee", changes)
        self.assertIn("mssql-unicode-prefix", changes)

    def test_evidence_state_renders_structured_observation(self):
        state = EvidenceState()
        state.accept(EvidenceRecord.from_tool(
            "call-3", "query", {}, "department=ผลิต,n=3"
        ))
        # Reuse a minimal duck-typed observation to ensure storage stays
        # independent from the LLM orchestration module.
        fact = SimpleNamespace(
            subject="ผลิต",
            predicate="employee_count",
            value=3,
            unit="person",
            grain="department",
            evidence_id="call-3",
            derivation=None,
        )
        observation = SimpleNamespace(
            evidence_id="call-3",
            action_succeeded=True,
            supports_active_step=True,
            evidence_complete=True,
            grain="department",
            fields=("department", "employee_count"),
            canonical_labels=("ผลิต",),
            facts=(fact,),
            proved_claim_ids=("claim_001",),
            contradictions=(),
            missing_evidence=(),
            claim_updates=(),
            next_action=NextAction.ACCEPT,
            reason="complete",
        )
        state.add_observation(observation)
        rendered = state.render_structured()
        self.assertIn('"grain": "department"', rendered)
        self.assertIn('"evidence_id": "call-3"', rendered)

    @patch("labs.lab6_todo.agent_todo.time.sleep")
    def test_mcp_retry_recovers_from_transient_503(self, sleep):
        registry = SimpleNamespace()
        registry.dispatch = unittest.mock.Mock(side_effect=[
            self.http_error(503),
            "rows",
        ])
        result = dispatch_with_retry(registry, "query", {})
        self.assertEqual(result, "rows")
        self.assertEqual(registry.dispatch.call_count, 2)
        sleep.assert_called_once_with(0.5)

    @patch("labs.lab6_todo.agent_todo.time.sleep")
    def test_mcp_retry_does_not_retry_permanent_400(self, sleep):
        registry = SimpleNamespace()
        registry.dispatch = unittest.mock.Mock(
            side_effect=self.http_error(400)
        )
        with self.assertRaises(httpx.HTTPStatusError):
            dispatch_with_retry(registry, "query", {})
        self.assertEqual(registry.dispatch.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
