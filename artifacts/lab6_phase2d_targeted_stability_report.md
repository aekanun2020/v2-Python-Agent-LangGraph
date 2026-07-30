# Phase 2D Targeted Stability Audit

Date: 2026-07-30

Q1 and Q4 were repeated five times after evidence-admission contracts.

| Run | Atomic items | Whole questions |
|---|---:|---:|
| 1 | 13/17 | 1/2 |
| 2 | 17/17 | 2/2 |
| 3 | 6/17 | 0/2 |
| 4 | 15/17 | 1/2 |
| 5 | 14/17 | 1/2 |

The deterministic grader itself produced a stable hash on every 20-repeat
artifact replay, but live outcomes were not stable.

Observed failure classes:

- one Q1 final Observer response contained a literal JSON control character;
- some Q4 answers lost the distinct-employee qualifier;
- fail-closed filtering sometimes removed coverage and threshold claims,
  producing incomplete but safer answers;
- one Q4 answer reported shortfall as percent rather than percentage points.

Fixes added after the audit:

- tolerant JSON parsing for literal control characters;
- claim-set-level grain preservation;
- rejection of percent-form shortfall;
- Python coverage derivation from accepted total, distinct numerator, and
  user threshold.

A subsequent Q4 smoke passed 7/7 atomic items, but one run is not stability
evidence. Full Q1-Q10 testing was intentionally deferred.

Conclusion: the active goal remains unproven.
