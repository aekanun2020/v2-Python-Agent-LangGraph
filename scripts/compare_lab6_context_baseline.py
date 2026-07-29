"""Run the 10-question HR baseline against original and context-state Lab 6.

This runner measures execution facts only.  Semantic grading is deliberately
kept separate because Phase 1 is observe-only and must not grade itself.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


QUESTIONS = [
    {
        "id": "q01_headcount",
        "level": 1,
        "question": (
            "พนักงานที่มีสถานะ `ปฏิบัติงาน` มีทั้งหมดกี่คน "
            "และแยกตามค่า `department` ในฐานข้อมูลอย่างไร"
        ),
        "semantic_risk": "canonical labels and exact counts",
    },
    {
        "id": "q02_employment_mix",
        "level": 2,
        "question": (
            "สำหรับพนักงานสถานะ `ปฏิบัติงาน` จงแสดงจำนวนพนักงาน `ประจำ` "
            "และ `สัญญา` ของแต่ละแผนก พร้อมคำนวณสัดส่วนพนักงานสัญญา"
            "ต่อจำนวนพนักงานของแผนก"
        ),
        "semantic_risk": "correct denominator and no relabelling",
    },
    {
        "id": "q03_contract_policy",
        "level": 3,
        "question": (
            "บริษัทกำหนดว่าแผนกมีความเสี่ยงด้าน contract dependency "
            "เมื่อพนักงานสัญญามากกว่า 50% ของพนักงานที่ปฏิบัติงานในแผนก "
            "แผนกใดเข้าเกณฑ์ แสดง numerator, denominator และอัตราร้อยละ"
        ),
        "semantic_risk": "strict greater-than boundary",
    },
    {
        "id": "q04_review_coverage",
        "level": 4,
        "question": (
            "มีพนักงานที่ปฏิบัติงาน 25 คน แต่มี performance review ปี 2023 "
            "จำนวน 7 รายการ ก่อนเปรียบเทียบผลงานระหว่างแผนก จงคำนวณ "
            "evidence coverage และประเมินว่าผ่านเกณฑ์ขั้นต่ำ 80% หรือไม่"
        ),
        "semantic_risk": "records are not necessarily distinct employees",
    },
    {
        "id": "q05_training_portfolio",
        "level": 5,
        "question": (
            "ชั่วโมงอบรมของบริษัทกระจายตาม `training_type` อย่างไร "
            "และประเภทใดเกินนโยบาย concentration limit 50% "
            "ของชั่วโมงอบรมทั้งหมด"
        ),
        "semantic_risk": "hours share, not course-count share",
    },
    {
        "id": "q06_certificate_semantics",
        "level": 6,
        "question": (
            "ทุกรายการอบรมมี `certificate_obtained = True` หรือไม่ "
            "และข้อมูลนี้พิสูจน์ได้หรือไม่ว่าพนักงานทุกคนมี certification "
            "ที่ยังใช้ได้"
        ),
        "semantic_risk": "training certificate is not certification validity",
    },
    {
        "id": "q07_expert_skill",
        "level": 7,
        "question": (
            "จาก skill records ทั้งหมด จงวิเคราะห์สัดส่วนระดับ `เชี่ยวชาญ` "
            "และตรวจว่าสูงถึงเป้าหมาย 50% หรือไม่ พร้อมแยกตาม `skill_category`"
        ),
        "semantic_risk": "record grain is not employee grain",
    },
    {
        "id": "q08_project_concentration",
        "level": 8,
        "question": (
            "บริษัทกำหนดว่า project portfolio มี concentration risk "
            "หากโครงการมูลค่าสูงสุดสองอันดับรวมกันเกิน 60% "
            "ของมูลค่าทุกโครงการ จงตรวจตามนโยบายนี้"
        ),
        "semantic_risk": "top-two ratio and missing currency metadata",
    },
    {
        "id": "q09_efficiency_trap",
        "level": 9,
        "question": (
            "จากข้อมูลพบว่า `วิจัยและพัฒนา` มีพนักงานปฏิบัติงาน 3 คน "
            "และมีโครงการมูลค่า 10,000,000 ส่วน `เทคโนโลยีสารสนเทศ` "
            "มีพนักงาน 5 คนและโครงการมูลค่า 5,000,000 "
            "จงสรุปว่าแผนกใดใช้กำลังคนมีประสิทธิภาพกว่ากัน"
        ),
        "semantic_risk": "project value per head is not efficiency",
    },
    {
        "id": "q10_staffing_decision",
        "level": 10,
        "question": (
            "จาก headcount, employment type, performance reviews, training, "
            "skills, certifications และ project value จงเลือกหนึ่งแผนกที่ควรลดคน "
            "และหนึ่งแผนกที่ควรเพิ่มคน พร้อมเหตุผลเชิงธุรกิจ"
        ),
        "semantic_risk": "insufficient evidence for staffing decision",
    },
]


def extract_answer(output: str) -> str:
    match = re.search(
        r"\[answer\]\n(.*?)(?:\n-{20,}|\n\[todo สุดท้าย\])",
        output,
        flags=re.DOTALL,
    )
    answer = match.group(1).strip() if match else ""
    return "" if answer in {"None", "null"} else answer


def run_one(repo: Path, question: str, timeout: int) -> dict:
    command = [
        sys.executable,
        "labs/lab6_todo/agent_todo.py",
        question,
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        returncode = None
    elapsed = time.perf_counter() - started
    return {
        "elapsed_seconds": round(elapsed, 3),
        "returncode": returncode,
        "timed_out": timed_out,
        "completed_with_answer": bool(extract_answer(stdout)),
        "mcp_tool_calls": len(re.findall(r"\] TOOL ", stdout)),
        "context_alerts": len(re.findall(r"\[CONTEXT ALERT\]", stdout)),
        "answer": extract_answer(stdout),
        "stdout": stdout,
        "stderr": stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    variants = {
        "original_49f6f10": args.original_dir.resolve(),
        "context_state_phase1": args.current_dir.resolve(),
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("OPENROUTER_MODEL", ""),
        "mcp_server": os.environ.get("MCP_SERVER_URL", ""),
        "questions": QUESTIONS,
        "runs": [],
    }

    for question in QUESTIONS:
        for variant, repo in variants.items():
            print(f"[RUN] {question['id']} {variant}", flush=True)
            result = run_one(repo, question["question"], args.timeout)
            payload["runs"].append(
                {
                    "question_id": question["id"],
                    "level": question["level"],
                    "variant": variant,
                    **result,
                }
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print(f"[SAVED] {args.output}")


if __name__ == "__main__":
    main()
