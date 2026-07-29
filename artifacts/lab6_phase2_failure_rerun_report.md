# Lab 6 Phase 2 Failure-Case Rerun

Date: 2026-07-29

Commit under test: `9b9d25a`

Model: `qwen/qwen3.5-35b-a3b`

Scope: Q2, Q5, Q6, Q8, Q9, and Q10; one new run per variant.

Raw output: [`lab6_phase2a_phase2b_failure_rerun.json`](lab6_phase2a_phase2b_failure_rerun.json)

## Why this rerun exists

The first 10-question run was a single sample. This rerun keeps the code,
questions, model, and MCP endpoint unchanged and repeats only the six failed
questions. Its purpose is to distinguish recurring architectural failures from
one-run model or provider variance.

## Runtime result

| Question | Phase 2A | Phase 2B |
|---|---:|---:|
| Q2 employment mix | completed, 46.8 s | completed, 129.1 s |
| Q5 training portfolio | completed, 22.3 s | **timeout, 360.0 s** |
| Q6 certificate semantics | completed, 53.4 s | completed, 93.1 s |
| Q8 project concentration | completed, 32.5 s | completed, 118.6 s |
| Q9 efficiency trap | completed, 54.1 s | completed, 138.3 s |
| Q10 staffing decision | **timeout, 360.0 s** | completed, 127.6 s |

Completion was 5/6 for both variants, but the timeout moved from Phase 2B Q9
and Q10 in the first run to Phase 2B Q5 and Phase 2A Q10 in the rerun. This
confirms substantial run-to-run variance.

## Strict semantic grading

| Question | Phase 2A | Phase 2B | Rerun finding |
|---|---|---|---|
| Q2 | Pass | Fail | Phase 2A now returned the exact aggregation. Phase 2B again exhausted aggregation attempts and returned no business answer. |
| Q5 | Pass | Fail | Phase 2A repeated the correct 252-hour result. Phase 2B timed out. |
| Q6 | Fail | Fail | Phase 2B gave a better refusal but still did not perform the required current-date expiry check; Phase 2A ended in a rewrite failure. |
| Q8 | Pass | Fail | Phase 2A again preserved the unknown unit. Phase 2B again invented `บาท`. |
| Q9 | Fail | Fail | Both found the right refusal concept but failed their second rewrite because an unsupported currency unit remained. |
| Q10 | Fail | Pass | Phase 2A timed out. Phase 2B completed with an evidence-insufficiency refusal. |

Strict rerun score over the six selected failures:

- **Phase 2A: 3/6**
- **Phase 2B: 1/6**

## Cross-run diagnosis

### Recurring regressions

1. **Q5 Phase 2B:** failed in both runs (rewrite dead-end, then timeout).
2. **Q8 Phase 2B:** invented `บาท` in both runs despite the unit rule.
3. **Q9 both variants:** a rewrite can identify the unsupported unit but still
   fail to remove it in the next candidate.
4. **Q6 both variants:** the agent recognizes the semantic distinction but
   does not reliably obtain the decisive expiry-date evidence.

### Non-deterministic failures

1. **Q2 Phase 2A:** failed the first aggregation and passed the rerun.
2. **Q9 Phase 2B:** timed out first, completed the rerun.
3. **Q10 Phase 2B:** timed out first, produced the correct refusal in the
   rerun.
4. **Q10 Phase 2A:** completed first, timed out in the rerun.

## Conclusion

The rerun strengthens the earlier conclusion: Phase 2B is not yet more
deterministic than Phase 2A. Its intended semantic policy is often correct,
but execution is not bounded and the LLM rewrite path does not reliably apply
its own verdict.

The next implementation should target the repeated mechanisms, not add HR
special cases:

1. deterministic label/unit sanitizer after a rewrite verdict;
2. one bounded rewrite with no MCP access;
3. whole-run deadline and per-phase call budget;
4. structured missing-evidence request for date validity and entity grain;
5. explicit refusal output when evidence remains insufficient.

After those changes, rerun these same six questions before returning to the
full 10-question × 3-run stability benchmark.
