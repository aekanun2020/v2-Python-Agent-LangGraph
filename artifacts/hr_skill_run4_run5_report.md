# HR Analytics Skill — isolation and consistency report

Date: 2026-07-31

## Change

- Moved all HR executable contracts from the Lab 6 runtime file into
  `skills/hr-analytics/references/answer_contracts.json`.
- Added HR semantics and decision boundaries to the Skill.
- Added Q2 employment-mix and Q3 strict contract-dependency contracts so the
  frozen HR Q1–Q10 suite is fully contract matched.
- Left the Finance Skill contracts unchanged.
- The generic runtime contract file now contains no domain contracts.

## Architecture

```text
Generic Lab 6 runtime
  -> discover skills/*/references/answer_contracts.json
       -> HR Analytics Skill
       -> Finance Analytics Skill
  -> MCP evidence
  -> contract completeness
  -> deterministic output
```

## HR live results

| Run | Questions | Atomic | Total | Median | Max |
|---|---:|---:|---:|---:|---:|
| HR Skill run 4 | 10/10 | 77/77 | 7.303s | 0.710s | 0.901s |
| HR Skill run 5 | 10/10 | 77/77 | 7.310s | 0.706s | 0.945s |

Both runs produced the same answer SHA-256:

`af20423f90d8b38b2469691032831cf67efa7f2da81868056ed391b015ed51f9`

Both atomic results produced the established HR grader hash:

`f8da2d66ba26090e307363e2c365ebf1575a47a246ee1bcee47992ea58bc7e8f`

For contract-matched HR Q1–Q10, no Agent or Observer LLM call is needed.

## Finance isolation proof

After the final HR changes, the full Finance Q1–Q10 smoke test produced:

- questions: 10/10;
- atomic checks: 148/148;
- grader hash:
  `be4fcb4e3350613525e97e3c0603e3bf33649d50896b50f22c0c02a129225c07`;
- answer hash:
  `16b98ff0164f142ee592a59b081d2fe7f99785a86ef320b593d49ea2bd49715c`.

The Finance answer hash is identical to the pre-HR-isolation Finance run 4.

## Regression

- HR and Finance Skill validation: passed.
- Unit/non-Lab8 regression: 76 passed.
- Generic runtime domain contracts: zero.
- HR contracts: 10.
- Finance contracts: 10.
- Contract IDs do not overlap.

## Limits

These results apply to the declared frozen HR and Finance suites. Questions
that do not match a Skill contract still use the general Agent path.
