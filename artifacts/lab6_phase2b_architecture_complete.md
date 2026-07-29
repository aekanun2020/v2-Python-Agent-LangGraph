# Lab 6 Phase 2B Architecture Completion

Date: 2026-07-29

Branch: `codex/evidence-phase2b`

## Scope

Phase 2B implements a generic post-tool Observation layer for the Pure Python
agent. It does not encode HR-specific answers or policies.

```text
Question
  -> Claim Ledger
  -> Agent Action
  -> MCP Tool Result
  -> Grounded Evidence Extractor
  -> Dynamic Observation
  -> accept | query_more | replan | stop
  -> Proposed Answer
  -> Final Semantic Observer
  -> approve | bounded rewrite | query_more | refuse_decision
```

## Runtime authority

The LLM proposes semantic interpretations. Python owns state transitions and
completion:

1. A proposed claim proof is accepted only when the observation succeeded,
   supports the active step, is complete, and its `grain` and `fields` cover
   the claim requirement.
2. Unknown claim IDs are ignored.
3. Extracted labels, direct fact values, fields, and units are retained only
   when present in the accepted tool result or tool arguments.
4. `query_more` requires a structured request containing claim ID, grain,
   fields, operation, and reason. An empty request is downgraded to `replan`.
5. `stop` removes tool access from the next agent call.
6. Final `approve` is downgraded to `query_more` while claims remain unresolved.
7. A rewrite is applied at most once. It cannot call MCP and exact violations
   are deterministically replaced or removed.
8. Whole-run, agent-call, observer-call, final-review, and MCP-call budgets are
   enforced by `Phase2Budget`.
9. Provider and transport failures produce explicit bounded termination rather
   than an unhandled exception or an unlimited loop.

## Structured states

### Claim requirement

```text
claim_id
description
required_grain
required_fields
status: required | proved | contradicted
evidence_ids
```

### Evidence fact

```text
subject
predicate
value
unit
grain
evidence_id
derivation
```

### Missing evidence request

```text
claim_id
grain
fields
operation
reason
```

### Final violation

```text
kind: label | unit | number | grain | unsupported_claim
text: exact offending span
replacement: grounded replacement or empty
```

## Verification

The Pure Python test suite passes 22 tests covering:

- known/unknown claim IDs;
- proof acceptance and rejection by grain and fields;
- schema-grounded claim revision;
- structured missing-evidence requests;
- rejection of ungrounded facts, labels, and units;
- final approval downgrade for unresolved claims;
- single bounded rewrite;
- whole-run and per-call budgets;
- MCP transient retry and permanent-error behavior;
- ContextState and EvidenceState regression coverage.

## Status

The architecture is implementation-complete but not yet empirically proven
better. The next step is a fresh live rerun of the six known failure cases,
followed by the full 10-question × 3-run benchmark only if those failures
improve.
