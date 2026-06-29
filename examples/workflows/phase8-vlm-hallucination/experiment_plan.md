# Example Experiment Plan

## Claim

Evidence-sensitivity tests reveal hallucination behavior that final-answer accuracy misses.

## Dataset

Small public VQA-style subset selected for object, attribute, and relation questions. This example does not include dataset files.

## Baseline

Compare normal evaluation against evidence-perturbed evaluation for two open VLMs.

## Metrics

- Answer accuracy
- Answer flip rate under evidence change
- Contradiction rate
- Prompt sensitivity

## Ablations

- With image vs. text-only prompt
- Original image vs. masked evidence region
- Neutral prompt vs. evidence-demanding prompt

## One-Week Timeline

1. Day 1: select 50 public examples and define perturbation rules.
2. Day 2: build inference script and prompt templates.
3. Day 3: run two open VLMs.
4. Day 4: score answer flips and contradictions.
5. Day 5: analyze failure cases.
6. Day 6: write short report and limitations.
7. Day 7: decide whether the idea deserves a larger benchmark.

## Success Criterion

Find cases where final answers look correct but evidence sensitivity fails.

## Failure Criterion

If perturbations are too noisy to isolate evidence use, the pilot cannot support the claim.
