# Deep Paper Card Protocol

The deep paper card is the core reading artifact in ScholarFlow. It is designed to help users understand why a paper exists, what it really contributes, where it is weak, and what could be done next.

The agent must not reduce this workflow to a generic paper summary.

## Output Goals

Each paper card should help the user answer:

- What problem did the paper solve?
- Why was this problem worth solving?
- What was missing in prior work?
- How might the authors have arrived at the idea?
- What is the method's core intuition?
- What exactly happens from input to output?
- What theory or math is necessary to understand the method?
- Do the experiments actually support the claims?
- What should I remember after reading it?
- What assumption is most vulnerable?
- What can I reproduce in one week?
- How could I attack the paper's core claim?
- What non-incremental follow-up idea becomes possible?

## Required Sections

### 1. Research Problem And Background

Explain the research problem proposed and solved by the paper. Add necessary background so a beginner can understand why the problem matters.

The output should cover:

- The task or phenomenon.
- The research context.
- Why the problem is important.
- What value solving it creates.

### 2. Prior Work And Limitations

Explain whether this problem had already been addressed and why prior solutions were insufficient.

Possible limitation types:

- Unrealistic data assumptions.
- Incomplete evaluation metrics.
- Weak generalization.
- High compute or annotation cost.
- Poor interpretability.
- Benchmark bias.
- Missing failure-mode analysis.

### 3. Reconstructed Author Reasoning Path

This is a required core section.

Before explaining the proposed method, reconstruct the possible reasoning path that could have led to the paper's idea.

Rules:

- Do not use the paper's own contribution as a premise.
- Use only prior background, known failure modes, empirical observations, and related work.
- Explain possible inspirations and intuitions.
- Make clear when the reconstruction is an inference rather than a confirmed author statement.

The goal is to help the user understand why a capable researcher could have thought of this idea from existing knowledge.

### 4. Core Intuition

Explain the method's core idea in concise language.

The output should answer:

- What is the method trying to make easier, more reliable, or more measurable?
- What is the one-sentence essence of the idea?
- Why is this idea plausible?

### 5. Method Pipeline With A Real Example

Describe the concrete method using an example.

Required format:

```text
Input:
Processing:
Intermediate states:
Output:
```

The example should be realistic enough to make the pipeline understandable, but it must not invent experimental results.

### 6. Math And Theory Explanation

If the paper contains important formulas, optimization objectives, losses, proofs, or theoretical assumptions, explain them from a beginner-friendly perspective.

Required behavior:

- First introduce the necessary math background.
- Explain what each formula term means.
- Explain the intuition behind the objective.
- Connect the math back to the method behavior.

If the paper does not contain meaningful math or theory, state this clearly and skip the section. Do not fabricate theory.

### 7. Experiment Logic And Claim Validation

Summarize experiments by logic, not by dumping numbers.

Use this format:

```text
Question:
Experiment:
Answer:
```

The analysis should explain whether the experiment really supports the paper's claim.

### 8. Take-Aways

Summarize what the user should retain after reading the paper.

Cover:

- Method-level lesson.
- Experiment-design lesson.
- Research-positioning lesson.
- Transferable idea for future work.

### 9. Weakest Assumption

Identify the most fragile assumption in the paper.

Examples:

- The benchmark represents real deployment.
- The metric measures the intended capability.
- The training data covers the relevant distribution.
- The annotation process is reliable.
- The baseline is strong enough.
- The model scale assumption is realistic.

This section should be specific and attackable.

### 10. One-Week Minimal Reproduction

Design a minimal reproduction that can be completed in about one week.

Required fields:

- Claim to test.
- Minimal dataset or subset.
- Baseline.
- Required compute.
- Steps.
- Success criterion.
- Failure criterion.
- Expected risks.

The goal is to verify one central claim, not reproduce the whole paper.

### 11. Counterexample Design

Design a counterexample that challenges the paper's core claim.

The counterexample should target:

- A hidden assumption.
- A failure mode.
- A metric blind spot.
- A data distribution shift.
- A situation where the method's intuition breaks.

Avoid generic suggestions such as "try another dataset" unless the dataset shift directly attacks a specific assumption.

### 12. Non-Incremental Follow-Up Idea

Propose one follow-up idea based on limitations, unmet needs, and the counterexample analysis.

The idea should avoid:

- Only changing the backbone.
- Only adding a module.
- Only changing a dataset.
- Only replacing the metric name.

Prefer ideas based on:

- New failure-mode framing.
- New evaluation perspective.
- New task definition.
- New causal or mechanistic hypothesis.
- New evidence requirement.

## Recommended Artifact Formats

Each deep paper card should be saved as both Markdown and JSON.

Markdown is for reading:

```text
artifacts/papers/<paper_slug>/paper_card.md
```

JSON is for downstream agents:

```text
artifacts/papers/<paper_slug>/paper_card.json
```

The JSON should preserve structured fields for later gap analysis, novelty checking, and experiment planning.

