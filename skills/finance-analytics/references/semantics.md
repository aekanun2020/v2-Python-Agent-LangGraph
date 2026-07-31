# Lending semantics

## Tables

- `loans_fact`: one stored loan row; no unique row identifier is exposed.
- `application_type_dim`: canonical application-type labels.
- `loan_status_dim`: canonical post-origination status labels.
- `issue_d_dim`: issue month/year.
- `home_ownership_dim`: canonical home-ownership labels.
- `emp_length_dim`: canonical employment-length labels.

## Fields

| Field | Meaning | Prohibition |
|---|---|---|
| `loan_amnt` | Requested loan amount recorded for a funded-loan row | Not an application population |
| `funded_amnt` | Amount funded for a stored loan row | Not approval/rejection |
| `int_rate` | Rate stored as a fraction | Multiply by 100 before adding `%` |
| `dti` | Recorded debt-to-income value | Do not infer causal risk |
| `annual_inc` | Recorded annual income | Currency is not declared |
| `loan_status` | Post-origination outcome/status | Never relabel as approval |

## Decision boundary

The schema lacks rejected applications and an approval-decision field.
Consequently it cannot establish:

- approval rate;
- probability of approval;
- why an application was approved or rejected;
- an individual lending decision.

It can support descriptive funded-loan portfolio metrics and observed
post-origination status comparisons.

## Deterministic bucketing

Do not use `NTILE` over a non-unique ordering key when downstream values are
graded exactly. Tied rows can move across boundaries. Prefer fixed,
left-inclusive bands declared in the answer contract.
