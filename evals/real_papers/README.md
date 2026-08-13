# ScholarFlow real-paper development evaluation

This directory is separate from the fixed 135-case constructed regression benchmark. Its default path is a deterministic, offline `development_benchmark`; human expert review is an optional extension.

## Current status

- `cases.development.json`: **4 generated candidates, validated 0/50**, covering 3 papers and 3 domains. They do not enter development metrics until fixed local PDFs pass source validation.
- `cases.expert.json`: optional expert dataset, currently empty. This does not block `npm run eval:rag`.
- `cases.unreviewed.json`: legacy compatibility input. New development work should use `cases.development.json` and `development_status`.
- Target: 50–100 validated development cases. The target is a coverage goal, not a reason to upgrade generated records.

The development metrics measure repeatable system behavior on fixed sources. They are not expert accuracy, human accuracy, inter-annotator agreement, scientific truth, or validation of paper conclusions.

## Files

| File | Role |
| --- | --- |
| `cases.schema.json` | Dataset v3 schema; v2 remains readable |
| `schema.json` | Compatibility reference retained for older tooling |
| `cases.development.json` | Default generated/validated development cases |
| `cases.unreviewed.json` | Legacy compatibility entry only |
| `cases.expert.json` | Optional expert-review dataset; currently empty |
| `resources.local.example.json` | Non-secret local PDF manifest template |
| `annotation-guide.md` | Optional advanced human review and adjudication procedure |
| `predictions.schema-fixture.json` | Evaluator contract fixture, never system evidence |

Local manifests matching `resources.local*.json` are ignored except for the example. Full PDFs, large excerpts and private reviewer identities must not be committed.

## Evaluation tiers and development states

| Tier | Purpose | Default behavior |
| --- | --- | --- |
| `constructed_fixture` | Deterministic retrieval/refusal code regression | Always runs; fixed at 135 cases |
| `development_benchmark` | Fixed-PDF, deterministically validated system regression | Default real-paper tier |
| `expert_labelled` | Optional human-reviewed extension | Empty means `not_configured`, never blocks development |
| `live_external_smoke` | Current external connectivity | Separate command/report only |

Development cases use these independent states:

- `generated`: candidate only; excluded from metrics.
- `validated`: passed current deterministic source and label checks; included.
- `maintainer_verified`: optional stronger development status; included, but not an expert claim.
- `invalid`: failed validation and retains explicit errors; excluded.
- `disabled`: intentionally excluded.

Expert `review_status` fields remain available for optional advanced review, but are not required for `development_benchmark`.

## Deterministic validation

Copy `resources.local.example.json` to ignored `resources.local.json` and fill the exact local PDF identity. Validation checks schema completeness, paper/version/source identity, SHA-256, page count and locator bounds, evidence excerpt presence and hash, the configured answer comparator, whole-document refusal probes, paper-level split isolation and duplicate/near-duplicate questions. Gold-only fields are projected out before ingestion, retrieval or RAG execution.

```bash
npm run eval:rag:dataset -- validate \
  --cases evals/real_papers/cases.development.json \
  --resources evals/real_papers/resources.local.json \
  --output /private/tmp/scholarflow-cases.validated.json

npm run eval:rag:dataset -- coverage \
  --cases evals/real_papers/cases.development.json

npm run eval:rag:dataset -- split-check \
  --cases evals/real_papers/cases.development.json
```

Schema correctness alone never upgrades a case. If a PDF is absent, version/hash differs, a page is missing, an excerpt cannot be found, or a refusal probe finds direct support, the candidate remains non-metric and the error is reported.

## Offline prediction and evaluation

The standard command can validate local resources, write a temporary validated dataset, run PDF parsing, chunk/FTS ingestion, retrieval and the real RAG answer service, then score only `offline_system_run` predictions:

```bash
SCHOLARFLOW_DB_PATH=/private/tmp/scholarflow-rag-eval.sqlite3 \
  npm run eval:rag -- \
  --real-dataset evals/real_papers/cases.development.json \
  --real-resources evals/real_papers/resources.local.json \
  --report-dir /private/tmp/scholarflow-rag-eval-report
```

Or run the two stages explicitly:

```bash
npm run eval:rag:real-predict -- \
  --cases /private/tmp/scholarflow-cases.validated.json \
  --resources evals/real_papers/resources.local.json \
  --output /private/tmp/scholarflow-real-predictions.json

SCHOLARFLOW_DB_PATH=/private/tmp/scholarflow-rag-eval-2.sqlite3 \
  npm run eval:rag -- \
  --real-dataset /private/tmp/scholarflow-cases.validated.json \
  --real-resources evals/real_papers/resources.local.json \
  --real-predictions /private/tmp/scholarflow-real-predictions.json
```

Without local resources, `development_benchmark` reports `blocked_missing_resources`. An empty optional expert file reports `not_configured`. Neither condition erases or blocks the completed constructed fixture section.

## Coverage target

The 50–100 case goal should cover main-text facts, numerical values and units, tables, figures/captions, equations, experiment setup, datasets/metrics, conditional limitations, paper versions, supplemental material, `no_reliable_hit`, refusal and conflicting sources. Coverage output reports the actual count, for example `validated 18/50`; generated candidates are never counted as validated.

## Citation locator boundary

Runtime `machine_locator` binds paper, source hash/version, page, normalized section, chunk index/hash and evidence excerpt hash. `semantic_locator` is optional and may be emitted only when the parser actually identifies paragraph/table/figure/equation/abstract structure. Plain pypdf text containing “Table 2” remains a chunk and cannot claim structured table parsing.

Evaluation reports source identity, page, machine anchor and semantic locator separately. Runtime `citation_id` is not treated as a stable cross-version gold identifier. Semantic accuracy is `null` when the system made no semantic-locator attempt.

See [`annotation-guide.md`](annotation-guide.md) only if the optional expert-review workflow is needed.
