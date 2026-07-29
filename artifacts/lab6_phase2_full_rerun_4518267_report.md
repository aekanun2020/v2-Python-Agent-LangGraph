# Lab 6 Full 10-Question Rerun — Commit 4518267

Date: 2026-07-29

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

Configuration:

- 10 HR questions
- Phase 2A and Phase 2B
- 20 live runs
- 180-second internal hard deadline per run
- 210-second outer process timeout

Raw output:
[`lab6_phase2_full_rerun_4518267.json`](lab6_phase2_full_rerun_4518267.json)

## Runtime results

| Metric | Phase 2A | Phase 2B |
|---|---:|---:|
| Runs with extracted answer text | 9/10 | 10/10 |
| Outer process timeouts | 0 | 0 |
| Runs at approximately 180-second deadline | 1/10 | 7/10 |
| Mean elapsed time | 63.9 s | 167.2 s |
| Median elapsed time | 52.6 s | 180.8 s |

“Extracted answer text” includes safe-stop and error messages; it is not a
correctness score.

## Strict grounded grading

| Question | Phase 2A | Phase 2B | Finding |
|---|---|---|---|
| Q1 active headcount | Pass | Fail | Phase 2A returned 25 and exact department counts. Phase 2B hit the hard deadline. |
| Q2 employment mix | Fail | Fail | Phase 2A could not verify the aggregation. Phase 2B ended with provider error. |
| Q3 strict contract policy | Fail | Fail | Phase 2A did not obtain department aggregation. Phase 2B hit the deadline. |
| Q4 review coverage | Pass | Fail | Phase 2A returned 7/25 = 28%. Phase 2B hit the deadline. |
| Q5 training concentration | Pass | Fail | Phase 2A returned the correct hour shares. Phase 2B rejected its result due to an unresolved claim. |
| Q6 certificate semantics | Fail | Fail | Both ended without a consistent, grounded validity answer. |
| Q7 expert skill | Fail | Fail | Phase 2A produced no answer; Phase 2B rejected unresolved claims. |
| Q8 project concentration | Pass | Fail | Phase 2A returned 18/28 = 64.29%. Phase 2B failed during bounded recheck. |
| Q9 efficiency trap | Fail | Fail | Neither produced a clean grounded refusal. |
| Q10 staffing decision | Pass | Fail | Phase 2A refused the decision while reporting descriptive evidence. Phase 2B failed during bounded recheck. |

Strict grounded score:

- **Phase 2A: 5/10**
- **Phase 2B: 0/10**

## What was proven

The hard deadline works: no run was killed by the outer subprocess timeout.
Phase 2B now fails safely rather than returning unsupported claims.

However, Phase 2B is operationally worse:

1. Claim Planner is a mandatory provider call before useful work starts.
2. Dynamic Observer calls consume most of the deadline.
3. Strict single-observation grain/field coverage leaves valid cumulative
   evidence unresolved.
4. Final post-rewrite verification adds another provider failure point.
5. Safe failure messages are frequent enough that task completion is
   effectively zero on this suite.

## Decision

Do not merge Phase 2B into `main`, and do not proceed to 10 questions × 3
runs. One complete run is sufficient to reject this architecture revision.

The next revision must change the critical path rather than add more prompts:

1. optional/cached Claim Planner with a deterministic fallback;
2. cumulative claim coverage over the complete EvidenceState;
3. deterministic final number/label/unit validation without an LLM recheck;
4. finalization time reserved before the action deadline;
5. fewer observer calls selected by risk instead of one per tool result.
