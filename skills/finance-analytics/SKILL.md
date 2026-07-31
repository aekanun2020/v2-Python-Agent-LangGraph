---
name: finance-analytics
description: Ground finance and lending analytics in MSSQL MCP evidence using explicit metric, grain, unit, and semantic contracts. Use for portfolio totals, application or loan-status distributions, yearly cohorts, home-ownership or employment-length segments, DTI buckets, income bands, funding gaps, charged-off comparisons, and questions that might incorrectly equate funded loans or post-origination status with approval decisions.
---

# Finance Analytics

Use deterministic contracts before prose generation.

## Workflow

1. Read [semantics.md](references/semantics.md) before interpreting lending fields.
2. Match the request to
   [answer_contracts.json](references/answer_contracts.json).
3. Execute the declared read-only query against accepted MCP evidence.
4. Preserve every required output column and every returned canonical label.
5. Emit the evidence table before adding any interpretation.
6. Apply the contract's grounded notes and semantic prohibitions.
7. Refuse an approval, causal, or individual decision when its required field or
   population is absent.

## Invariants

- Treat `loan_amnt` as requested amount and `funded_amnt` as funded amount.
- Treat `loan_status` as post-origination status, not approval/rejection.
- Never call `SUM(funded_amnt) / SUM(loan_amnt)` an approval rate.
- Convert `int_rate` from fraction to percent only through explicit arithmetic.
- Do not invent a currency.
- Preserve exact category labels.
- Keep record, distinct entity, cohort, segment, and bucket grains separate.
- Report grouped associations descriptively; do not infer causality.
- Use fixed bucket boundaries when the fact table lacks a deterministic
  tie-breaker.

The runtime, not this prose, owns required-column completeness and fail-closed
emission.

## Runtime Boundary

- The generic runtime discovers this Skill through
  `skills/*/references/answer_contracts.json`.
- A matched contract executes its declared MCP query and deterministic output
  path without Agent or Observer LLM calls.
- An unmatched Finance question remains on the general agent path; this Skill
  does not claim universal lending or finance coverage.
- Domain contracts must stay in this Skill and must not be copied into
  `labs/lab6_todo/executable_metric_contracts.json`.

The frozen Finance Q1–Q10 suite passed `148/148` atomic checks in two repeated
runs with identical answer hashes. The full smoke remained unchanged after
the HR Skill was added. See `artifacts/finance_skill_run3_run4_report.md`.
