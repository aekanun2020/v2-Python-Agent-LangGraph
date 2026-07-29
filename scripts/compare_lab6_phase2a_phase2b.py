"""Run the 10-question HR suite against Phase 2A and Phase 2B.

Phase 2A keeps the final semantic observer but disables post-tool dynamic
observation. Phase 2B enables both. The runner records raw output and
execution facts; semantic scoring is intentionally performed separately.
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

from compare_lab6_context_baseline import QUESTIONS, extract_answer


VARIANTS = {
    "phase2a_final_only": {
        "semantic_observer": "on",
        "dynamic_observer": "off",
    },
    "phase2b_dynamic_and_final": {
        "semantic_observer": "on",
        "dynamic_observer": "on",
    },
}


def run_one(
    repo: Path,
    question: str,
    variant: dict[str, str],
    timeout: int,
) -> dict:
    command = [
        sys.executable,
        "labs/lab6_todo/agent_todo.py",
        "--semantic-observer",
        variant["semantic_observer"],
        "--dynamic-observer",
        variant["dynamic_observer"],
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

    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")

    elapsed = time.perf_counter() - started
    answer = extract_answer(stdout)
    return {
        "elapsed_seconds": round(elapsed, 3),
        "returncode": returncode,
        "timed_out": timed_out,
        "completed_with_answer": bool(answer),
        "mcp_tool_calls": len(re.findall(r"\] TOOL (?!BLOCKED)", stdout)),
        "blocked_tool_calls": len(re.findall(r"\] TOOL BLOCKED", stdout)),
        "dynamic_observations": len(
            re.findall(r"\[DYNAMIC OBSERVATION\]", stdout)
        ),
        "final_verdicts": re.findall(
            r"\[FINAL (?:OBSERVATION|RECHECK)\] verdict=([a-z_]+)",
            stdout,
        ),
        "answer": answer,
        "stdout": stdout,
        "stderr": stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument(
        "--question-id",
        action="append",
        help="Run only selected IDs; may be supplied more than once.",
    )
    args = parser.parse_args()

    selected = set(args.question_id or [])
    questions = [
        question
        for question in QUESTIONS
        if not selected or question["id"] in selected
    ]
    unknown = selected - {question["id"] for question in QUESTIONS}
    if unknown:
        raise SystemExit(f"Unknown question IDs: {sorted(unknown)}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("OPENROUTER_MODEL", ""),
        "mcp_server": os.environ.get("MCP_SERVER_URL", ""),
        "comparison": VARIANTS,
        "questions": questions,
        "runs": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    for question in questions:
        for variant_name, variant in VARIANTS.items():
            print(f"[RUN] {question['id']} {variant_name}", flush=True)
            result = run_one(
                args.repo.resolve(),
                question["question"],
                variant,
                args.timeout,
            )
            payload["runs"].append(
                {
                    "question_id": question["id"],
                    "level": question["level"],
                    "variant": variant_name,
                    **result,
                }
            )
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"[DONE] answer={result['completed_with_answer']} "
                f"timeout={result['timed_out']} "
                f"elapsed={result['elapsed_seconds']}s",
                flush=True,
            )

    print(f"[SAVED] {args.output}", flush=True)


if __name__ == "__main__":
    main()
