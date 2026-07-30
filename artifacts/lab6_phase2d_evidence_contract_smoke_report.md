# Phase 2D Evidence Admission Contract — Live Smoke

Date: 2026-07-30

## Change

Accepted evidence is now fail-closed before claim admission:

```text
tool result
→ deterministic transport/result checks
→ evidence contract
→ accepted evidence
→ typed claim gate
```

The initial Q1 regression occurred because successful query payloads were
accepted before semantic filter checks. A zero result from an unsafe MSSQL
Unicode filter could therefore coexist with correct evidence and later be
selected by the final Observer.

The new generic contracts:

1. reject non-`N` MSSQL Unicode literals;
2. require distinct entity grain for coverage numerators;
3. admit only deterministic `accept` results.

## Live result

Models:

- Agent: `qwen/qwen3.5-35b-a3b`
- Observer: `openai/gpt-oss-120b`

| Question | Time | Atomic items | Whole question |
|---|---:|---:|---:|
| Q1 active headcount | 37.600s | 10/10 | pass |
| Q4 review coverage | 73.751s | 7/7 | pass |

Q1 emitted the correct total of 25 and all eight canonical department counts.

Q4 logged:

```text
[EVIDENCE CONTRACT] decision=query_more
reason=coverage numerator requires distinct entity grain
```

The Agent recovered, obtained evidence at distinct employee grain, and emitted
25 active employees, 7 reviewed employees, 28% coverage, and failure against
the 80% threshold.

The Python-only grader was replayed 20 times. Every replay produced:

`1e596467990fa4f547baeeba994f76b0a262af47b13143cfc94c47b325850922`

## Interpretation

This closes the two targeted failure modes. It does not yet prove live
stability across repeated runs or superiority on all ten questions. A repeated
full paired run remains required before the active goal can be completed.
