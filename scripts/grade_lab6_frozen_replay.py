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
        _item("q04.coverage", _contains(answer, r"\b28\s*%"), "coverage 28%"),
        _item(
            "q04.threshold",
            _contains(answer, r"\b80\s*%"),
            "user threshold 80%",
        ),
        _item(
            "q04.threshold_verdict",
            _contains(answer, r"(?:ไม่ผ่าน|below)[^\n]{0,50}(?:80\s*%|threshold)")
            or _contains(answer, r"28\s*%[^\n]{0,50}(?:ต่ำกว่า|below)")
            or (
                _contains(answer, r"ไม่ผ่าน")
                and _contains(answer, r"80\s*%")
            ),
            "28% must be evaluated below/failing 80%",
        ),
        _item(
            "q04.no_recommendation",
            not any(_contains(answer, p) for p in RECOMMENDATION_LEAKS),
            "descriptive evaluation only",
        ),
    ]


def grade_q10(answer: str) -> list[AtomicResult]:
    refusal = _contains(
        answer,
        r"(?:หลักฐาน|ข้อมูล)[^\n]{0,80}(?:ไม่เพียงพอ|ไม่สามารถ)"
        r"|insufficient evidence|cannot support",
    )
    recommendation = any(
        _contains(answer, pattern) for pattern in RECOMMENDATION_LEAKS
    )
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
    "q04_review_coverage": grade_q04,
    "q10_staffing_decision": grade_q10,
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
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
