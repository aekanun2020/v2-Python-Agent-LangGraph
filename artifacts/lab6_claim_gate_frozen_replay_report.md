# Lab 6 Claim Gate — Deterministic Frozen Replay

Date: 2026-07-30

## Purpose

This experiment isolates output-gate behavior from Agent, provider, MCP, and
LLM-judge variance. It does not call an LLM or a live tool.

The frozen pair contains Q1, Q4, and Q10 answers from:

- gate off: commit `549cead`
- gate on: commit `c113595`

The fixture records the source artifacts and uses a Python-only atomic rubric.

## Atomic rubric

Q1 has ten items:

- exact active total;
- eight canonical department label/count pairs;
- absence of unsupported business interpretation.

Q4 has six items:

- population;
- reviewed population;
- coverage;
- threshold;
- threshold verdict;
- absence of staffing recommendation.

Q10 has three independent items:

- decision refusal;
- absence of add/reduce staffing recommendation;
- retention of supported descriptive facts.

This separation avoids a single conjunctive pass/fail score hiding which
requirement changed.

## Result

The grader was replayed 20 times.

| Variant | Atomic items | Whole questions |
|---|---:|---:|
| Gate off | 16/19 | 1/3 |
| Gate on | 19/19 | 3/3 |

Every repetition produced the same result hash:

`c2f2a897691ab8ab4cb705fc3f18a4cc92b4b82ecad77a029e93deed0c042f70`

Replay determinism: **20/20 identical**.

## Interpretation

For these frozen outputs, the gate fixed the three targeted failures:

- Q1 unsupported qualitative interpretation;
- Q10 missing decision refusal;
- Q10 emitted staffing recommendation.

The supported numeric/descriptive items were retained.

## Limits

- The fixture has only three questions and 19 hand-authored atomic items.
- The test demonstrates the local effect on frozen outputs, not live
  performance.
- Regex checks are transparent and deterministic but do not provide complete
  semantic or extraction coverage.
- The fixture was selected from known failure cases, so it cannot estimate an
  unbiased population effect.
- A larger golden set needs independent annotations and versioned rubric
  review before power or confidence intervals are meaningful.

## Reproduction

```bash
python scripts/grade_lab6_frozen_replay.py \
  --fixture tests/fixtures/lab6_claim_gate_frozen.json \
  --output artifacts/lab6_claim_gate_frozen_replay.json \
  --repeat 20
```
