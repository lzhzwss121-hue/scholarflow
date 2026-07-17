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

function artifactSummary(item = artifact) {
  return {
    id: item.id,
    project_id: item.project_id,
    title: item.title,
    kind: item.kind,
    created_at: item.created_at,
    updated_at: item.updated_at,
    markdown_bytes: new TextEncoder().encode(item.content_markdown).length,
    json_bytes: new TextEncoder().encode(item.content_json).length,
    markdown_preview: item.content_markdown.slice(0, 280),
    json_schema_version: item.title.includes("direction_review") ? "direction_review.v2" : "paper_card.v2",
  };
}

async function mockReaderProject(page: Page, artifacts = [artifact]) {
  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: [paper] });
  });
  await page.route(`**/projects/${project.id}/paper-cards`, async (route) => {
    const cards = artifacts.flatMap((item) => {
      if (!item.title.toLowerCase().includes("paper_card")) {
        return [];
      }
      const payload = JSON.parse(item.content_json) as Record<string, unknown>;
      const card = (payload.card ?? payload) as Record<string, unknown>;
      if (!Array.isArray(card.sections)) {
        return [];
      }
      const fullText = (payload.full_text ?? card.full_text ?? {}) as Record<string, unknown>;
      return [
        {
          ...card,
          id: item.id,
          project_id: item.project_id,
          paper_id: (payload.paper_id as string) || paper.id,
          paper_title: (card.paper_title as string) || paper.title,
          artifact_id: item.id,
          source_artifact_title: item.title,
          card_source: "paper_table",
          evidence_level: (payload.evidence_level as string) || card.evidence_level || "metadata_only",
          full_text: fullText,
          created_at: item.created_at,
          updated_at: item.updated_at,
        },
      ];
    });
    await route.fulfill({ json: cards });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: artifacts.map((item) => artifactSummary(item)) });
  });
  for (const item of artifacts) {
    await page.route(`**/artifacts/${item.id}`, async (route) => {
      await route.fulfill({ json: item });
    });
  }
}

function fullTextCardArtifact(id: string, createdAt: string) {
  const fullText = {
    status: "extracted",
    pdf_url: "",
    source: "user_uploaded_pdf",
    page_count: 14,
    character_count: 50000,
    error: "",
    page_numbers: [4, 7, 9],
    section_names: ["method", "experiments", "limitations"],
  };
  const card = {
    paper_title: paper.title,
    paper_id: paper.id,
    evidence_level: "full_text",
    full_text: fullText,
    signals: {
      task: "VQA evidence faithfulness evaluation",
      method: "component-aware mitigation",
      dataset: "POPE",
      metric: "accuracy",
      baseline: "LLaVA",
      claim: "grounded intervention reduces object hallucination",
      limitation: "needs cross-model validation",
      prior_work_limitation: "existing methods suffer from object hallucination",
      contribution_type: "benchmark",
      contribution_evidence: "贡献证据：We introduce a benchmark and evaluate against LLaVA.",
      missing_signals: [],
      signal_evidence: {
        dataset: {
          field: "dataset",
          canonical_value: "POPE",
          raw_value: "POPE",
          source: "pdf.full_text",
          section: "experiments",
          page: 7,
          quote: "Experiments use Dataset: POPE.",
          confidence: "medium",
          validation_errors: [],
        },
        limitation: {
          field: "limitation",
          canonical_value: "needs cross-model validation",
          raw_value: "needs cross-model validation",
          source: "pdf.full_text",
          section: "limitations",
          page: 9,
          quote: "Our method is limited to the evaluated model families.",
          confidence: "medium",
          validation_errors: [],
        },
      },
    },
    sections: sections.map((section) => ({
      ...section,
      content: section.content.replace("第 ", "全文证据第 "),
    })),
    weakest_assumption: "The benchmark covers deployment failures.",
    minimal_reproduction: "Run POPE against LLaVA with the reported metric.",
  };
  return {
    id,
    project_id: project.id,
    title: "direction_round_1_paper_card_grounded-evidence-evaluation-for-visual-question-answering.md",
    kind: "markdown",
    content_markdown: "# Full-text Paper Card",
    content_json: JSON.stringify({ schema_version: "paper_card.v2", paper, paper_id: paper.id, card, evidence_level: "full_text", full_text: fullText }),
    diff: "+ Parsed user uploaded PDF\n+ Full-text Paper Card",
    created_at: createdAt,
    updated_at: createdAt,
  };
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
  await expect(tocItems.nth(0)).toHaveAttribute("aria-current", "true");

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

test("full-text paper detail exposes signal source section and page", async ({ page }) => {
  const fullTextArtifact = fullTextCardArtifact("artifact_e2e_located_signals", "2026-07-10T01:00:00+00:00");
  await mockReaderProject(page, [artifact, fullTextArtifact]);
  await page.goto(`/#paper-reader/${paper.id}?from=direction-review`);

  const signalPanel = page.locator('article[aria-label="paper evidence signals"]');
  await expect(signalPanel).toBeVisible();
  await expect(signalPanel.getByText("本论文自身 Limitation", { exact: true })).toBeVisible();
  await expect(signalPanel.getByText("已有研究不足", { exact: true })).toBeVisible();
  await expect(signalPanel.getByText("pdf.full_text · experiments · p.7 · 抽取置信度 medium", { exact: true })).toBeVisible();
  await expect(signalPanel.getByText("pdf.full_text · limitations · p.9 · 抽取置信度 medium", { exact: true })).toBeVisible();
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

  await page.getByRole("button", { name: "展开工作流侧栏" }).click();
  const readerStep = page.locator(".workflow-step", { hasText: "Deep Paper Card" });
  await expect(readerStep).toHaveAttribute("title", /Deep Paper Card/);
  const readerStepLayout = await readerStep.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(readerStepLayout.scrollWidth).toBeLessThanOrEqual(readerStepLayout.clientWidth + 1);
});

test("uploaded PDF immediately replaces a stale abstract card for the same paper", async ({ page }) => {
  const staleCard = {
    ...artifact,
    id: "artifact_e2e_stale_abstract_card",
    title: "paper_card_grounded-evidence-evaluation-for-visual-question-answering.md",
    content_json: JSON.stringify({
      paper,
      card: {
        paper_title: paper.title,
        paper_id: paper.id,
        evidence_level: "abstract_only",
        signals: directionPayload.papers[0].signals,
        sections,
        weakest_assumption: "Stale abstract-only card.",
        minimal_reproduction: "Status: blocked.",
      },
      evidence_level: "abstract_only",
      full_text: {
        status: "download_failed",
        pdf_url: "https://arxiv.org/pdf/fixture.pdf",
        source: "arxiv_pdf",
        page_count: 0,
        character_count: 0,
        error: "CERTIFICATE_VERIFY_FAILED",
      },
    }),
  };
  const uploadedArtifact = fullTextCardArtifact("artifact_e2e_uploaded_full_text", "2026-07-12T00:00:00+00:00");
  const uploadedPayload = JSON.parse(uploadedArtifact.content_json) as { card: object; full_text: object };
  await mockReaderProject(page, [staleCard]);
  await page.route(`**/projects/${project.id}/papers/${paper.id}/full-text`, async (route) => {
    await route.fulfill({
      json: {
        paper_id: paper.id,
        text: "full text fixture",
        evidence_level: "full_text",
        evidence_quality: "full_text",
        source: "user_uploaded_pdf",
        page_count: 14,
        char_count: 50000,
        updated_at: uploadedArtifact.updated_at,
        full_text: uploadedPayload.full_text,
        card: {
          id: "paper_card_e2e_uploaded_full_text",
          project_id: project.id,
          paper_id: paper.id,
          artifact_id: uploadedArtifact.id,
          evidence_level: "full_text",
          full_text: uploadedPayload.full_text,
          signals: (uploadedPayload.card as { signals: object }).signals,
          sections: (uploadedPayload.card as { sections: object[] }).sections,
          weakest_assumption: "The benchmark covers deployment failures.",
          minimal_reproduction: "Run POPE against LLaVA with the reported metric.",
          created_at: uploadedArtifact.created_at,
        },
        artifact: uploadedArtifact,
      },
    });
  });

  await page.goto("/#paper-reader");
  await expect(page.getByRole("heading", { name: "摘要级阅读 · Paper Card" })).toBeVisible();
  await page.locator("details.reader-supplemental-input > summary").click();
  await page.locator('.pdf-upload-control[aria-label="upload paper PDF"] input[type="file"]').setInputFiles({
    name: "fixture.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7 fixture"),
  });

  await expect(page.getByRole("heading", { name: "全文级深读 · Paper Card" })).toBeVisible();
  await expect(page.locator('.reader-evidence-level.full_text').getByText("全文已验证", { exact: true })).toBeVisible();
  const provenance = page.getByTestId("paper-card-provenance");
  await expect(provenance.getByText("已解析 14 页 / 50,000 字符", { exact: true })).toBeVisible();
  await expect(provenance.getByText("来源：用户上传 PDF", { exact: true })).toBeVisible();
  await expect(provenance.getByText(/更新时间：07\/12/)).toBeVisible();
  await expect(page.getByText("CERTIFICATE_VERIFY_FAILED")).toHaveCount(0);
  await expect(page.getByText("12/12 已生成")).toBeVisible();
});

test("refresh keeps a verified full-text direction card ahead of an old abstract review", async ({ page }) => {
  const staleReviewPayload = JSON.parse(JSON.stringify(directionPayload)) as typeof directionPayload;
  staleReviewPayload.errors = ["pdf download failed: CERTIFICATE_VERIFY_FAILED"];
  staleReviewPayload.papers[0].full_text = {
    status: "download_failed",
    pdf_url: "https://arxiv.org/pdf/fixture.pdf",
    source: "arxiv_pdf",
    page_count: 0,
    character_count: 0,
    error: "CERTIFICATE_VERIFY_FAILED",
  };
  const staleReview = { ...artifact, content_json: JSON.stringify(staleReviewPayload) };
  const staleStandalone = {
    ...artifact,
    id: "artifact_e2e_refresh_stale_abstract",
    title: "paper_card_grounded-evidence-evaluation-for-visual-question-answering.md",
    content_json: JSON.stringify({
      schema_version: "paper_card.v2",
      paper_id: paper.id,
      paper,
      card: {
        paper_title: paper.title,
        paper_id: paper.id,
        evidence_level: "abstract_only",
        signals: directionPayload.papers[0].signals,
        sections,
        weakest_assumption: "Stale abstract card.",
        minimal_reproduction: "Status: blocked.",
      },
      evidence_level: "abstract_only",
      full_text: staleReviewPayload.papers[0].full_text,
    }),
    created_at: "2026-07-10T00:00:00+00:00",
    updated_at: "2026-07-10T00:00:00+00:00",
  };
  const uploadedArtifact = fullTextCardArtifact("artifact_e2e_refresh_full_text", "2026-07-12T00:00:00+00:00");

  await mockReaderProject(page, [staleReview, staleStandalone, uploadedArtifact]);
  await page.goto("/#paper-reader");

  await expect(page.getByRole("heading", { name: "全文级深读 · Paper Card" })).toBeVisible();
  await expect(page.getByText("已解析 14 页 / 50,000 字符")).toBeVisible();
  await expect(page.getByText("来源：用户上传 PDF")).toBeVisible();
  await expect(page.locator(".workflow-latest-notice").getByText(/CERTIFICATE_VERIFY_FAILED/)).toHaveCount(0);
  await expect(page.locator(".reader-main-panel").getByText(/CERTIFICATE_VERIFY_FAILED/)).toHaveCount(0);
  await page.getByRole("button", { name: /研究轨迹/ }).click();
  const history = page.locator("details.workflow-history-notices");
  await expect(history.getByText(/历史尝试/)).toBeVisible();
  await history.locator("summary").click();
  await expect(history.getByText(/CERTIFICATE_VERIFY_FAILED/)).toBeVisible();
});

test("paper memory shows a no-reliable-hit boundary instead of invented evidence", async ({ page }) => {
  const memoryArtifact = {
    id: "artifact_e2e_no_reliable_memory",
    project_id: project.id,
    title: "research_memory_answer_object-hallucination.md",
    kind: "markdown",
    content_markdown: "# Research Memory Answer\n\nNo reliable hit.",
    content_json: JSON.stringify({
      schema_version: "research_memory_answer.v2",
      question: "如何评估对象幻觉？",
      top_k: 5,
      answer: "当前记忆没有可靠证据回答此问题。",
      hits: [],
      direction_memory: null,
      total_memories: 4,
      reliability_status: "no_reliable_hit",
      reliability_reason: "所有候选命中分数不足。",
      warnings: ["当前记忆没有可靠证据回答此问题；未把零分或弱相关论文包装成最相关命中。"],
    }),
    diff: "+ No reliable memory hit",
    created_at: "2026-07-15T00:00:00+00:00",
    updated_at: "2026-07-15T00:00:00+00:00",
  };
  await mockReaderProject(page, [artifact, memoryArtifact]);
  await page.route(`**/projects/${project.id}/research-memory/query`, async (route) => {
    await route.fulfill({
      json: {
        question: "如何评估对象幻觉？",
        top_k: 5,
        answer: "当前记忆没有可靠证据回答此问题。",
        hits: [],
        direction_memory: null,
        total_memories: 4,
        reliability_status: "no_reliable_hit",
        reliability_reason: "所有候选命中分数不足。",
        artifact: memoryArtifact,
        warnings: ["当前记忆没有可靠证据回答此问题；未把零分或弱相关论文包装成最相关命中。"],
        workflow_steps: [],
      },
    });
  });

  await page.goto("/#paper-memory");
  await page.getByLabel("用户问题").fill("如何评估对象幻觉？");
  await page.getByRole("button", { name: "检索记忆并回答" }).click();

  await expect(page.getByRole("heading", { name: "当前记忆没有可靠证据回答此问题" })).toBeVisible();
  await expect(page.getByText("所有候选命中分数不足。")).toBeVisible();
  await expect(page.locator('[aria-label="memory reliability boundary"]')).toBeVisible();
  await expect(page.locator('[aria-label="memory answer"]')).toHaveCount(0);
  await expect(page.locator('[aria-label="retrieved paper memories"] article')).toHaveCount(0);
  await page.getByRole("button", { name: "改写查询" }).click();
  await expect(page.getByLabel("用户问题")).toHaveValue(/具体研究对象、失败模式、数据集、指标与 baseline/);
  await expect(page.getByRole("button", { name: "返回 Literature Search" })).toBeVisible();
});

test("paper memory prioritizes synthesis and collapses per-paper research notes", async ({ page }) => {
  const memoryPayload = {
    schema_version: "research_memory_answer.v3",
    question: "对象幻觉在视觉证据冲突时为何恶化？",
    top_k: 3,
    answer: "结构化综合答案。",
    answer_summary: "两篇原文共同覆盖对象幻觉与视觉证据冲突，但尚不能证明结论完全一致。",
    claims: [
      {
        id: "memory-claim-1",
        statement: `${paper.title}：Object hallucination increases under conflicting visual evidence.`,
        support_status: "single_source",
        confidence: "medium",
        paper_ids: [paper.id],
        evidence_refs: [
          {
            paper_id: paper.id,
            paper_title: paper.title,
            snippet_id: "pdf-results-p7",
            source: "pdf.full_text",
            section: "results",
            page: "7",
            text: "Object hallucination increases under conflicting visual evidence.",
            confidence: "medium",
          },
        ],
      },
    ],
    unanswered_parts: ["仍缺少跨模型复现实验。"],
    hits: [
      {
        paper,
        direction: project.keyword,
        round: 1,
        score: 1.42,
        title_score: 0.42,
        keyword_score: 0.36,
        section_score: 0.49,
        priority_score: 0.15,
        snippets: ["[pdf-results-p7|pdf.full_text] Object hallucination increases under conflicting visual evidence."],
        evidence_quality: "full_text",
        evidence_refs: [],
        abstract_translation: "本文研究视觉证据冲突。",
        weakest_assumption: "视觉冲突样本能够代表真实失败。",
        minimal_reproduction: "复现视觉冲突切片。",
        counterexample: "替换视觉证据但保持答案选项不变。",
        follow_up_idea: "验证跨模型稳定性。",
        why_selected: "命中对象幻觉与视觉冲突。",
        research_sight: directionPayload.papers[0].research_sight,
        self_read_priority: true,
      },
    ],
    direction_memory: null,
    total_memories: 2,
    reliability_status: "reliable",
    reliability_reason: "命中全文证据。",
    warnings: [],
  };
  const memoryArtifact = {
    id: "artifact_e2e_memory_synthesis",
    project_id: project.id,
    title: "research_memory_answer_object-hallucination.md",
    kind: "markdown",
    content_markdown: "# Research Memory Answer",
    content_json: JSON.stringify(memoryPayload),
    diff: "+ Structured memory synthesis",
    created_at: "2026-07-17T00:00:00+00:00",
    updated_at: "2026-07-17T00:00:00+00:00",
  };
  await mockReaderProject(page, [artifact, memoryArtifact]);
  await page.goto("/#paper-memory");

  await expect(page.getByText(memoryPayload.answer_summary, { exact: true })).toBeVisible();
  await expect(page.locator('[aria-label="memory synthesized claims"]')).toContainText("results · p.7");
  await expect(page.locator('[aria-label="memory unanswered parts"]')).toContainText("仍缺少跨模型复现实验");
  const details = page.locator(".memory-hit-details").first();
  await expect(details).not.toHaveAttribute("open", "");
  await expect(page.getByText("替换视觉证据但保持答案选项不变。", { exact: true })).not.toBeVisible();
  await details.locator("summary").click();
  await expect(page.getByText("替换视觉证据但保持答案选项不变。", { exact: true })).toBeVisible();
});
