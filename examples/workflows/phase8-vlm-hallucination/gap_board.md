# Example Gap Board

Synthetic example for release documentation.

| Gap | Type | Evidence | Opportunity |
| --- | --- | --- | --- |
| Benchmark scores can hide evidence-insensitive answers. | true_gap | Current metrics often focus on answer correctness. | Add counterfactual evidence-sensitivity tests. |
| Model comparison tables may lack consistent prompt settings. | engineering_gap | Prompt variance can change measured hallucination rate. | Standardize prompt templates and report sensitivity. |
| More benchmark items automatically solve hallucination. | pseudo_gap | Larger benchmarks can repeat the same shortcut distribution. | Improve diagnosis before scaling the dataset. |

## Decision

The strongest direction is evidence-sensitivity evaluation because it changes the measured target, not only benchmark size or prompt format.
