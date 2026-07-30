# Finance MCP Agent Q1–Q10 — Run 1

Date: 2026-07-30

## Controlled setup

- Agent: `qwen/qwen3.5-35b-a3b`
- Semantic Observer: `openai/gpt-oss-120b`
- MCP: `https://7ff8-184-22-21-43.ngrok-free.app/mcp`
- Database: `TestDB`
- Ground truth: `finance_mcp_ground_truth_q1_q10.md`
- Evaluation: strict required-claim completeness plus semantic constraints

## Runtime

- Processes completed: 10/10
- Timeouts: 0
- Total: 1,067.518 seconds
- Median: 97.591 seconds/question
- Maximum: 172.718 seconds (Q10)

Execution success is not answer correctness.

## Strict question-level result

| Q | Runtime (s) | Verdict | Evidence |
|---|---:|---|---|
| Q1 | 83.368 | FAIL — incomplete | Count and both averages survived; both requested totals were removed by Final Claim Gate. |
| Q2 | 66.626 | FAIL — semantic | Counts and shares were correct, but an unsupported product-development recommendation survived the rewrite. |
| Q3 | 89.550 | FAIL — semantic | Required status metrics were correct, but unsupported “safe/collectible”, delinquency and risk interpretations survived. |
| Q4 | 86.992 | FAIL — semantic | Required yearly metrics were correct, but unsupported demand/economic explanations survived. |
| Q5 | 102.695 | PASS | All five canonical labels and all four required metrics per label survived with valid rate conversion. |
| Q6 | 102.180 | FAIL — incomplete | Extrema were identified, but required counts and supporting metrics for all requested extrema did not all survive. |
| Q7 | 136.397 | FAIL — incomplete | Funding and interest averages survived, but counts for all five buckets were removed. |
| Q8 | 93.002 | INVALID TEST | Original `NTILE` ground truth was non-deterministic at tied boundaries; excluded from score. |
| Q8R | live replacement | FAIL — incomplete | Fixed-band counts, interest and DTI survived; income ranges and average funded amounts were removed. |
| Q9 | 133.990 | FAIL — semantic | Yearly numbers were correct, but unsupported “funding efficiency / satisfies every need” interpretations survived. |
| Q10 | 172.718 | PASS | Both portfolio benchmarks and the exact five qualifying employment-length segments survived without extra segments. |

Strict score after replacing invalid Q8: **2/10 questions**.

## Important test-design finding

The original Q8 used:

```sql
NTILE(4) OVER (ORDER BY annual_inc)
```

`loans_fact` has no unique row identifier and many rows tie on `annual_inc`. SQL Server may
assign tied rows at a quartile boundary differently between executions/query plans. Counts
remained balanced while downstream averages changed. This is a non-deterministic oracle,
not necessarily an Agent error.

Q8 was therefore redesigned with fixed, left-inclusive bands:

- `<50000`
- `50000-<70000`
- `70000-<100000`
- `100000+`

## Architecture findings

1. MCP/tool execution recovery worked: every question completed and no run timed out.
2. The Observer detected unsupported interpretation in all ten original drafts.
3. Detection did not guarantee correction:
   - unsupported text sometimes survived `verify-then-emit`;
   - required supported aggregates sometimes disappeared.
4. Current typed contracts are strong for the frozen HR suite but do not yet generalize to
   unseen Finance aggregate shapes.
5. The next change should not add Finance-specific phrases. It should make claim extraction
   preserve the requested metric contract generically:
   - dimensions and canonical labels;
   - aggregate function and field;
   - filters and bucket boundaries;
   - required group coverage;
   - units/conversions;
   - semantic prohibitions.

## Evidence files

- Raw run: `finance_mcp_agent_q1_q10_run1.json`
- Ground truth and SQL: `finance_mcp_ground_truth_q1_q10.md`

This run disproves a universal-generalization claim. The current architecture was better
than its baseline on the frozen HR suite, but it is not yet reliable on this unseen Finance
suite.
