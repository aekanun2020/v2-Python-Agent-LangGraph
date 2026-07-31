# Unseen Paraphrase + Boundary Baseline

## Objective

Measure whether the current literal `question_terms_all/any` selector
generalizes beyond the frozen HR and Finance questions without changing the
selector after seeing failures.

The suite was frozen before the first successful routing run:

- HR: 10 unseen paraphrases + 10 boundary cases
- Finance: 10 unseen paraphrases + 10 boundary cases
- Total: 40 routing cases

Routing evaluation is deterministic and calls neither LLM nor MCP. Live
evaluation calls the read-only MSSQL MCP query declared by each correctly
routed unique contract.

## Routing Baseline

| Domain | Paraphrase recall | Boundary protected | False matches |
|---|---:|---:|---:|
| HR | 6/10 | 9/10 | 1 |
| Finance | 5/10 | 10/10 | 0 |
| **Total** | **11/20 (55%)** | **19/20 (95%)** | **1/20 (5%)** |

The baseline misses nine meaning-preserving paraphrases. These failures occur
when the question uses business-language synonyms instead of the exact
technical tokens in `question_terms_all`.

The one false match is `hr_boundary_005`:

> ควรลดคนหรือเพิ่มคนจาก headcount เพียงอย่างเดียวหรือไม่

It incorrectly selects `staffing_decision_insufficient` because the current
substring selector sees `ลดคน`, `เพิ่มคน`, and `headcount`, even though the
declared contract also requires project-value evidence.

## Live MCP Evidence

Only correctly routed paraphrases were live-tested, with one representative
per unique contract:

| Run | Unique contracts | Evidence complete | Normalized evidence hash |
|---|---:|---:|---|
| 1 | 11 | 11/11 | `d9070a6f6b2c78badea34f0ce181eb35d641d3f4c9b59cb4461ac9a7b4be01bc` |
| 2 | 11 | 11/11 | `d9070a6f6b2c78badea34f0ce181eb35d641d3f4c9b59cb4461ac9a7b4be01bc` |
| 3 | 11 | 11/11 | `d9070a6f6b2c78badea34f0ce181eb35d641d3f4c9b59cb4461ac9a7b4be01bc` |

The normalized hash excludes elapsed time and includes contract id, query
roles, queries, raw MCP results, completion verdict, and missing roles.

## Interpretation

The experiment separates two properties:

1. Contract execution/evidence validation is stable for contracts that are
   selected: 33/33 live completions across three runs with identical evidence.
2. Literal routing does not generalize sufficiently: 55% paraphrase recall and
   one unsafe false match.

Therefore the next change should target intent selection, not query templates,
evidence admission, or deterministic emission. The frozen suite must remain
unchanged while comparing a replacement router.

Recommended acceptance criteria for the next router:

- paraphrase recall at least 90%
- boundary precision 100%
- false matches 0
- live evidence completion 100% for selected contracts
- deterministic contracts remain the final authority after routing

## Artifacts

- `artifacts/unseen_boundary_routing_baseline.json`
- `artifacts/unseen_boundary_live_run1.json`
- `artifacts/unseen_boundary_live_run2.json`
- `artifacts/unseen_boundary_live_run3.json`
- `tests/evaluation/*.json`
- `scripts/evaluate_skill_routing.py`
