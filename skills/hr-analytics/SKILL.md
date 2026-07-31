---
name: hr-analytics
description: Ground HR and workforce analytics in MSSQL MCP evidence using explicit metric, entity-grain, label, and decision contracts. Use for active headcount, department composition, performance-review coverage, training hours, certifications, skill proficiency, project concentration, project-value-per-head arithmetic, staffing questions, and requests that could incorrectly turn missing HR records or descriptive proxies into employee or workforce decisions.
---

# HR Analytics

Use executable evidence contracts before narrative interpretation.

## Workflow

1. Read [semantics.md](references/semantics.md) before interpreting HR fields.
2. Match the request to
   [answer_contracts.json](references/answer_contracts.json).
3. Execute only the declared read-only MCP query roles.
4. Validate entity grain, filters, required fields, and canonical labels.
5. Emit all supported descriptive facts.
6. Apply declared arithmetic or thresholds without semantic relabelling.
7. Refuse staffing, causal, capability, or certification-validity conclusions
   when the necessary evidence is absent.

## Invariants

- Preserve exact department, status, category, and proficiency labels.
- Distinguish employee grain from training, review, skill, project, and
  certification record grain.
- Use `COUNT(DISTINCT employee_id)` for employee coverage.
- Treat `review_period` and `review_date` as different fields.
- Do not infer absence from a missing related record.
- Do not treat `certificate_obtained` as proof of a currently valid
  certification.
- Do not relabel project value per employee as productivity or efficiency.
- Do not recommend adding or reducing staff from headcount and project value
  alone.

The generic runtime owns discovery, MCP execution, completeness validation,
and fail-closed output. This Skill owns HR meanings and contracts.

## Runtime Boundary

- The generic runtime discovers this Skill through
  `skills/*/references/answer_contracts.json`.
- A matched contract executes its declared MCP query and deterministic output
  path without Agent or Observer LLM calls.
- An unmatched HR question remains on the general agent path; this Skill does
  not claim universal HR coverage.
- Domain contracts must stay in this Skill and must not be copied into
  `labs/lab6_todo/executable_metric_contracts.json`.

The frozen HR Q1–Q10 suite passed `77/77` atomic checks in two repeated runs
with identical answer hashes. This validates the declared contracts only.
See `artifacts/hr_skill_run4_run5_report.md`.
