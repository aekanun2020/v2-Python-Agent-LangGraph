# Phase 2B Architecture — Live Completion Report

Date: 2026-07-29

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

## Test sequence

Three live artifacts were produced:

1. [`lab6_phase2b_complete_failure_suite.json`](lab6_phase2b_complete_failure_suite.json)

   Six known failure questions, Phase 2A and Phase 2B, before the hard-deadline
   correction.
2. [`lab6_phase2b_hard_deadline_smoke.json`](lab6_phase2b_hard_deadline_smoke.json)

   Q2, Q8, and Q10 after hard deadline and post-rewrite verification.
3. [`lab6_phase2b_provenance_acceptance.json`](lab6_phase2b_provenance_acceptance.json)

   Phase 2B Q8 and Q10 after adding user-input provenance.

## First failure-suite result

| Metric | Phase 2A | Phase 2B |
|---|---:|---:|
| Completed with answer | 6/6 | 2/6 |
| Process timeout at 300 s | 0 | 4 |

Phase 2B timed out on Q2, Q5, Q6, and Q9. Q8 completed correctly without an
invented currency. Q10 completed but still made an unsupported staffing
recommendation. This disproved the first “architecture complete” claim.

## Corrections triggered by live evidence

1. Added an OS-level hard deadline around the complete run, including blocking
   provider and MCP calls.
2. Made benchmark subprocess output unbuffered so timeout diagnostics survive.
3. Added one bounded post-rewrite semantic check with no MCP access.
4. Made a failed post-rewrite check terminate fail-closed.
5. Added claim provenance: `user_input | tool | derived`.
6. User-supplied thresholds, operators, scopes, and policies can be proved by
   `user_question` rather than being incorrectly requested from MCP.
7. A semantically approved refusal can terminate despite unresolved factual
   claims, because insufficiency is itself the requested outcome.

## Focused smoke result

- Q2 Phase 2B terminated at the hard deadline instead of being killed by the
  outer process timeout.
- Q8 produced correct evidence, but an unresolved user-policy metadata claim
  caused a safe rejection. This exposed the missing provenance state.
- Q10 produced a safe evidence-insufficiency result after post-rewrite
  verification rather than allowing the earlier staffing recommendation.

## Provenance acceptance result

Both runs stayed within the hard deadline:

- Q8: Claim Planner received `APIConnectionError`; the run stopped safely at
  approximately 181 seconds without inventing an answer.
- Q10: Final Observer detected unsupported `ล้านบาท`; its bounded recheck
  received `APIConnectionError`, so the run failed closed.

## Verification

- Pure Python tests: **24 passed**
- Syntax compilation: passed
- Hard deadline unit test proves blocking work is interrupted
- No secret is stored in artifacts

## Final assessment

Phase 2B now has deterministic safety and termination properties that the
previous implementation lacked, but it is **not operationally complete**:

- provider failure can consume the entire run during Claim Planner;
- final recheck creates another provider dependency;
- completion is lower than Phase 2A;
- semantic correctness cannot compensate for poor availability.

Do not merge Phase 2B into `main`.

The architectural next step is not another HR rule. It is to remove mandatory
LLM calls from the critical path:

1. make Claim Planner optional and cacheable;
2. let schema/tool evidence create a minimal fallback ledger;
3. replace the LLM post-rewrite recheck with deterministic claim/label/unit
   verification over structured facts;
4. reserve an explicit fraction of the deadline for finalization;
5. then repeat the six-question suite.
