# Lab 6 Phase 2B Progress Report

วันที่: 2026-07-29  
Branch: `codex/evidence-phase2b`  
Base: Phase 2A commit `ff68de3`

## Implemented

- `ClaimLedger` with `required | proved | contradicted`
- schema-grounded revision of claim grain and required fields
- `EvidenceFact(subject, predicate, value, unit, grain, evidence_id, derivation)`
- post-tool `DynamicObservation`
- `accept | query_more | replan | stop`
- unknown claim IDs from LLM are rejected by Python
- structured facts and ledger are passed to Final Semantic Observer
- coverage/rate grain-alignment rule
- MCP hard budget: 12 agent tool calls
- Dynamic Observer budget: 6 LLM calls
- Dynamic Observer timeout: 45 seconds, client retries disabled
- Final Observer timeout: 60 seconds, client retries disabled
- MCP transient retry: timeout/transport/429/5xx only

## Automated verification

19 unit tests pass, including:

- claim proof/contradiction transitions
- claim field revision after schema
- filtering invented claim IDs
- specific `query_more` evidence request
- structured evidence serialization
- retry on HTTP 503
- no retry on HTTP 400

## Live observations

### Q4 — Review coverage grain

Initial Phase 2B run exposed an invalid ledger:

```text
numerator grain = record
denominator grain = entity
```

After adding grain alignment, Claim Planner generated:

```text
denominator = total eligible employees
numerator = COUNT(DISTINCT employee_id) with review in 2023
coverage = numerator / denominator
```

Dynamic Observer requested the missing distinct numerator rather than accepting
7 review records as 7 employees. A completed run then used 25 employees and 7
distinct reviewed employees and returned 28%.

The run also exposed a second semantic distinction:

- threshold shortfall: `80 - 28 = 52 percentage points`
- uncovered share: `100 - 28 = 72%`

This distinction is now part of the Final Observer policy.

### Runtime failures found and addressed

1. One Dynamic Observer call hung for more than four minutes because OpenAI
   client retries extended the request-level timeout.
2. Reviewer clients now use `max_retries=0`; timeout is bounded per call.
3. MCP returned HTTP 503 during another run.
4. MCP dispatch now retries only transient failures with bounded backoff.

## Not yet proven

Phase 2B has not yet passed the full 10-question × 3-run benchmark. In
particular:

- claim revision after schema needs live regression coverage
- Q6 certification semantics needs rerun with structured facts
- Q9 efficiency refusal needs rerun with Dynamic Observation enabled
- latency may remain too high even with six-observation budget
- LLM-extracted facts still need deterministic numeric/unit validation

Therefore Phase 2B remains experimental and should not be merged into `main`.
