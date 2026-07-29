# Lab 6 Phase 2C Stability Report — Two Full Runs

Date: 2026-07-29

Model: `qwen/qwen3.5-35b-a3b`

MCP: live MSSQL through the configured ngrok endpoint

Raw runs:

- [`lab6_phase2a_phase2c_full_10.json`](lab6_phase2a_phase2c_full_10.json)
- [`lab6_phase2a_phase2c_full_10_rerun2.json`](lab6_phase2a_phase2c_full_10_rerun2.json)

## Runtime stability

| Metric | Phase 2A run 1 | Phase 2A run 2 | Phase 2C run 1 | Phase 2C run 2 |
|---|---:|---:|---:|---:|
| Non-empty answers | 10/10 | 9/10 | 9/10 | 10/10 |
| Timeout | 0 | 0 | 0 | 0 |
| Mean elapsed | 37.1 s | 56.6 s | 43.2 s | 50.7 s |
| Median elapsed | 33.1 s | 47.0 s | 38.5 s | 47.5 s |
| Tool-result LLM observations | 0 | 0 | 17 | 18 |

The Phase 2C routing volume is reasonably stable, but latency and completion
still vary with provider and agent trajectory.

## Phase 2C strict result by question

| Question | Run 1 | Run 2 | Stability finding |
|---|---|---|---|
| Q1 active headcount | Pass | Pass | Stable pass |
| Q2 employment mix | Fail | Pass | Tool-budget failure disappeared |
| Q3 strict contract policy | Fail | Pass | Contradictory conclusion disappeared |
| Q4 review coverage | Pass | Fail | Run 2 corrupted canonical status label and weakened percentage-point wording |
| Q5 training concentration | Pass | Fail | Run 2 normalized canonical labels (`ภายนอก` → `อบรมภายนอก`) |
| Q6 certificate semantics | Fail | Fail | Stable failure; NULL/current-validity semantics remain unsafe |
| Q7 expert skill records | Pass | Fail | Run 2 returned 0% instead of the correct 40% |
| Q8 project concentration | Fail | Pass | Unrequested recommendation disappeared |
| Q9 efficiency trap | Pass | Fail | Run 2 reported the ratio comparison without clearly refusing the efficiency inference |
| Q10 staffing decision | Fail | Pass | Canonical-label corruption disappeared and refusal was grounded |

Phase 2C strict score:

- Run 1: **5/10**
- Run 2: **5/10**

The equal total is misleading. Only Q1 passed in both runs, and Q6 failed in
both. Eight questions changed pass/fail status. Outcome agreement is therefore
only **2/10**, with stable success on just **1/10**.

## Phase 2A comparison

Phase 2A also varied:

- Run 1: **4/10**
- Run 2: approximately **5/10**
- Q1 failed to produce an answer in run 2 after passing run 1.
- Several semantic outcomes changed between runs.

Phase 2C has better bounded execution and a slightly higher aggregate score,
but this experiment does not prove greater semantic consistency.

## Conclusion

Phase 2C is **not deterministic enough**. Aggregate accuracy alone concealed
large per-question instability.

The next work should not be another prompt change. Stable correctness requires
Python invariants applied to every final answer:

1. exact canonical-label membership;
2. numeric and operator consistency between displayed facts and conclusion;
3. explicit NULL-as-unknown handling;
4. removal of unrequested prescriptive sentences;
5. deterministic grain declarations for record versus distinct entity;
6. stop after accepted evidence instead of allowing later contradictory
   queries to replace it.

Only after those invariants pass should the same 10-question suite be run
three times.
