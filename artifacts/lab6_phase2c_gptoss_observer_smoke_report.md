# Phase 2C: Qwen Agent + GPT-OSS Observer Live Smoke

Date: 2026-07-30

## Configuration

- Agent: `qwen/qwen3.5-35b-a3b`
- Dynamic/Final Semantic Observer: `openai/gpt-oss-120b`
- MCP: live MSSQL over the configured ngrok endpoint
- Questions: Q1, Q4, Q10
- Unit/regression tests before live run: 29 passed

## Result

| Question | Time | Runtime completed | Strict grounded result |
|---|---:|---:|---:|
| Q1 active headcount | 24.713s | yes | fail |
| Q4 review coverage | 33.828s | yes | pass |
| Q10 staffing decision | 68.197s | yes | fail |

## Findings

The model split is wired correctly. The raw artifact records
`qwen/qwen3.5-35b-a3b` as the Agent and `openai/gpt-oss-120b` as the Observer.
Low-risk tool results bypass the LLM Observer, while semantic-risk results and
answers invoke it.

Q4 was successfully rewritten to the supported counts, 28% coverage, failure
against the user-supplied 80% threshold, and a 52 percentage-point shortfall.

Q1 failed because deterministic final routing did not classify unsupported
textual business interpretations as risky when they introduced no new number.
The answer inferred investment priorities, innovation balance, specialist
skills, and employment strategy without direct evidence.

Q10 failed even though GPT-OSS identified unsupported business recommendations.
It returned `rewrite`, but the current exact-span bounded rewrite did not remove
the unsupported recommendation to reduce Marketing staff and add IT staff.

## Decision

Do not treat the split model as a quality improvement yet, and do not run or
publish a full 10-question benchmark as if the smoke had passed. The next
architecture change should strengthen generic claim-level final enforcement:

1. route unsupported qualitative claims, not only unsupported numbers;
2. require a complete revised answer for `rewrite`;
3. deterministically downgrade an unsafe/incomplete rewrite to
   `refuse_decision` rather than returning the original recommendation.

Raw evidence: `artifacts/lab6_phase2c_gptoss_observer_smoke.json`.
