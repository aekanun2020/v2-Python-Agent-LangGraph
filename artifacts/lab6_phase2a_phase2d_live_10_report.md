# Phase 2A vs Phase 2D — Paired Live 10-Question Run

Date: 2026-07-30

## Configuration

- Agent model: `qwen/qwen3.5-35b-a3b`
- Semantic Observer: `openai/gpt-oss-120b`
- Data: live MSSQL through the configured ngrok MCP endpoint
- Questions: the versioned Q1–Q10 HR suite
- Order: paired by question, Phase 2A then Phase 2D
- Per-run whole-agent deadline: 150 seconds

This is a system-level comparison. Phase 2A and Phase 2D differ in more than
the final claim gate, so it is not a clean causal estimate of the gate alone.

## Operational result

| Metric | Phase 2A final-only | Phase 2D Python-first gate |
|---|---:|---:|
| Runs with detected answer marker | 9/10 | 10/10 |
| Mean latency | 78.213s | 74.467s |
| Median latency | 81.403s | 70.616s |
| MCP tool calls | 72 | 75 |
| Python observations | 0 | 75 |
| Dynamic LLM observations | 0 | 14 |
| Final-review verdicts | 19 | 9 |

The Phase 2D Q10 answer marker contained a deadline-stop message rather than a
completed substantive answer. It must not be counted as task success.

## Strict per-question review

| Q | Phase 2A | Phase 2D | Key observation |
|---|---|---|---|
| Q1 | pass | **fail** | Phase 2D emitted 0 active employees; ground truth is 25 |
| Q2 | fail | pass | Phase 2A emitted no answer; Phase 2D returned all eight exact mixes |
| Q3 | pass | pass | Both preserved the strict `> 50%` boundary |
| Q4 | fail | fail | Both used review-record count as employee coverage without proving distinct grain in the emitted claim |
| Q5 | pass | pass | Both returned 252 hours and external 60.32% over the 50% limit |
| Q6 | fail | pass | Phase 2D avoided claiming training certificates prove current-valid certifications |
| Q7 | pass | pass | Both preserved skill-record grain and category rates |
| Q8 | fail | pass | Phase 2A invented `HIGH_RISK`; Phase 2D used the declared concentration policy |
| Q9 | fail | fail | Phase 2A invented currency; Phase 2D omitted the supported literal per-head arithmetic |
| Q10 | pass | **fail** | Phase 2A refused the decision; Phase 2D hit the 150-second deadline |

Provisional strict score:

- Phase 2A: **5/10**
- Phase 2D: **6/10**

This manual strict score is included for incident analysis, not statistical
inference. The atomic deterministic grader currently covers only Q1/Q4/Q10;
the remaining rubric still needs independent versioned annotations.

## Main finding

The aggregate score hides a serious regression. Phase 2D's allowlist prevents
unsupported prose from re-entering the answer, but it cannot protect against a
wrong claim that the Observer marks supported because the upstream tool/query
path produced or selected bad evidence. Q1 demonstrates this directly:
verify-then-emit was internally consistent yet emitted the wrong real-world
answer.

This separates two correctness layers:

```text
evidence acquisition correctness
→ claim verification correctness
→ answer composition correctness
```

Phase 2D improved the third layer and parts of the second. It did not solve the
first layer.

## Decision

Do not merge Phase 2D as a proven replacement.

The next work should not add more final-Observer prompting. It should:

1. add versioned metric/grain contracts for the ten questions;
2. verify accepted evidence against those contracts before claim admission;
3. distinguish deadline-stop markers from successful answers in the harness;
4. complete an independently annotated atomic rubric for all ten questions;
5. replay frozen evidence/drafts before another live run.

Raw output: `artifacts/lab6_phase2a_phase2d_live_10.json`.
