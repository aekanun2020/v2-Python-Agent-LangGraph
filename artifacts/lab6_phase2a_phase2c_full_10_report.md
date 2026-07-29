# Lab 6 Phase 2A vs Phase 2C — Full 10-Question Run

Date: 2026-07-29

Commit: `225c52e`

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

Raw output:
[`lab6_phase2a_phase2c_full_10.json`](lab6_phase2a_phase2c_full_10.json)

## Runtime

| Metric | Phase 2A | Phase 2C |
|---|---:|---:|
| Runs | 10 | 10 |
| Extracted non-empty answers | 10/10 | 9/10 |
| Timeout | 0 | 0 |
| Mean elapsed | 37.1 s | 43.2 s |
| Median elapsed | 33.1 s | 38.5 s |
| Python observations | 0 | 64 |
| Tool-result LLM observations | 0 | 17 |

Phase 2C is approximately 16% slower on mean elapsed time in this run, but it
is far faster and more available than the rejected Phase 2B design.

## Strict grounded grading

| Question | Phase 2A | Phase 2C | Main finding |
|---|---|---|---|
| Q1 active headcount | Pass | Pass | Both returned the correct 25-person breakdown. |
| Q2 employment mix | Pass | Fail | Phase 2C exhausted the tool budget and emitted an empty answer. |
| Q3 strict contract policy | Fail | Fail | Both contradicted the actual 75% HR result; Phase 2C displayed 75% but concluded that no department exceeded 50%. |
| Q4 review coverage | Fail | Pass | Phase 2C obtained distinct employee grain and correctly separated 52 percentage points from the 72% uncovered share. |
| Q5 training concentration | Pass | Pass | Both returned the correct 252-hour distribution and 60.32% external concentration. |
| Q6 certificate semantics | Fail | Fail | Phase 2C improved the date analysis but overclaimed that no employee has a valid certification while NULL expiry remains semantically unknown, and added unsupported process-quality language. |
| Q7 expert skill records | Fail | Pass | Phase 2C returned the correct record-grain totals: 6/15 = 40%, with correct category rates. |
| Q8 project concentration | Fail | Fail | Phase 2C returned 64.29% correctly but added an unrequested investment recommendation; Phase 2A invented a `High Risk` severity. |
| Q9 efficiency trap | Pass | Pass | Both refused to relabel project-value/head as efficiency. |
| Q10 staffing decision | Fail | Fail | Both refused the decision, but Phase 2C corrupted the canonical department label to `เทคโนโลยีสถานที่`; Phase 2A reported an incorrect duplicated headcount. |

Strict grounded score:

- **Phase 2A: 4/10**
- **Phase 2C: 5/10**

## Interpretation

Phase 2C restores task completion and produces a small strict-correctness gain
over Phase 2A. It also fixes two important semantic cases:

- distinct-employee review coverage;
- record-grain expert-skill analysis.

It has not yet met the merge threshold:

1. simple query recovery can still exhaust the tool budget (Q2);
2. the final observer can preserve a contradiction between a table and its
   conclusion (Q3);
3. NULL validity semantics remain unsafe (Q6);
4. unrequested recommendations can survive a rewrite (Q8);
5. canonical labels can still be changed (Q10).

## Decision

Keep Phase 2C experimental. It is directionally better than Phase 2B and
slightly better than Phase 2A, but one 5/10 run is not sufficient evidence for
merge.

The next work should remain generic:

1. stop retrying after accepted non-empty evidence already satisfies the
   requested fields;
2. compare final conclusion operators against displayed numeric facts;
3. treat NULL as unknown unless metadata defines its meaning;
4. remove prescriptive sentences when the user did not request them;
5. validate canonical labels against accepted evidence before returning.

After these invariants are implemented, repeat the same 10 questions once
before considering a three-run stability benchmark.
