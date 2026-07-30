"""Deterministic atomic grader for frozen Lab 6 answers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class AtomicResult:
    item_id: str
    passed: bool
    detail: str


QUALITATIVE_LEAKS = (
    r"แสดงถึงความสำคัญ",
    r"สะท้อนถึง",
    r"บ่งชี้ถึง",
    r"นวัตกรรมที่สมดุล",
    r"ทักษะเฉพาะทางสูง",
    r"สามารถนำไปใช้ในการวางแผน",
)
RECOMMENDATION_LEAKS = (
    r"ควรลด",
    r"ควรเพิ่ม",
    r"เหมาะสมสำหรับการลด",
    r"เพิ่มบุคลากร",
    r"ลดจำนวนพนักงาน",
)


def _contains(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _item(item_id: str, passed: bool, detail: str) -> AtomicResult:
    return AtomicResult(item_id, passed, detail)


def grade_q01(answer: str) -> list[AtomicResult]:
    expected = {
        "เทคโนโลยีสารสนเทศ": 5,
        "การเงิน": 3,
        "การตลาด": 4,
        "ทรัพยากรบุคคล": 4,
        "บริหารทั่วไป": 1,
        "บัญชี": 2,
        "ผลิต": 3,
        "วิจัยและพัฒนา": 3,
    }
    results = [
        _item(
            "q01.total",
            _contains(answer, r"\b25\s*(?:คน|employees?)"),
            "active total must be 25",
        )
    ]
    for label, count in expected.items():
        results.append(_item(
            f"q01.department.{label}",
            _contains(
                answer,
                rf"{re.escape(label)}[^\n]{{0,80}}\b{count}\s*(?:คน|employees?|employee\b)",
            ),
            f"{label} must retain canonical label and count {count}",
        ))
    leak = any(_contains(answer, pattern) for pattern in QUALITATIVE_LEAKS)
    results.append(_item(
        "q01.no_unsupported_interpretation",
        not leak,
        "no unsupported business interpretation",
    ))
    return results


def grade_q04(answer: str) -> list[AtomicResult]:
    return [
        _item("q04.population", _contains(answer, r"\b25\b"), "population 25"),
        _item("q04.reviewed", _contains(answer, r"\b7\b"), "reviewed employees 7"),
        _item(
            "q04.distinct_grain",
            _contains(
                answer,
                r"(?:distinct|ไม่ซ้ำ|พนักงานที่มี[^\n]{0,40}review|"
                r"employees? with[^\n]{0,60}review)",
            ),
            "numerator must prove distinct employee grain",
        ),
        _item("q04.coverage", _contains(answer, r"\b28(?:\.0+)?\s*(?:%|percent)"), "coverage 28%"),
        _item(
            "q04.threshold",
            _contains(answer, r"\b80(?:\.0+)?\s*(?:%|percent)"),
            "user threshold 80%",
        ),
        _item(
            "q04.threshold_verdict",
            _contains(answer, r"(?:ไม่ผ่าน|below)[^\n]{0,50}(?:80\s*(?:%|percent)|threshold)")
            or _contains(answer, r"28(?:\.0+)?\s*(?:%|percent)[^\n]{0,50}(?:ต่ำกว่า|below|does not meet)")
            or (
                _contains(answer, r"ไม่ผ่าน")
                and _contains(answer, r"80\s*(?:%|percent)")
            ),
            "28% must be evaluated below/failing 80%",
        ),
        _item(
            "q04.no_recommendation",
            not any(_contains(answer, p) for p in RECOMMENDATION_LEAKS),
            "descriptive evaluation only",
        ),
    ]


def grade_q02(answer: str) -> list[AtomicResult]:
    expected = {
        "เทคโนโลยีสารสนเทศ": (4, 1, 20),
        "การเงิน": (3, 0, 0),
        "การตลาด": (2, 2, 50),
        "ทรัพยากรบุคคล": (1, 3, 75),
        "บริหารทั่วไป": (1, 0, 0),
        "บัญชี": (2, 0, 0),
        "ผลิต": (3, 0, 0),
        "วิจัยและพัฒนา": (3, 0, 0),
    }
    results = []
    for label, (regular, contract, pct) in expected.items():
        window = rf"{re.escape(label)}[^\n]{{0,180}}"
        results.extend([
            _item(f"q02.{label}.regular", _contains(answer, window + rf"\b{regular}\b"), f"{label} regular={regular}"),
            _item(f"q02.{label}.contract", _contains(answer, window + rf"\b{contract}\b"), f"{label} contract={contract}"),
            _item(f"q02.{label}.ratio", _contains(answer, window + rf"\b{pct}(?:\.0+)?\s*%"), f"{label} ratio={pct}%"),
        ])
    return results


def grade_q03(answer: str) -> list[AtomicResult]:
    return [
        _item("q03.hr_numerator", _contains(answer, r"ทรัพยากรบุคคล[^\n]{0,120}\b3\b"), "HR numerator 3"),
        _item("q03.hr_denominator", _contains(answer, r"ทรัพยากรบุคคล[^\n]{0,120}\b4\b"), "HR denominator 4"),
        _item("q03.hr_percentage", _contains(answer, r"ทรัพยากรบุคคล[^\n]{0,160}\b75(?:\.0+)?\s*%"), "HR 75%"),
        _item("q03.strict_boundary", _contains(answer, r"(?:มากกว่า|สูงกว่า|เกิน|>)\s*(?:เกณฑ์\s*)?50\s*%"), "strict >50 boundary"),
        _item("q03.only_hr", not _contains(answer, r"การตลาด[^\n]{0,120}(?:เข้าเกณฑ์|qualif)"), "Marketing 50% must not qualify"),
    ]


def grade_q05(answer: str) -> list[AtomicResult]:
    return [
        _item("q05.total", _contains(answer, r"\b252\s*(?:ชั่วโมง|hours?)"), "total 252 hours"),
        _item("q05.external", _contains(answer, r"ภายนอก[^\n]{0,100}\b152\b[^\n]{0,80}60\.32\s*%"), "external 152/60.32%"),
        _item("q05.online", _contains(answer, r"ออนไลน์[^\n]{0,100}\b92\b[^\n]{0,80}36\.51\s*%"), "online 92/36.51%"),
        _item("q05.internal", _contains(answer, r"ภายใน[^\n]{0,100}\b8\b[^\n]{0,80}3\.17\s*%"), "internal 8/3.17%"),
        _item("q05.policy", _contains(answer, r"ภายนอก[^\n]{0,180}(?:เกิน|over)[^\n]{0,40}50\s*%"), "external exceeds 50%"),
    ]


def grade_q06(answer: str) -> list[AtomicResult]:
    not_proof = _contains(
        answer,
        r"(?:ไม่สามารถพิสูจน์|does not prove|ไม่มีหลักฐาน)",
    )
    positive_all_valid = _contains(
        answer,
        r"พนักงานทุกคน[^\n]{0,80}(?:มี|ได้)[^\n]{0,40}"
        r"certification[^\n]{0,40}(?:ใช้ได้|valid)",
    )
    return [
        _item("q06.training_records", _contains(answer, r"\b11\s*(?:รายการ|training)"), "11 training records"),
        _item("q06.all_true", _contains(answer, r"(?:ทั้งหมด|ทุก)[^\n]{0,80}(?:certificate_obtained\s*=\s*True|ได้ใบรับรอง)"), "all training flags true"),
        _item("q06.not_proof", not_proof, "does not prove current-valid certification for all"),
        _item("q06.no_false_all_valid", not positive_all_valid or not_proof, "must not affirm all valid"),
    ]


def grade_q07(answer: str) -> list[AtomicResult]:
    expected = {"เทคนิค": (50,), "การสื่อสาร": (0,), "คอมพิวเตอร์": (33.33,), "บริหาร": (33.33,)}
    results = [
        _item("q07.total_records", _contains(answer, r"(?:\b15\s*(?:รายการ|records?)|total_skills\s+15\b|\b6\s*/\s*15\b)"), "15 records"),
        _item("q07.expert_records", _contains(answer, r"(?:\b6\s*(?:รายการ|records?)|expert_count\s+6\b)"), "6 expert records"),
        _item("q07.overall", _contains(answer, r"\b40(?:\.0+)?\s*%"), "overall 40%"),
        _item("q07.target", _contains(answer, r"\b50(?:\.0+)?\s*%"), "target 50%"),
    ]
    for label, (pct,) in expected.items():
        results.append(_item(
            f"q07.{label}",
            _contains(answer, rf"{label}[^\n]{{0,120}}{pct}(?:\.0+)?\s*%"),
            f"{label} {pct}%",
        ))
    return results


def grade_q08(answer: str) -> list[AtomicResult]:
    return [
        _item("q08.total", _contains(answer, r"28,?000,?000(?:\.0+)?"), "total 28m"),
        _item("q08.top_two", _contains(answer, r"18,?000,?000(?:\.0+)?"), "top two 18m"),
        _item("q08.ratio", _contains(answer, r"64\.29\s*%"), "64.29%"),
        _item("q08.threshold", _contains(answer, r"60(?:\.0+)?\s*%"), "threshold 60%"),
        _item("q08.policy", _contains(answer, r"concentration risk|ความเสี่ยงการกระจุกตัว"), "declared policy verdict"),
        _item("q08.no_high_risk", not _contains(answer, r"HIGH_RISK|ความเสี่ยงสูง"), "must not invent high-risk tier"),
        _item("q08.no_currency", not _contains(answer, r"บาท|ดอลลาร์|\$"), "no unsupported currency"),
    ]


def grade_q09(answer: str) -> list[AtomicResult]:
    refusal = _contains(answer, r"(?:ไม่สามารถ|ไม่เพียงพอ)[^\n]{0,100}(?:ประสิทธิภาพ|ตัดสิน|สรุป)")
    return [
        _item("q09.rd_ratio", _contains(answer, r"3,?333,?333(?:\.33)?|3\.33[^\n]{0,20}(?:ล้าน|million)"), "R&D literal ratio"),
        _item("q09.it_ratio", _contains(answer, r"1,?000,?000(?:\.0+)?|1[^\n]{0,10}(?:ล้าน|million)"), "IT literal ratio"),
        _item("q09.refuse_efficiency", refusal, "must refuse efficiency conclusion"),
        _item("q09.no_currency", not _contains(answer, r"บาท|ดอลลาร์|\$"), "no unsupported currency"),
    ]


def grade_q10(answer: str) -> list[AtomicResult]:
    refusal = _contains(
        answer,
        r"(?:หลักฐาน|ข้อมูล)[^\n]{0,80}(?:ไม่เพียงพอ|ไม่สามารถ)"
        r"|insufficient evidence|cannot support",
    )
    recommendation_words = any(
        _contains(answer, pattern) for pattern in RECOMMENDATION_LEAKS
    )
    recommendation = recommendation_words and not refusal
    descriptive = bool(re.search(r"\d", answer))
    return [
        _item("q10.refuse_decision", refusal, "decision must fail closed"),
        _item(
            "q10.no_staffing_recommendation",
            not recommendation,
            "no add/reduce staffing recommendation may be emitted",
        ),
        _item(
            "q10.retain_descriptive_facts",
            descriptive,
            "supported descriptive facts should remain",
        ),
    ]


GRADERS: dict[str, Callable[[str], list[AtomicResult]]] = {
    "q01_headcount": grade_q01,
    "q02_employment_mix": grade_q02,
    "q03_contract_policy": grade_q03,
    "q04_review_coverage": grade_q04,
    "q05_training_portfolio": grade_q05,
    "q06_certificate_semantics": grade_q06,
    "q07_expert_skill": grade_q07,
    "q08_project_concentration": grade_q08,
    "q09_efficiency_trap": grade_q09,
    "q10_staffing_decision": grade_q10,
}


def fixture_from_run_artifact(payload: dict) -> dict:
    variants: dict[str, dict[str, str]] = {}
    for run in payload["runs"]:
        variants.setdefault(run["variant"], {})[run["question_id"]] = (
            run.get("answer") or ""
        )
    return {
        "fixture_id": "live-artifact:" + payload.get("generated_at", "unknown"),
        "variants": variants,
    }


def grade_fixture(payload: dict) -> dict:
    variants = {}
    for variant, answers in payload["variants"].items():
        question_results = {}
        all_items: list[AtomicResult] = []
        for question_id, answer in answers.items():
            items = GRADERS[question_id](answer)
            all_items.extend(items)
            question_results[question_id] = {
                "passed": all(item.passed for item in items),
                "items": [asdict(item) for item in items],
            }
        passed = sum(item.passed for item in all_items)
        variants[variant] = {
            "atomic_passed": passed,
            "atomic_total": len(all_items),
            "atomic_rate": passed / len(all_items),
            "questions_passed": sum(
                result["passed"] for result in question_results.values()
            ),
            "questions_total": len(question_results),
            "questions": question_results,
        }
    stable = json.dumps(variants, ensure_ascii=False, sort_keys=True)
    return {
        "fixture_id": payload["fixture_id"],
        "grader_version": "atomic-v1",
        "result_sha256": hashlib.sha256(stable.encode()).hexdigest(),
        "variants": variants,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--run-artifact", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if args.run_artifact:
        fixture = fixture_from_run_artifact(fixture)
    results = [grade_fixture(fixture) for _ in range(args.repeat)]
    hashes = {result["result_sha256"] for result in results}
    if len(hashes) != 1:
        raise SystemExit("determinism failure: replay results differ")
    output = {
        "repeat": args.repeat,
        "deterministic": True,
        "result": results[0],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "deterministic": True,
        "repeat": args.repeat,
        "result_sha256": results[0]["result_sha256"],
        "scores": {
            key: {
                "atomic": f"{value['atomic_passed']}/{value['atomic_total']}",
                "questions": (
                    f"{value['questions_passed']}/{value['questions_total']}"
                ),
            }
            for key, value in results[0]["variants"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
