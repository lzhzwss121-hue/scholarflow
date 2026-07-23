import { expect, test, type Page } from "@playwright/test";

const project = {
  id: "project_e2e_rag_answer",
  title: "RAG Answer Regression",
  description: "Evidence-grounded answer and citation inspector.",
  keyword: "object hallucination visual grounding",
  field: "Artificial Intelligence",
  language: "zh-CN",
  workflow: "survey-to-experiment",
  stage: "paper-card",
  active_session_id: "session_e2e_rag_answer",
  created_at: "2026-07-18T00:00:00+00:00",
  updated_at: "2026-07-18T00:00:00+00:00",
};

const paper = {
  id: "paper_e2e_rag_answer",
  project_id: project.id,
  title: "Counterfactual Grounding for Object Hallucination",
  authors: "A. Researcher",
  abstract: "Counterfactual grounding binds generated objects to localized visual evidence.",
  year: "2026",
  type: "Method",
  venue: "CVPR",
  source: "arxiv",
  url: "https://arxiv.org/abs/2601.00031",
  pdf_url: "https://arxiv.org/pdf/2601.00031.pdf",
  relation: "Direct object hallucination and grounding match.",
  priority: "High",
  code: "unknown",
  relevance_score: 1.8,
  relevance_quality: "strong",
  matched_terms: ["object hallucination", "visual grounding"],
  created_at: "2026-07-18T00:00:00+00:00",
};

const citation = {
  rank: 1,
  citation_id: `${paper.id}:experiments:p.9:chunk-2`,
  paper_id: paper.id,
  paper_title: paper.title,
  paper_authors: paper.authors,
  paper_year: paper.year,
  paper_venue: paper.venue,
  paper_url: paper.url,
  chunk_id: "paper_chunk_e2e_rag_answer",
  chunk_index: 2,
  chunk_hash: "e2e-rag-answer-hash",
  source: "pdf.full_text",
  source_origin: "user_uploaded_pdf",
  evidence_level: "full_text",
  section: "experiments",
  page_start: 9,
  page_end: 9,
  text: "On POPE, counterfactual grounding reduces object hallucination rate by 12% while preserving answer accuracy.",
  lexical_score: 0.72,
  vector_score: 0.82,
  hybrid_score: 0.79,
  anchor_coverage: 0.75,
  matched_query_terms: ["object hallucination", "grounding", "对象幻觉"],
  match_strength: "strong",
  match_explanation: "强命中：覆盖 3/4 个问题锚点；关键词分 0.72，向量分 0.82，混合分 0.79；证据来自 PDF/用户全文。",
};

const artifact = {
  id: "artifact_e2e_rag_answer",
  project_id: project.id,
  title: "rag_answer_object-hallucination.md",
  kind: "markdown",
  content_markdown: "# Evidence-grounded RAG Answer",
  content_json: "{}",
  diff: "+ saved grounded RAG answer",
  created_at: "2026-07-18T00:00:00+00:00",
  updated_at: "2026-07-18T00:00:00+00:00",
};

function retrieval(hits = [citation]) {
  return {
    query: "对象幻觉如何被反事实 grounding 缓解？",
    scientific_query: "对象幻觉 反事实 grounding POPE metric",
    answer_constraints: ["只返回证据", "必须可定位"],
    requested_facets: ["dataset", "metric"],
    status: hits.length ? "complete" : "no_reliable_hit",
    retrieval_mode: "hybrid",
    provider: "local",
    embedding_model: "local/hash-embedding-v1",
    embedding_dimensions: 384,
    external_data_transfer: false,
    candidate_chunks: hits.length,
    vector_ready_chunks: hits.length,
    returned_hits: hits.length,
    top_k: 5,
    min_score: 0.18,
    query_anchor_terms: ["object hallucination", "grounding", "counterfactual"],
    rejected_by_relevance_gate: 0,
    score_explanation: "本地模式的混合分由 80% 关键词相关性与 20% hash 向量相似度组成；该分数不是正确率。",
    hits,
    warnings: [],
  };
}

function qualityAssessment(safeRefusal = false) {
  return {
    evaluation_id: safeRefusal ? "rag_eval_refusal" : "rag_eval_grounded",
    quality_status: safeRefusal ? "safe_refusal" : "strong_evidence",
    score: safeRefusal ? null : 96,
    metrics: {
      claim_traceability: 1,
      citation_integrity: 1,
      full_text_coverage: safeRefusal ? 0 : 1,
      mean_retrieval_score: safeRefusal ? 0 : 0.79,
      distinct_papers: safeRefusal ? 0 : 1,
      accepted_claims: safeRefusal ? 0 : 1,
      rejected_claims: 0,
    },
    checks: [
      {
        id: "answer_boundary",
        label: "回答边界",
        status: "pass",
        detail: safeRefusal ? "无可靠命中时保持空答案，拒答边界正确。" : "1 条主张进入最终回答。",
        remediation: "",
      },
    ],
    strengths: [
      safeRefusal
        ? "没有可靠证据时未生成答案。"
        : "所有最终主张都能定位到当前响应中的原文引用。",
    ],
    risk_flags: safeRefusal
      ? []
      : ["自动检查不能验证论文结论、因果关系或实验可复现性。"],
    human_review_required: !safeRefusal,
    disclaimer: "该分数只检查证据链，不能替代研究者阅读全文。",
    evaluated_at: "2026-07-18T00:00:00+00:00",
  };
}

async function mockWorkspace(page: Page) {
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
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });
}

test("full-text RAG renders validated claims and focuses the cited evidence", async ({ page }) => {
  await mockWorkspace(page);
  let requestBody: Record<string, unknown> = {};
  await page.route(`**/projects/${project.id}/rag-answer`, async (route) => {
    requestBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        question: "对象幻觉如何被反事实 grounding 缓解？",
        status: "complete",
        answer_kind: "grounded_synthesis",
        answer: `基于当前索引证据，可确认以下内容：\n1. POPE 上对象幻觉率降低 12%。 [${citation.citation_id}]`,
        claims: [
          {
            id: "rag-claim-1",
            statement: "POPE 上 object hallucination rate 降低 12%，同时保持回答准确率。",
            citation_ids: [citation.citation_id],
            confidence: "high",
            evidence_level: "full_text",
          },
        ],
        unanswered_parts: ["尚未覆盖跨模型复现。"],
        limitations: ["回答只覆盖本次检索返回的索引片段。"],
        retrieval: retrieval(),
        citations: [citation],
        citation_validation: {
          available_citation_ids: [citation.citation_id],
          used_citation_ids: [citation.citation_id],
          rejected_citation_ids: [],
          rejected_claim_count: 0,
        },
        generation_provider: "local",
        generation_model: "extractive-evidence-v1",
        external_data_transfer: false,
        quality_assessment: qualityAssessment(),
        artifact,
        warnings: [],
      },
    });
  });

  await page.goto("/#paper-memory");
  await page.getByLabel("原文 RAG 问题").fill("对象幻觉如何被反事实 grounding 缓解？");
  await page.getByRole("button", { name: "检索原文并回答" }).click();

  await expect(page.locator('[aria-label="evidence grounded rag answer"]')).toBeVisible();
  await expect(page.getByText("POPE 上 object hallucination rate 降低 12%")).toBeVisible();
  await expect(page.getByText("本次全部在本机处理")).toBeVisible();
  const retrievalExplanation = page.locator('[aria-label="rag retrieval explanation"]');
  await expect(retrievalExplanation).toContainText("1 候选 → 0 门槛拒绝 → 1 返回");
  await expect(retrievalExplanation).toContainText("object hallucination");
  await expect(retrievalExplanation).toContainText("实际科研检索式：对象幻觉 反事实 grounding POPE metric");
  await expect(retrievalExplanation).toContainText("数据集 / benchmark");
  await expect(retrievalExplanation).toContainText("输出约束");
  await expect(retrievalExplanation).toContainText("必须可定位");
  await expect(retrievalExplanation).toContainText("该分数不是正确率");
  await expect(page.locator('[aria-label="rag automated evidence quality"]')).toBeVisible();
  await expect(page.getByText("96.0/100")).toBeVisible();
  await expect(page.getByText(/证据链分 · 证据链较强/)).toBeVisible();
  await expect(page.getByText("证据链较强")).toBeVisible();
  await expect(page.getByText("全文覆盖").locator("..").getByText("100%")).toBeVisible();
  await expect(page.getByText("自动检查不能验证论文结论、因果关系或实验可复现性。")).toBeVisible();
  await expect(page.getByText("PDF 全文").first()).toBeVisible();
  await expect(page.getByText("p.9", { exact: true })).toBeVisible();
  await expect(page.getByText(citation.text)).toBeVisible();
  await expect(page.getByText("强命中", { exact: true })).toBeVisible();
  await page.getByText("为什么命中这段证据", { exact: true }).click();
  await expect(page.locator('[aria-label="matched query anchors"]')).toContainText("对象幻觉");
  await expect(page.getByText(citation.match_explanation, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /experiments:p.9:chunk-2/ })).toBeVisible();

  await page.getByRole("button", { name: /experiments:p.9:chunk-2/ }).click();
  await expect(page.locator(".rag-evidence-card")).toBeFocused();
  expect(requestBody.query).toBe("对象幻觉如何被反事实 grounding 缓解？");
  expect(requestBody.evidence_levels).toEqual(["abstract_only", "full_text"]);
  expect(requestBody.refresh_embeddings).toBe(true);
  await expect(page.getByLabel("原文 RAG 问题")).toHaveValue("对象幻觉如何被反事实 grounding 缓解？");
  await expect(page.getByLabel("用户问题")).toHaveValue("这个方向最值得做的一周验证实验是什么？");
  await expect(page.getByRole("button", { name: "检索记忆并回答" })).toBeVisible();
});

test("full-text RAG shows a refusal boundary when no chunk is reliable", async ({ page }) => {
  await mockWorkspace(page);
  await page.route(`**/projects/${project.id}/rag-answer`, async (route) => {
    await route.fulfill({
      json: {
        question: "不存在的火山考古问题",
        status: "no_reliable_hit",
        answer_kind: "no_answer",
        answer: "",
        claims: [],
        unanswered_parts: ["当前索引没有达到相关性阈值的原文证据，无法回答该问题。"],
        limitations: ["系统未把低相关 chunk 或零命中结果包装成科研结论。"],
        retrieval: retrieval([]),
        citations: [],
        citation_validation: {
          available_citation_ids: [],
          used_citation_ids: [],
          rejected_citation_ids: [],
          rejected_claim_count: 0,
        },
        generation_provider: "",
        generation_model: "",
        external_data_transfer: false,
        quality_assessment: qualityAssessment(true),
        artifact,
        warnings: ["没有 chunk 达到最小相关性阈值 0.18；未返回低置信度证据。"],
      },
    });
  });

  await page.goto("/#paper-memory");
  await page.getByLabel("原文 RAG 问题").fill("不存在的火山考古问题");
  await page.getByRole("button", { name: "检索原文并回答" }).click();

  await expect(page.getByRole("heading", { name: "当前原文索引无法可靠回答" })).toBeVisible();
  await expect(page.getByText("拒答通过")).toBeVisible();
  await expect(page.getByText("安全拒答")).toBeVisible();
  await expect(page.getByText("没有可靠证据时未生成答案。")).toBeVisible();
  await expect(page.locator('[aria-label="rag no reliable hit"]')).toBeVisible();
  await expect(page.locator('[aria-label="rag validated claims"]')).toHaveCount(0);
  await expect(page.locator('[aria-label="rag citation evidence"]')).toHaveCount(0);
});
