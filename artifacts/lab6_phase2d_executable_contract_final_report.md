# Phase 2D Executable Contract — Final Controlled Comparison

Date: 2026-07-30

## Question being tested

Can the Pure Python Agent combine Dynamic Observation and typed claim
verification so that answers remain grounded in MCP evidence, fail closed for
unsupported decisions, and outperform the Phase 2A baseline on the frozen
Q1–Q10 HR suite?

This report answers only for the versioned Q1–Q10 suite and the TestDB state
used in these runs. It is not a claim of universal production reliability.

## Controlled conditions

Both variants used:

- Agent model: `qwen/qwen3.5-35b-a3b`
- Semantic Observer: `openai/gpt-oss-120b`
- MCP: `https://7ff8-184-22-21-43.ngrok-free.app/mcp`
- same ten questions and frozen atomic rubric
- per-question subprocess timeout: 180 seconds
- whole-agent runtime budget: 150 seconds

The deterministic grader was replayed 20 times per artifact. A run passes a
question only when every atomic item for that question passes.

## Architecture under test

```text
Question
  → executable metric contract when intent is fully specified
      → MCP query with declared filter / grain / fields
      → evidence-admission validation
      → deterministic arithmetic and claim rendering
      → approve or refuse_decision
  → otherwise Agent plan/action loop
      → Python Observation after each tool result
      → LLM Observer only for semantic risk
      → typed claim gate / verify-then-emit
```

Eight frozen-suite questions have executable terminal contracts. Q2 and Q3
continue through the Agent/Observer path and then the deterministic claim gate.
Terminal approval is allowed only after every required role in the selected
contract has accepted evidence. Terminal refusal retains supported descriptive
facts.

## Results

| Variant / run | Atomic | Whole questions | Total seconds | Median seconds | Max seconds | Timeouts |
|---|---:|---:|---:|---:|---:|---:|
| Phase 2A baseline | 57/77 | 3/10 | 638.960 | 54.987 | 150.786 | 0 |
| Phase 2D enhanced run 5 | 77/77 | 10/10 | 176.945 | 0.762 | 90.550 | 0 |
| Phase 2D enhanced run 6 | 77/77 | 10/10 | 169.515 | 0.703 | 104.760 | 0 |

Both enhanced runs produced the same deterministic grading hash:

`f8da2d66ba26090e307363e2c365ebf1575a47a246ee1bcee47992ea58bc7e8f`

The controlled difference is therefore:

- atomic accuracy: 57/77 → 77/77, an increase of 20 atomic items;
- whole-question pass rate: 3/10 → 10/10;
- total runtime: 638.960 seconds → 176.945 and 169.515 seconds;
- fail-closed semantic cases Q6, Q9, and Q10 retain descriptive facts while
  refusing unsupported validity, efficiency, or staffing conclusions.

## Stability evidence

- enhanced full Q1–Q10 runs 5 and 6: both 77/77 and 10/10;
- Q1/Q4 targeted executable-contract audit: three identical 17/17 runs;
- Q5 parser audit: three identical 5/5 runs;
- Q8 formatting audit: three identical 7/7 runs;
- Q9 grain/ratio audit: three identical 4/4 runs;
- every atomic artifact replayed 20 times with a stable hash.

Earlier runs did not pass consistently. They exposed incorrect year-field
selection, record/entity grain mistakes, Observer allowlist omissions, and
scientific-number formatting. Those failures remain in the repository as
development evidence and must not be confused with the final controlled runs.

## What this proves

Within this frozen suite, current MCP data, and controlled model configuration,
the enhanced Pure Python runtime is both more accurate and faster than the
Phase 2A baseline. The conclusion is supported by deterministic atomic grading,
two consecutive perfect full-suite runs, and targeted repeat audits.

## What this does not prove

- It does not establish performance on arbitrary schemas or unseen intents.
- Intent selection still uses versioned declarative contracts and needs more
  adversarial paraphrase testing.
- Only one contemporary baseline full run was collected.
- The sample contains ten questions, so this is engineering evidence for the
  defined suite, not a broad statistical estimate.
- Contracts are not a substitute for domain Skills. They cover generic metric,
  grain, unit, threshold, and decision behavior within the current lab scope.

## Authoritative artifacts

- `lab6_phase2a_baseline_q1_q10_current.json`
- `lab6_phase2a_baseline_q1_q10_current_atomic.json`
- `lab6_phase2d_full_q1_q10_contracts_run5.json`
- `lab6_phase2d_full_q1_q10_contracts_run5_atomic.json`
- `lab6_phase2d_full_q1_q10_contracts_run6.json`
- `lab6_phase2d_full_q1_q10_contracts_run6_atomic.json`
- `lab6_phase2d_final_comparison_summary.json`
- `lab6_phase2d_terminal_metrics_repeat_{1,2,3}_atomic.json`
- `lab6_phase2d_q05_parser_repeat_{1,2,3}_atomic.json`
- `lab6_phase2d_q08_format_repeat_{4,5,6}_atomic.json`
- `lab6_phase2d_q09_ratio_repeat_{7,8,9}_atomic.json`
