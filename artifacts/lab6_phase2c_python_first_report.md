# Lab 6 Phase 2C — Python-First Observation

Date: 2026-07-29

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

## Architecture

```text
Agent tool call
  -> Python Observer
       error / empty / fields / numeric evidence / risk signature
  -> low risk: accept without reviewer LLM
  -> high semantic risk: one LLM Observer per risk signature
  -> proposed answer
  -> Python final risk check
  -> low risk: answer directly
  -> high risk: one Final Semantic Observer
  -> answer or one bounded rewrite
```

Removed from the mandatory critical path:

- Claim Planner LLM
- LLM observation after every tool result
- mandatory Final Observer
- post-rewrite LLM recheck

## Generic Python checks

- explicit error and empty-result payloads;
- result fields;
- unsupported final-answer numbers;
- SQL risk signals such as `COUNT(DISTINCT ...)`, joins, ratios, conditional
  metrics, time validity, and aggregate comparisons;
- semantic decision signals such as recommendation, causation, efficiency,
  risk, approval, and staffing language;
- repeated risk signatures are not reviewed repeatedly.

These checks route risk; they do not encode HR answers.

## Live smoke result

Raw output:
[`lab6_phase2c_python_first_smoke.json`](lab6_phase2c_python_first_smoke.json)

| Question | Previous Phase 2B | Phase 2C | Tool-result LLM observations | Result |
|---|---:|---:|---:|---|
| Q1 active headcount | ~181 s | 26.8 s | 0 | Correct 25-person department breakdown |
| Q4 review coverage | ~181 s | 27.5 s | 0 | Correct 7/25 = 28%, below 80% |
| Q10 staffing decision | ~181 s | 55.2 s | 2 risk signatures | Correctly refused unsupported staffing decision |

All three runs completed without timeout or unresolved-claim rejection.

Q1 exposed one routing false positive: an ordered-list marker such as `6.` was
read as an unsupported number. The numeric parser now excludes ordered-list
markers and has a regression test.

## Automated verification

- Pure Python tests: **29 passed**
- syntax compilation: passed
- simple grouped queries route without an LLM observer;
- distinct/ratio queries route to semantic review;
- tool errors route to retry;
- unsupported final numbers and decision language route to final review;
- ordered-list numbers do not trigger review.

## Status

Phase 2C passes the three-question smoke test and restores practical latency.
It is not yet proven on the complete 10-question suite. The next test should
run all 10 questions once against Phase 2A and Phase 2C before any merge.
