# ScholarFlow real-paper evaluation data

This directory is separate from the fixed 135-case constructed regression benchmark.

## Current audited status

- `cases.unreviewed.json`: **4 drafts**, covering 3 papers and 3 domains. They have fixed public source versions and locators, but no independent reviewer pair or adjudication.
- `cases.expert.json`: **0/50 expert-labelled cases**. It is intentionally empty.
- Formal target: 50–100 cases; current planning target is 75 cases over 15–25 papers and at least 5 domains.

No current file supports claims about expert accuracy, inter-annotator agreement, or scientific truth. The four drafts are not renamed or copied into the expert dataset.

## Files

| File | Role |
| --- | --- |
| `cases.schema.json` | Authoritative JSON Schema for dataset v2 |
| `schema.json` | Compatibility reference to `cases.schema.json` |
| `annotation-guide.md` | Human annotation, adjudication, coverage and audit procedure |
| `cases.unreviewed.json` | Human-locatable drafts excluded from default evaluation |
| `cases.expert.json` | Formal expert-only dataset; currently empty |
| `resources.local.example.json` | Non-secret local PDF manifest template |
| `predictions.schema-fixture.json` | Synthetic evaluator contract fixture, never system or expert evidence |

Local PDF manifests matching `resources.local*.json` are ignored, except for the example template. Full PDFs, large excerpts and private reviewer identity mappings must not be committed.

## Evidence tiers

| Tier | Purpose | Formal metric source? |
| --- | --- | --- |
| `constructed_fixture` | Deterministic retrieval/refusal regression | No |
| `real_paper_unreviewed` | Annotation/schema development | No |
| `expert_labelled` | Two independent human reviews plus adjudication | Yes, only after the 50-case/15-paper/5-domain gate |
| `live_external_smoke` | Current external connectivity | No; report separately |

## Dataset commands

```bash
npm run eval:rag:dataset -- validate \
  --cases evals/real_papers/cases.expert.json

npm run eval:rag:dataset -- coverage \
  --cases evals/real_papers/cases.unreviewed.json

npm run eval:rag:dataset -- disagreements \
  --cases evals/real_papers/cases.unreviewed.json

npm run eval:rag:dataset -- split-check \
  --cases evals/real_papers/cases.unreviewed.json
```

`promote` advances exactly one state and requires a separate output file:

```bash
npm run eval:rag:dataset -- promote \
  --cases /private/tmp/annotation-round-1.json \
  --case-id <case-id> \
  --output /private/tmp/annotation-round-2.json
```

The validator rejects cross-split papers, missing version/hash, out-of-range locators, wrong-version citations, answerable cases without evidence, refusal cases with direct support, duplicate/near-duplicate questions, false expert status and unresolved disagreements.

## Offline system predictions

Copy `resources.local.example.json` to an ignored local manifest and replace every placeholder with the exact local PDF identity. The cases and resource manifest must agree on paper ID, version, source URL, SHA-256 and page count.

```bash
PYTHONPATH=services/api/src .venv/bin/python \
  -m scholarflow_api.real_paper_prediction_runner \
  --cases evals/real_papers/cases.unreviewed.json \
  --resources evals/real_papers/resources.local.json \
  --output /private/tmp/scholarflow-real-predictions.json
```

This command is useful for pipeline testing on drafts, but the default evaluator will not score those drafts as expert gold. Formal evaluation defaults to `cases.expert.json` and reports `0/50` until real human work is complete:

```bash
SCHOLARFLOW_DB_PATH=/private/tmp/scholarflow-rag-eval.sqlite3 \
  npm run eval:rag
```

When a sufficient expert dataset exists, pass its matching `offline_system_run` predictions. `offline_test_fixture`, missing predictions and blocked executions remain explicitly blocked and are never substituted.

See [`annotation-guide.md`](annotation-guide.md) for the state machine, 75-case coverage matrix, reviewer independence rules and release sampling procedure.
