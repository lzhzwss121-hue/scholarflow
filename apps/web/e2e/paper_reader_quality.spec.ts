import { expect, test, type Page } from "@playwright/test";

const project = {
  id: "project_e2e_reader_quality",
  title: "Paper Reader Quality Regression",
  description: "Locks readable 12-section layout and evidence-boundary deduplication.",
  keyword: "grounded VQA evidence faithfulness",
  field: "Artificial Intelligence",
  language: "zh-CN",
  workflow: "survey-to-experiment",
  stage: "paper-card",
  active_session_id: "session_e2e_reader_quality",
  created_at: "2026-07-10T00:00:00+00:00",
  updated_at: "2026-07-10T00:00:00+00:00",
};

const paper = {
  id: "paper_e2e_reader_quality",
  project_id: project.id,
  title: "Grounded Evidence Evaluation for Visual Question Answering",
  authors: "A. Researcher",
  abstract: "This paper evaluates whether VQA answers remain faithful to visual evidence.",
  year: "2026",
  type: "Benchmark",
  venue: "CVPR",
  source: "arxiv",
  url: "https://arxiv.org/abs/2601.00999",
  relation: "Matches grounded VQA evidence faithfulness.",
  priority: "High",
  code: "unknown",
  relevance_score: 1.7,
  relevance_quality: "strong",
  matched_terms: ["VQA", "evidence faithfulness"],
  created_at: "2026-07-10T00:00:00+00:00",
};

const legacyBoundary =
  "证据边界（abstract_only）：当前没有 PDF/完整正文，下面是基于标题、摘要和可选片段的阅读提纲，不能当作已讲清整篇论文。";

const sectionTitles = [
  "1. 研究问题与背景",
  "2. 已有研究与不足",
  "3. 作者可能的思考路径重建",
  "4. 核心 Intuition",
  "5. 方法 Pipeline 与真实例子",
  "6. 数学与理论解释",
  "7. 实验逻辑与 Claim 验证",
  "8. Take-aways",
  "9. 最脆弱的假设",
  "10. 一周最小复现实验",
  "11. 反例设计",
  "12. 非增量 Follow-up Idea",
];

const sections = sectionTitles.map((title, index) => ({
  id: `quality_section_${index + 1}`,
  title,
  content: [
    legacyBoundary,
    `阅读提纲：阅读原文时应重点核验「${title}」对应的证据。`,
    `当前可见线索：第 ${index + 1} 段唯一科研内容，用于确认切换目录后不会显示另一段。`,
    "证据缺口：缺少 PDF 中的方法、实验表、消融和失败样本。",
    "需要验证的问题：补充 PDF 后检查原文证据是否支持该判断。",
  ].join("\n"),
}));

const directionPayload = {
  schema_version: "direction_review.v2",
  direction: project.keyword,
  round: 1,
  review_status: "partial",
  target_paper_count: 10,
  round_read_count: 1,
  relevant_read_count: 1,
  low_relevance_count: 0,
  off_topic_count: 0,
  relevance_coverage: {
    candidate_count: 1,
    returned_count: 1,
    strong_match_count: 1,
    medium_match_count: 0,
    weak_match_count: 0,
    off_topic_count: 0,
    filtered_count: 0,
  },
  total_read_count: 1,
  recommended_paper_ids: [paper.id],
  direction_summary: "Reader quality regression fixture.",
  artifact_refs: [],
  errors: [],
  papers: [
    {
      paper,
      paper_id: paper.id,
      paper_title: paper.title,
      abstract_translation: "本文评估视觉问答答案是否忠实于视觉证据。",
      evidence_level: "abstract_only",
      signals: {
        task: "VQA evidence faithfulness evaluation",
        method: "counterfactual grounding benchmark",
        dataset: "POPE and A-OKVQA",
        metric: "grounding faithfulness",
        baseline: "LLaVA",
        claim: "counterfactual evidence exposes hallucination",
        limitation: "abstract does not expose ablation details",
        contribution_type: "benchmark",
        missing_signals: ["full-text ablation"],
      },
      sections,
      research_sight: {
        motivation_sharpness: "Targets a falsifiable evidence-faithfulness failure.",
        solution_elegance: "Uses counterfactual evidence intervention.",
        evaluation_integrity: "Requires PDF tables and failure cases for verification.",
        paradigm_inspiration: "Moves from answer accuracy to evidence grounding.",
        why_good: "The target failure is measurable.",
        why_not_good: "The abstract does not establish coverage.",
        better_angle: "Audit sensitivity to conflicting evidence.",
        baseline_comparison: "Compare with LLaVA and POPE.",
        next_step_proposal: "Reproduce a 50-sample counterfactual probe.",
        evidence_pack: {
          evidence_level: "abstract_only",
          confidence: "medium",
          snippets: [],
          missing_evidence: ["full_pdf"],
          grounding_summary: "Only title and abstract evidence are available.",
        },
        critique_evidence: [],
      },
      weakest_assumption: "Counterfactual prompts represent real hallucination failures.",
      minimal_reproduction: "Run 50 paired examples against LLaVA.",
      counterexample: "Keep the answer constant while replacing its visual support.",
      follow_up_idea: "Measure causal evidence reliance rather than rationale overlap.",
      why_selected: "Strong direction match.",
      venue_signal: "CVPR",
      self_read_priority: true,
    },
  ],
};

const artifact = {
  id: "artifact_e2e_reader_quality",
  project_id: project.id,
  title: "direction_review_round_1.md",
  kind: "markdown",
  content_markdown: "# Direction Review reader quality fixture",
  content_json: JSON.stringify(directionPayload),
  diff: "+ paper reader quality regression fixture",
  created_at: "2026-07-10T00:00:00+00:00",
  updated_at: "2026-07-10T00:00:00+00:00",
};

function artifactSummary() {
  return {
    id: artifact.id,
    project_id: artifact.project_id,
    title: artifact.title,
    kind: artifact.kind,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at,
    markdown_bytes: new TextEncoder().encode(artifact.content_markdown).length,
    json_bytes: new TextEncoder().encode(artifact.content_json).length,
    markdown_preview: artifact.content_markdown.slice(0, 280),
    json_schema_version: "direction_review.v2",
  };
}

async function mockReaderProject(page: Page) {
  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: [paper] });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [artifactSummary()] });
  });
  await page.route(`**/artifacts/${artifact.id}`, async (route) => {
    await route.fulfill({ json: artifact });
  });
}

test("12-section reader uses a table of contents and one readable section instead of equal-height cards", async ({
  page,
}) => {
  await mockReaderProject(page);
  await page.goto("/#paper-reader");

  const board = page.locator('section.question-board[aria-label="paper card reading"]');
  const toc = page.locator('nav.paper-reader-toc[aria-label="12 段精读目录"]');
  const tocItems = toc.locator(".paper-reader-toc-item");

  await expect(board).toBeVisible();
  await expect(toc).toBeVisible();
  await expect(tocItems).toHaveCount(12);
  await expect(page.locator(".question-grid, .question-card")).toHaveCount(0);
  await expect(board.locator("article.paper-reader-section")).toHaveCount(1);
  await expect(board.locator("#paper-reader-section-1")).toBeVisible();
  await expect(tocItems.first()).toHaveAttribute("aria-current", "true");

  await page.locator("details.reader-supplemental-input > summary").click();
  const pdfUpload = page.locator('.pdf-upload-control[aria-label="upload paper PDF"]');
  await expect(pdfUpload).toBeVisible();
  await expect(pdfUpload.locator('input[type="file"]')).toHaveAttribute("accept", "application/pdf,.pdf");

  await tocItems.nth(6).click();
  await expect(tocItems.nth(6)).toHaveAttribute("aria-current", "true");
  await expect(board.locator("#paper-reader-section-7")).toBeVisible();
  await expect(board.locator(".paper-reader-section-body")).toContainText("第 7 段唯一科研内容");
  await expect(board.locator(".paper-reader-section-body")).not.toContainText("第 1 段唯一科研内容");
});

test("legacy repeated evidence boilerplate is centralized and the mobile reader does not overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockReaderProject(page);
  await page.goto("/#paper-reader");

  const evidenceScope = page.locator('details.reader-evidence-scope[aria-label="paper card evidence scope"]');
  const sectionBody = page.locator(".paper-reader-section-body");
  const tocItems = page.locator(".paper-reader-toc-item");

  await expect(evidenceScope).toHaveCount(1);
  await expect(evidenceScope).toContainText(/摘要|abstract_only/);
  await expect(sectionBody).not.toContainText("证据边界（abstract_only）");
  await expect(sectionBody).not.toContainText("当前没有 PDF/完整正文");
  await expect(tocItems).toHaveCount(12);

  const firstBox = await tocItems.nth(0).boundingBox();
  const secondBox = await tocItems.nth(1).boundingBox();
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  expect(Math.abs((firstBox?.x ?? 0) - (secondBox?.x ?? 0))).toBeLessThanOrEqual(2);
  expect(secondBox?.y ?? 0).toBeGreaterThan((firstBox?.y ?? 0) + (firstBox?.height ?? 0) - 1);

  const overflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
});
