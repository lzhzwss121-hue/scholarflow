import { expect, test } from "@playwright/test";

test("mocked research workflow smoke keeps a created project after refresh", async ({ page }) => {
  const project = {
    id: "project_e2e_smoke",
    title: "证据忠实性评估",
    description: "E2E smoke project",
    keyword: "evidence faithfulness benchmark",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_smoke",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_evidence_faithfulness",
    project_id: project.id,
    title: "Evidence Faithfulness Benchmark for Visual Question Answering",
    authors: "A. Researcher",
    abstract: "Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv cs.CV",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00002",
    relation: "匹配关键词：evidence, faithfulness, benchmark。",
    priority: "High",
    code: "unknown",
    relevance_score: 1.4,
    created_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_paper_table",
    project_id: project.id,
    title: "paper_table_e2e.md",
    kind: "markdown",
    content_markdown: "# Paper Table\n\nEvidence Faithfulness Benchmark for Visual Question Answering",
    content_json: JSON.stringify({ query: project.keyword, papers: [paper], errors: [] }),
    diff: "+ E2E smoke paper table",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };

  let projects: typeof project[] = [];
  let papers: typeof paper[] = [];
  let artifacts: typeof artifact[] = [];
  let artifactListReads = 0;

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    if (route.request().method() === "POST") {
      projects = [project];
      await route.fulfill({ status: 201, json: project });
      return;
    }
    await route.fulfill({ json: projects });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: papers });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts`, async (route) => {
    artifactListReads += 1;
    await route.fulfill({ json: artifacts });
  });
  await page.route(`**/projects/${project.id}/literature/search`, async (route) => {
    papers = [paper];
    artifacts = [artifact];
    await route.fulfill({
      status: 201,
      json: {
        query: project.keyword,
        expanded_queries: [project.keyword],
        papers,
        artifact,
        errors: ["mock_api_e2e: 使用 mocked API smoke，不代表真实外部检索质量。"],
      },
    });
  });
  await page.route(`**/artifacts/${artifact.id}`, async (route) => {
    await route.fulfill({ json: artifact });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /新建研究项目/ }).first().click();
  await expect(page).toHaveURL(/#new-project/);

  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill(project.title);
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill(project.keyword);
  await page.getByRole("button", { name: "创建项目" }).click();

  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByRole("heading", { name: /论文表格/ })).toBeVisible();
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByText(paper.title)).toBeVisible();
  await expect(page.getByText(/mock_api_e2e/)).toBeVisible();
  expect(artifactListReads).toBeGreaterThan(0);

  await page.reload();
  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByText(paper.title)).toBeVisible();
});

test("hydrates real direction review and memory artifact shapes without blank views", async ({ page }) => {
  const project = {
    id: "project_e2e_artifact_shape",
    title: "Artifact Shape 回归",
    description: "真实 artifact hydration 回归",
    keyword: "visual grounding hallucination benchmark",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_artifact_shape",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_artifact_shape",
    project_id: project.id,
    title: "Artifact Shape Paper for Grounded Hallucination Evaluation",
    authors: "B. Researcher",
    abstract: "This paper studies visual grounding and object hallucination.",
    year: "2026",
    type: "Benchmark",
    venue: "CVPR",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00003",
    relation: "覆盖 visual grounding 与 hallucination benchmark。",
    priority: "High",
    code: "unknown",
    relevance_score: 1.5,
    created_at: "2026-07-02T00:00:00+00:00",
  };
  const evidencePack = {
    evidence_level: "abstract",
    confidence: "medium",
    snippets: [
      {
        id: "snippet_1",
        source: "abstract",
        kind: "claim",
        text: "The benchmark checks whether answers are grounded in visual evidence.",
        note: "E2E artifact shape evidence",
        confidence: "medium",
      },
    ],
    missing_evidence: ["full_pdf"],
    grounding_summary: "基于 artifact 中保存的摘要证据。",
  };
  const researchSight = {
    motivation_sharpness: "问题动机聚焦在视觉证据约束。",
    solution_elegance: "评估设计比单纯刷指标更可解释。",
    evaluation_integrity: "需要更多负样本检查。",
    paradigm_inspiration: "从答案正确性转向证据忠实性。",
    why_good: "好在把 hallucination 评价落到可检查证据上。",
    why_not_good: "脆弱点是负样本构造可能不覆盖真实失败模式。",
    better_angle: "可加入反事实视觉证据干预。",
    baseline_comparison: "应与 POPE 和 CHAIR 类指标对比。",
    next_step_proposal: "构建小规模反事实 grounding probe。",
    evidence_pack: evidencePack,
    critique_evidence: [
      {
        field: "why_good",
        evidence_snippet_id: "snippet_1",
        confidence: "medium",
        rationale: "E2E regression",
      },
    ],
  };
  const directionPayload = {
    direction: project.keyword,
    round: 1,
    review_status: "complete",
    target_paper_count: 10,
    total_read_count: 1,
    scope: {
      direction: project.keyword,
      round: 1,
      year_range: "2024-2026",
      included_scope: "视觉证据约束的 hallucination benchmark。",
      excluded_scope: "非 AI 论文。",
      subtopics: ["grounding", "hallucination"],
      queries: [project.keyword],
    },
    baseline_map: {
      direction: project.keyword,
      task_definition: "评估 VLM 答案是否忠实于视觉证据。",
      classic_baselines: [],
      recent_strong_baselines: [],
      alternative_paradigms: [],
      common_benchmarks: [],
      evaluation_risks: [],
      open_questions: [],
      generated_from: [paper.id],
      evidence_summary: "E2E artifact shape",
      curator_notes: "mocked",
    },
    papers: [
      {
        paper,
        abstract_translation: "本文研究视觉证据约束下的幻觉评估。",
        signals: {
          task: "VLM hallucination evaluation",
          method: "benchmark construction",
          dataset: "counterfactual visual grounding set",
          metric: "grounding faithfulness",
          claim: "benchmark exposes object hallucination",
          limitation: "negative samples may be narrow",
          contribution_type: "benchmark",
          missing_signals: [],
        },
        card: {
          sections: [
            {
              id: "section_1",
              title: "研究问题与背景",
              content: "它把 VLM 幻觉问题转化为证据忠实性评估。",
            },
          ],
          weakest_assumption: "负样本足以代表真实 hallucination。",
          minimal_reproduction: "用 50 个反事实样本复核 grounding faithfulness。",
          counterexample: "构造同答案但视觉证据冲突的样本。",
          follow_up_idea: "把反事实视觉证据和语言证据联合评估。",
        },
        research_sight: researchSight,
        why_selected: "它代表该方向的 benchmark 路线。",
        venue_signal: "CVPR",
        self_read_priority: true,
      },
    ],
    recommended_paper_ids: [paper.id],
    direction_summary: "本轮 artifact shape 用于验证 hydrate 兼容性。",
    errors: [],
  };
  const memoryPayload = {
    question: "如何设计反例？",
    top_k: 5,
    answer: "优先构造视觉证据冲突的反事实样本。",
    hits: [
      {
        memory: {
          id: "memory_e2e_artifact_shape",
          paper_id: paper.id,
          project_id: project.id,
          direction: project.keyword,
          round_index: 1,
          title: paper.title,
          authors: paper.authors,
          year: paper.year,
          venue: paper.venue,
          source: paper.source,
          url: paper.url,
          abstract_translation: "本文研究视觉证据约束下的幻觉评估。",
          weakest_assumption: "负样本足以代表真实 hallucination。",
          minimal_reproduction: "用 50 个反事实样本复核 grounding faithfulness。",
          counterexample: "构造同答案但视觉证据冲突的样本。",
          follow_up_idea: "把反事实视觉证据和语言证据联合评估。",
          why_selected: "它代表该方向的 benchmark 路线。",
          research_sight_json: JSON.stringify(researchSight),
          self_read_priority: 1,
          created_at: "2026-07-02T00:00:00+00:00",
        },
        score: 1.24,
        title_score: 0.4,
        keyword_score: 0.3,
        section_score: 0.34,
        priority_score: 0.2,
        snippets: ["counterexample: 构造同答案但视觉证据冲突的样本。"],
      },
    ],
    direction_memory: null,
    total_memories: 1,
    warnings: [],
  };
  const directionArtifact = {
    id: "artifact_e2e_direction_shape",
    project_id: project.id,
    title: "direction_review_round_1.md",
    kind: "markdown",
    content_markdown: "# Direction Review",
    content_json: JSON.stringify(directionPayload),
    diff: "+ real artifact shape",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const memoryArtifact = {
    id: "artifact_e2e_memory_shape",
    project_id: project.id,
    title: "research_memory_answer_counterexample.md",
    kind: "markdown",
    content_markdown: "# Memory Answer",
    content_json: JSON.stringify(memoryPayload),
    diff: "+ real memory artifact shape",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

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
  await page.route(`**/projects/${project.id}/artifacts`, async (route) => {
    await route.fulfill({ json: [directionArtifact, memoryArtifact] });
  });

  await page.goto("/#direction-review");
  await expect(page.getByRole("button", { name: /Artifact Shape Paper/ }).first()).toBeVisible();
  await page.getByRole("button", { name: /Artifact Shape Paper/ }).first().click();
  await expect(page.getByText("Selected Paper Detail")).toBeVisible();
  await expect(page.getByText("Paper Signals")).toBeVisible();
  await expect(page.getByText("Research Sight")).toBeVisible();
  await expect(page.locator(".view-error-state")).toHaveCount(0);

  await page.goto("/#paper-memory");
  await expect(page.getByText("Memory-Grounded Answer")).toBeVisible();
  await expect(page.getByText(paper.title)).toBeVisible();
  expect(pageErrors).toEqual([]);
});
