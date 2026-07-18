"""Compare both Lab 8 graphs on a researched, schema-validated HR challenge."""

import argparse
import asyncio
import json
from pathlib import Path

from scripts.compare_lab8 import render_comparison_html, run_comparison
from scripts.hr_challenges import HR_CHALLENGES


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", choices=HR_CHALLENGES, default="skills_project_risk")
    parser.add_argument("--output-prefix", default="artifacts/lab8_hr_comparison")
    args = parser.parse_args()
    challenge = HR_CHALLENGES[args.challenge]
    print(f"[HR CHALLENGE] {args.challenge}: {challenge['title']}")
    print(f"[REQUIRED FIELDS] {len(challenge['required_fields'])} fields validated by validate_hr_challenges.py")
    summary = await run_comparison(challenge["question"])
    summary["challenge_id"] = args.challenge
    summary["research"] = {
        "community_basis": challenge["community_basis"],
        "sources": challenge["sources"],
        "required_fields": challenge["required_fields"],
    }
    html_path = Path(f"{args.output_prefix}_{args.challenge}.html")
    json_path = Path(f"{args.output_prefix}_{args.challenge}.json")
    html_path.write_text(render_comparison_html(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ARTIFACT] {html_path}")
    print(f"[ARTIFACT] {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
