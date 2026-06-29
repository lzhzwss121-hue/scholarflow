# Example Idea Validation Report

## Idea

Evaluate VLM hallucination through evidence-sensitivity rather than final-answer correctness alone.

## Why It Is Not Merely Incremental

The idea changes the evaluation target from "is the answer correct" to "does the answer respond correctly to controlled evidence changes."

## Difference From Existing Work

Instead of only collecting harder QA pairs, the method introduces paired conditions that expose shortcut-based invariance.

## Novelty Risk

Medium. Counterfactual evaluation is a known evaluation pattern, so novelty depends on the quality of evidence controls and diagnostic metrics.

## Feasibility

One-week minimal reproduction.

## Key Risks

- Perturbations may introduce artifacts.
- Open VLM outputs may be unstable across prompts.
- Small sample size may only support a pilot claim.
