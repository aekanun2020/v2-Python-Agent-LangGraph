"""Compare the same Pure Python agent with Phase 2 observer off versus on."""
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


def run_one(
    repo: Path,
    question: str,
    observer_mode: str,
    timeout: int,
) -> dict:
    command = [
        sys.executable,
        "labs/lab6_todo/agent_todo.py",
        "--semantic-observer",
        observer_mode,
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
    answer = extract_answer(stdout)
    verdicts = re.findall(
        r"\[FINAL (?:OBSERVATION|RECHECK)\] verdict=([a-z_]+)",
        stdout,
    )
    return {
        "elapsed_seconds": round(elapsed, 3),
        "returncode": returncode,
        "timed_out": timed_out,
        "completed_with_answer": bool(answer),
        "mcp_tool_calls": len(re.findall(r"\] TOOL (?!BLOCKED)", stdout)),
        "blocked_tool_calls": len(re.findall(r"\] TOOL BLOCKED", stdout)),
        "context_alerts": len(re.findall(r"\[CONTEXT ALERT\]", stdout)),
        "semantic_verdicts": verdicts,
        "answer": answer,
        "stdout": stdout,
        "stderr": stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    variants = {
        "phase1_observer_off": "off",
        "phase2_observer_on": "on",
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("OPENROUTER_MODEL", ""),
        "mcp_server": os.environ.get("MCP_SERVER_URL", ""),
        "questions": QUESTIONS,
        "runs": [],
    }
    for question in QUESTIONS:
        for variant, mode in variants.items():
            print(f"[RUN] {question['id']} {variant}", flush=True)
            result = run_one(
                args.repo.resolve(),
                question["question"],
                mode,
                args.timeout,
            )
            payload["runs"].append({
                "question_id": question["id"],
                "level": question["level"],
                "variant": variant,
                **result,
            })
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    print(f"[SAVED] {args.output}")


if __name__ == "__main__":
    main()
