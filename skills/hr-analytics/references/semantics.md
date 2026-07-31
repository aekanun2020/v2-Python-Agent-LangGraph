# HR semantics and decision boundaries

## Entity and record grains

| Table | Grain | Important constraint |
|---|---|---|
| `employees` | One employee | `status` and `department` are canonical values |
| `performance_reviews` | One review record | Coverage requires distinct employees |
| `training_records` | One training record | A record is not a trained-employee count |
| `certifications` | One certification record | Validity depends on certification evidence |
| `skills` | One skill record | A skill record is not a distinct employee |
| `projects` | One employee-project record | Project value is not productivity |
| `position_history` | One position-history record | `is_current` controls current position records |

## Required interpretations

- Active employee population uses the exact evidenced status
  `N'ปฏิบัติงาน'`.
- Performance-review employee coverage uses
  `COUNT(DISTINCT employee_id)` over the declared `review_period`.
- `review_period` such as `2023` is not interchangeable with `review_date`.
- `certificate_obtained` belongs to a training record. It does not prove that
  every employee has a certification that remains valid.
- Missing skill, training, review, project, or certification rows do not prove
  that an employee lacks the underlying capability or activity.
- Project value divided by active headcount may be reported only as literal
  `project_value per active employee`.

## Decision boundary

Headcount, training, skill, review, and project aggregates can support
descriptive reporting. Staffing decisions require workload, capacity, demand
forecast, service-level, target-cost, and other policy evidence. When those
inputs are absent, refuse the decision while retaining supported facts.

Grouped association does not establish causality or individual employee
performance.
