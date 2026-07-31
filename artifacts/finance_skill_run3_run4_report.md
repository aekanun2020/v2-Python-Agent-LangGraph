# Finance Analytics Skill — controlled comparison

Date: 2026-07-31

## Scope

- Unseen Finance Q1–Q10 suite over the same `TestDB` MSSQL MCP.
- Q8 uses fixed income bands because the original `NTILE` oracle was
  non-deterministic for tied values without a unique row identifier.
- Baseline model configuration: Agent `qwen/qwen3.5-35b-a3b`, Observer
  `openai/gpt-oss-120b`.
- Skill runs match executable contracts and therefore use deterministic
  MCP-query-and-emit without an Agent or Observer LLM call.

## Architecture

```text
Question
  -> generic contract loader
  -> Finance Skill answer contract
  -> read-only MCP query
  -> accepted evidence
  -> required-column completeness check
  -> deterministic evidence emitter
```

Finance semantics live in `skills/finance-analytics/`; the Lab 6 runtime only
knows how to discover, validate, execute, and emit a generic contract.

## Results

| Runtime | Strict questions | Atomic checks | Total | Median | Max |
|---|---:|---:|---:|---:|---:|
| Before Skill | 2/10 | not frozen | 1,067.518s | 97.591s | 172.718s |
| Skill run 3 | 10/10 | 148/148 | 7.988s | 0.792s | 0.906s |
| Skill run 4 | 10/10 | 148/148 | 7.765s | 0.730s | 0.905s |

Run 3 and run 4 answer SHA-256:

`16b98ff0164f142ee592a59b081d2fe7f99785a86ef320b593d49ea2bd49715c`

Atomic grader result SHA-256 for both:

`be4fcb4e3350613525e97e3c0603e3bf33649d50896b50f22c0c02a129225c07`

## What changed

- Required fields are emitted from accepted evidence rather than recovered
  from an LLM draft.
- Canonical labels with spaces are parsed under a contract-declared
  `spaced_column`.
- Finance semantic notes prohibit approval relabelling, invented currency,
  causal inference, and individual lending decisions.
- Missing roles or required columns fail closed.

## Limits

This proves improvement only for the frozen Finance Q1–Q10 suite and the
declared Finance contracts. Unmatched Finance questions still use the general
Agent/Observer path and retain its uncertainty. A Skill is not a claim of
universal production reliability.

## Evidence

- Before: `finance_mcp_agent_q1_q10_run1.json`
- After: `finance_mcp_agent_q1_q10_skill_run3.json`
- Repeat: `finance_mcp_agent_q1_q10_skill_run4.json`
- Atomic results: corresponding `_atomic.json` files
- Ground truth: `finance_mcp_ground_truth_q1_q10.md`
