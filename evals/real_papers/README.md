# ScholarFlow real-paper RAG evaluation

This directory is separate from the fixed 135-case constructed regression benchmark.

## Evidence tiers

| Tier | Purpose | May be reported as expert gold? |
| --- | --- | --- |
| `constructed_fixture` | Deterministic regression contract for retrieval, refusal, contradiction and evidence gates | No |
| `real_paper_unreviewed` | Real bibliographic records and human-locatable PDF positions awaiting expert review | No |
| `expert_labelled` | Cases independently checked and adjudicated by named human experts | Only as performance on that labelled set; it still does not prove a scientific conclusion true |
| `live_external_smoke` | Connectivity and current arXiv/OpenAlex/PDF behavior | No; report separately as `complete`, `partial` or `blocked` |

`cases.unreviewed.json` contains public-paper examples whose page, section and table/paragraph positions were checked by a repository maintainer. They are deliberately marked `unreviewed`. The file is a schema and evaluation-code fixture, not an expert-labelled benchmark.

`predictions.schema-fixture.json` is a synthetic system-output fixture. It intentionally contains one wrong BERT Table 1 claim so that the evaluator must expose an unsupported claim and contradiction escape. It is not a gold-label source.

## Annotation rules

1. Start from the exact paper version recorded in `source` and `version`.
2. Record one answerable or refusal question without asking a model to create the gold answer.
3. For every answerable case, copy or conservatively normalize a claim that a human can find at `page`, `section` and the paragraph/table/figure locator.
4. Add every acceptable citation locator and known contradiction trap.
5. Set `label_origin` to `human_annotation` or `imported_bibliographic_fixture`. `model_generated` is not valid schema input.
6. Keep `adjudication_status=unreviewed` until a human reviewer checks the source.
7. Promote a dataset to `expert_labelled` only after all cases are `adjudicated` human annotations. Resolve disagreements outside the model under test and record the final annotator/adjudicator identity.

## Offline execution

The constructed benchmark and real-paper evaluation are emitted in separate report sections:

```bash
SCHOLARFLOW_DB_PATH=/private/tmp/scholarflow-rag-eval.sqlite3 \
SCHOLARFLOW_REAL_EVAL_PREDICTIONS=evals/real_papers/predictions.schema-fixture.json \
npm run eval:rag
```

The JSON and Markdown reports are written beside the temporary database under a dedicated report directory. Do not merge `real_paper_unreviewed` metrics into `expert_labelled` metrics.

Live external smoke checks use a separate command and report. External failure remains `partial` or `blocked`; it must never fall back to these fixtures while retaining a `live_external_smoke` label.
