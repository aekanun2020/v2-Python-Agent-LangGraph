# Phase 2D Typed Claim Gate — Live Smoke

Date: 2026-07-30

## Architecture change

Phase 2D replaces `draft → LLM rewrite → emit` with:

```text
draft
→ final risk routing
→ LLM Observer atomic supported-claim allowlist
→ Python typed verification
→ compose only accepted claims
→ fail closed for unsupported decisions
```

The Context Engineering components remain the control plane. They do not
decide factual correctness.

## Configuration

- Agent: `qwen/qwen3.5-35b-a3b`
- Semantic Observer: `openai/gpt-oss-120b`
- Data: live MSSQL MCP through the configured ngrok endpoint
- Regression tests after implementation: 35 passed

## Live results

### Q1 — active headcount

The first smoke exposed an empty Agent draft. The final router originally
treated it as no-risk and emitted an empty answer. After adding the generic
`empty-answer` fail-closed route, the rerun completed in 60.040 seconds and
emitted only nine verified claims: the total of 25 and the eight exact
department counts. Unsupported investment, innovation, and staffing
interpretations were absent.

### Q4 — review coverage

Completed in 63.484 seconds. The gate emitted the supported population count
(25), distinct reviewed employees (7), coverage (28%), and the comparison with
the user-supplied 80% threshold. Unsupported business recommendations were not
emitted.

### Q10 — staffing decision

Completed in 121.057 seconds. Descriptive evidence was emitted, but the
recommendation itself was removed. The answer ended with:

> หลักฐานที่มีไม่เพียงพอสำหรับการตัดสินใจหรือคำแนะนำที่ร้องขอ

This is the intended fail-closed outcome because no workload, demand,
capacity, service-level, or policy contract was available to justify a staffing
decision.

## What this proves

- The Phase 2C rewrite failure seen in Q10 is prevented: an Observer rewrite is
  no longer emitted.
- Supported claims form an allowlist, so rejected claims cannot re-enter the
  answer through prose surrounding an exact-span replacement.
- Decision refusal is computed by Python from question intent and verdict.
- Transparent numeric arithmetic has deterministic post-conditions.

## What this does not prove

- Three smoke questions do not establish statistical superiority.
- The qualitative verifier remains model-based.
- Recommendation approval is deliberately unavailable until a generic,
  explicit policy/evidence contract is designed.
- Canonical categorical verification still relies on accepted evidence plus
  the Observer allowlist; it is not yet a complete ontology-aware verifier.

Raw runs:

- `artifacts/lab6_phase2c_claim_gate_smoke.json`
- `artifacts/lab6_phase2c_claim_gate_q1_rerun.json`
