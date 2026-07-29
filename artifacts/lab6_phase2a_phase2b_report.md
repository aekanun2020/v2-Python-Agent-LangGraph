# Lab 6 Phase 2A vs Phase 2B — First 10-Question Live Run

Date: 2026-07-29

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

Runs: one run per question and variant (20 live runs)

## Compared variants

- **Phase 2A:** Final Semantic Observer on, Dynamic Observation off
- **Phase 2B:** Final Semantic Observer on, Dynamic Observation on

The raw prompts, outputs, verdicts, timings, and errors are stored in
[`lab6_phase2a_phase2b_runs.json`](lab6_phase2a_phase2b_runs.json).

## Runtime result

| Metric | Phase 2A | Phase 2B |
|---|---:|---:|
| Completed with an answer | 10/10 | 8/10 |
| Hard timeout (360 seconds) | 0 | 2 |
| Total elapsed time | 462.3 s | 1,686.1 s |
| Mean per question | 46.2 s | 168.6 s |
| Median per question | 48.4 s | 128.4 s |

## Strict manual semantic grading

Passing requires the final answer to agree with ground truth, preserve evidence
labels and units, use the correct grain, and take the expected decision route.
An error message or reviewer rejection is not counted as a correct business
answer.

| Question | Phase 2A | Phase 2B | Main finding |
|---|---|---|---|
| Q1 active headcount | Pass | Pass | Both returned the exact 25-person, 8-department result. |
| Q2 employment mix | Fail | Fail | Both exhausted queries without returning the known aggregation. |
| Q3 strict `> 50%` policy | Pass | Pass | Both correctly included only `ทรัพยากรบุคคล`; 50% did not pass. |
| Q4 review coverage | Pass | Pass | Both used 7 distinct employees / 25 = 28% and failed the 80% threshold. |
| Q5 training-hour concentration | Pass | Fail | Phase 2B found the values but its rewrite loop rejected canonical labels and ended without a usable answer. |
| Q6 certificate semantics | Fail | Fail | Both rejected the universal certification claim, but neither completed the required current-date validity result (`expiry_date >= current date` gives zero stored valid records). |
| Q7 expert skill records | Fail | Pass | Phase 2A returned 0% incorrectly; Phase 2B returned 6/15 = 40% and correct category record rates. |
| Q8 top-two project concentration | Pass | Fail | Phase 2B invented the currency label `บาท`; Phase 2A preserved the unknown unit. |
| Q9 efficiency trap | Fail | Fail | Phase 2A relabelled project-value/head as efficiency; Phase 2B timed out. |
| Q10 staffing decision | Fail | Fail | Phase 2A did not produce a clean evidence-insufficiency refusal; Phase 2B timed out. |

**Strict grounded score: Phase 2A = 5/10, Phase 2B = 4/10.**

## What Phase 2B demonstrated

Phase 2B is not generally better yet. It showed one material correctness gain:
Q7 recovered the correct expert-record counts and percentages where Phase 2A
returned zero. It also maintained the correct distinct-employee grain for Q4.

However, the same mechanism introduced or failed to prevent material
regressions:

1. Q5 had correct evidence but failed to finish a label-only rewrite.
2. Q8 passed an invented currency through the Final Observer.
3. Q9 and Q10 did not terminate within six minutes.
4. Q2 still could not recover from an aggregation/query failure.
5. Q6 stopped short of the decisive expiry-date calculation.

## Decision

Do **not** merge Phase 2B into `main` based on this run. The experiment does
not prove improved determinism. It currently lowers strict grounded accuracy
from 5/10 to 4/10 and completion from 10/10 to 8/10.

The next change should be narrow and evidence-driven:

1. Add a deterministic termination budget covering the whole observer path,
   not only individual LLM calls.
2. Make label/unit-only violations a bounded rewrite that cannot call MCP.
3. Require a concrete missing-evidence request for `query_more`, including
   grain and fields.
4. Separate calculated ratios from semantic labels such as “efficiency”.
5. Re-run only Q2, Q5, Q6, Q8, Q9, and Q10 during development; after they pass,
   repeat the full 10-question suite three times.

This remains within the original TAO goal: improve the **Observation after a
tool call**, without introducing domain-specific HR policy as the core
mechanism.
