# ScholarFlow Design System

This file is the visual contract for the ScholarFlow web app. It follows the
`DESIGN.md` structure popularized by VoltAgent's `awesome-design-md`
collection and combines its token-first documentation approach with the calm,
fixed-workbench interaction model observed in LobsterAI. Cohere contributes the
editorial research-table and agent-console patterns; Linear contributes compact
controls and hairline hierarchy; LobsterAI contributes the persistent sidebar,
bounded reading column, and list-to-detail navigation. It does not copy another
product's logo, proprietary fonts, or Electron-specific implementation.

Source inspiration:

- `VoltAgent/awesome-design-md`, `design-md/cohere/DESIGN.md`
- `VoltAgent/awesome-design-md`, `design-md/linear.app/DESIGN.md`
- `netease-youdao/LobsterAI`, renderer shell, sidebar, and reading-width patterns
- Upstream license: MIT, Copyright (c) 2026 VoltAgent
- Reference commit: `664b3e78fd1a298ba11973822da988483256d4b4`

## 1. Visual theme and atmosphere

ScholarFlow is a local-first research operating system. The interface should
feel calm, exact, and evidence-led: an editorial research surface inside a
controlled AI workbench.

- Use a quiet neutral rail and near-white canvas for long research sessions.
- Reserve ScholarFlow green for the logo, current step, success state, and
  primary action; never use it as a full-height color field.
- Let tables, rules, and typography carry dense information. Do not turn every
  row into a floating card.
- Reserve the dark product field for high-value summaries and agent execution.
- Keep the UI flat. Hierarchy comes from surface changes and hairline borders,
  not large shadows or decorative gradients.

## 2. Color palette and roles

```css
--sf-ink: #1a1d23;
--sf-ink-muted: #636a76;
--sf-ink-subtle: #9298a3;
--sf-canvas: #f8f9fb;
--sf-surface: #ffffff;
--sf-surface-soft: #f0f1f4;
--sf-surface-tint: #f5f6f8;
--sf-deep-green: #16845b;
--sf-deep-green-hover: #0f6b49;
--sf-action: #16845b;
--sf-action-hover: #0f6b49;
--sf-coral: #ff7759;
--sf-border: rgba(224, 226, 231, 0.9);
--sf-border-soft: rgba(224, 226, 231, 0.58);
--sf-success: #16845b;
--sf-warning: #a86400;
--sf-danger: #b43d28;
```

Roles:

- Green is a semantic product accent, not a navigation background.
- The action green is used for links, keyboard focus, and the primary state.
- Coral is a small signal for warnings or taxonomy; never use it as decoration.
- Semantic success/warning/danger colors must remain distinguishable from the
  workflow status text and always include a text label.

## 3. Typography

Use locally available system fonts; do not fetch remote font files.

```css
--sf-font-display: "SF Pro Display", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--sf-font-body: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--sf-font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
```

- Workspace title: 28-34px, 580-650 weight, -0.03em tracking.
- Section title: 18-22px, 600 weight, -0.015em tracking.
- Body: 14-16px, 400 weight, 1.55-1.7 line height.
- UI label: 11-12px, 650 weight, 0.08em uppercase tracking.
- Technical/status value: 11-13px mono, 500-650 weight.
- Chinese and English should share one restrained hierarchy. Do not force
  uppercase on Chinese text.

## 4. Spacing, shape, and depth

Use a 4px base scale:

```text
4, 8, 12, 16, 20, 24, 32, 40, 48
```

- Controls: 8px radius, at least 40px tall.
- Content panels: 12px radius.
- Major product field: 16px radius.
- Chips/status: full pill only when the content is short.
- Default elevation: 1px border, no shadow.
- Optional floating elevation: `0 16px 40px rgba(23, 23, 28, 0.06)` and only
  for overlays or the primary summary field.

## 5. Shell and layout

Desktop uses a fixed two-zone research workbench plus an on-demand trace drawer:

1. 244px left rail: identity, active project, and the truthful workflow pipeline.
2. Main canvas: current task, evidence, tables, forms, and execution controls.
3. Right trace drawer: warnings, saved artifacts, and backend timeline; hidden
   until requested so it cannot squeeze the reading surface.

The viewport does not scroll as one giant document. Rail and main canvas own
their scroll contexts, Paper Card details replace the main list page, and prose
uses a maximum 760px reading column.

## 6. Component rules

### Workflow rail

- Neutral gray background with dark primary text and quiet secondary text.
- Every step keeps its backend-derived status label (`ready`, `running`,
  `partial`, `complete`, `blocked`, `error`).
- Selected step uses a quiet neutral surface plus a 2px ScholarFlow-green edge.
- Progress is derived from real workflow steps; never hard-code completion.

### Buttons

- Primary: near-black or action blue, white text, 8px radius.
- Secondary: transparent/white surface, hairline border, dark text.
- Disabled: preserve the label and explanation; lower contrast without hiding.
- Focus: visible 2px action-blue outline with 2px offset.

### Panels and metrics

- Use white on the mineral canvas.
- Metrics use thin separators and large values, not colorful gradients.
- The dashboard summary may use the deep-green product field.
- Avoid glassmorphism, oversized shadows, and gradient backgrounds.

### Research tables

- White editorial surface, strong column alignment, rule-separated rows.
- Metadata uses muted text; evidence or quality states use small labelled chips.
- On narrow screens, allow horizontal scrolling rather than deleting columns.

### Agent console

- Use a controlled dark field or bordered white console.
- Plan, run, cancellation, and warning states must remain explicit.
- Never visually present partial/degraded retrieval as complete.

### Warnings and evidence boundaries

- Warning and error blocks include icon, label, and full message.
- `partial`, `low_recall`, cached, rate-limited, and offline conditions remain
  visible and are not collapsed into generic success states.

### Direction Review and Paper Card

- Direction Review is action-first: controls, evidence status, recommended
  papers, all paper rows, then collapsible supporting material.
- Long generated summaries are bounded to a 760px column and collapsed by
  default; the complete source text remains available.
- A paper row is 76-96px tall, keeps a two-line title and concise evidence
  metadata, and behaves as one accessible button.
- Opening a paper uses `#paper-reader/<paper-id>?from=direction-review`, pushes
  browser history, moves focus to the paper title, and never silently falls
  back to the first paper when the requested ID is missing.
- The full Direction Paper detail remains intact: evidence level, translation,
  signals, Research Sight, reproduction, counterexample, follow-up, and all
  structured sections.
- The Deep Paper Card never lays twelve long answers into equal-height columns.
  Use a compact twelve-item table of contents and render one readable section
  at a time; evidence scope and missing evidence appear once at card level.
- Full-text state is provenance, not decoration: show acquisition status, PDF
  source, parsed page/character counts, and the exact failure reason. When an
  open PDF cannot be resolved, keep a local PDF upload and pasted-evidence path
  available without upgrading the card beyond its verified evidence level.

## 7. Motion and interaction

- Hover transitions: 140-180ms, color/border/transform only.
- Avoid autoplay, ambient animation, and parallax in the workbench.
- Respect `prefers-reduced-motion`.
- Use motion to confirm state changes, never to mask latency.

## 8. Responsive behavior

- Above 860px: fixed 244px rail plus independently scrolling main canvas.
- The trace remains an overlay drawer at every width.
- Below 860px: the workflow rail becomes an off-canvas drawer; the main canvas
  keeps the whole viewport and the list/detail route split remains unchanged.
- Below 720px: metrics use a 2x2 grid and form controls become one column.
- Below 560px: secondary prose is reduced, Paper Card paging uses icon controls,
  and primary touch targets remain at least 44px where practical.
- Tables keep horizontal scroll and their semantic header cells.

## 9. Do and do not

Do:

- Make real project state and evidence quality the strongest visual signals.
- Prefer editorial rows, rules, and open space for research content.
- Use a single dominant accent per surface.
- Keep local-first, API, artifact, and timeline state legible at a glance.

Do not:

- Add synthetic papers or demo content to fill empty states.
- Hide blocked, partial, degraded, cached, or offline workflow outcomes.
- Mix several bright gradients, glass cards, or large soft shadows.
- Copy another company's logo, wordmark, or proprietary font.
- Redesign accessible labels or stable E2E selectors without updating coverage.
