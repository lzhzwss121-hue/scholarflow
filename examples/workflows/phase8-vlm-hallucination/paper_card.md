# Example Deep Paper Card

This synthetic card demonstrates ScholarFlow's 12-section structure. It is intentionally generic and should be replaced with a real paper card generated from a selected paper.

## 1. Research Problem And Background

The paper studies whether VLM hallucination benchmarks actually test visual evidence use or mostly expose language and dataset priors.

## 2. Prior Work Gap

Prior benchmarks often count incorrect object or attribute mentions, but may not isolate whether the model looked at the image evidence.

## 3. Reconstructed Author Thinking Path

Starting from existing VQA and hallucination evaluations, the likely observation is that many failures can be explained by answer-frequency shortcuts, prompt priors, or object co-occurrence priors. A natural next step is to design tests where the answer should change only when the visual evidence changes.

## 4. Core Intuition

Hallucination evaluation should measure evidence sensitivity, not only final-answer correctness.

## 5. Method Pipeline

Input: image-question pairs with controlled evidence conditions.
Processing: compare model answers before and after evidence-relevant perturbations.
Output: scores that separate answer correctness from evidence sensitivity.

## 6. Math Or Theory

The core idea can be expressed as a conditional dependence check: if the visual evidence changes while the question remains fixed, an evidence-grounded model should change its answer in the expected direction.

## 7. Experiment Logic

Question: Does the model rely on visual evidence?
Experiment: Apply controlled visual or semantic perturbations.
Answer: If answers remain stable when evidence changes, the model is likely using shortcuts.

## 8. Take-Aways

- Final-answer accuracy is insufficient for hallucination evaluation.
- Counterfactual evidence changes can expose shortcut behavior.
- Benchmark design and model behavior should be analyzed separately.

## 9. Weakest Assumption

The benchmark assumes the perturbation changes only the intended evidence and does not introduce unrelated artifacts.

## 10. One-Week Minimal Reproduction

Use an open VQA subset, select 50 image-question pairs, create controlled text prompts or image masks, and compare answer flips across two open VLMs.

## 11. Counterexample Design

Construct cases where the model gives correct answers from language priors even when the image is removed or contradicted.

## 12. Follow-Up Idea

Build an evidence-sensitivity benchmark that scores whether the model's answer changes for the right visual reason, not merely whether it matches a label.
