import { expect, test } from "@playwright/test";

function artifactSummary(artifact: {
  id: string;
  project_id: string;
  title: string;
  kind: string;
  content_markdown: string;
  content_json: string;
  created_at: string;
  updated_at: string;
}) {
  let json_schema_version = "";
  try {
    const payload = JSON.parse(artifact.content_json) as { schema_version?: string };
    json_schema_version = payload.schema_version ?? "";
  } catch {
    json_schema_version = "";
  }
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
    json_schema_version,
  };
}

test("shows an API offline notice instead of implying empty data", async ({ page }) => {
  await page.route("**/health", async (route) => {
    await route.abort();
  });

  await page.goto("/#paper-table");
  await expect(page.getByText("API 未连接，请先启动 ScholarFlow 后端服务。", { exact: true })).toBeVisible();
  await expect(page.getByText("当前不是“没有论文”，而是前端无法读取真实 paper table。")).toBeVisible();
});

test("empty user project paper table does not show mock or demo papers", async ({ page }) => {
  const project = {
    id: "project_e2e_empty",
    title: "空项目回归",
    description: "empty paper table regression",
    keyword: "trustworthy multimodal evaluation",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_empty",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/#paper-table");
  await expect(page.getByText("本次没有可展示论文")).toBeVisible();
  await expect(page.getByText("请先运行 Literature Search，系统不会用内置示例论文填充表格。")).toBeVisible();
  await expect(page.getByText(/Synthetic Example/)).toHaveCount(0);
});

test("new project page has no inert action buttons and saves drafts locally", async ({ page }) => {
  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/#new-project");
  await expect(page.getByRole("button", { name: /导入已有论文/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Artificial Intelligence/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Survey/ })).toHaveCount(0);

  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill("科研工作台按钮回归");
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill("trustworthy agent workflow");
  await page.getByRole("button", { name: /保存草稿/ }).click();
  await expect(page.getByText(/草稿已保存到本机浏览器 localStorage/)).toBeVisible();
  const savedDraft = await page.evaluate(() => window.localStorage.getItem("scholarflow.projectDraft"));
  expect(savedDraft).toContain("trustworthy agent workflow");
});

test("paper table CSV export downloads current real papers", async ({ page }) => {
  const project = {
    id: "project_e2e_csv",
    title: "CSV 导出回归",
    description: "csv export regression",
    keyword: "trustworthy paper export",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_csv",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_csv",
    project_id: project.id,
    title: "Trustworthy Agent Workflow Evaluation",
    authors: "C. Researcher",
    abstract: "Dataset: AgentBench. Metric: task success.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00004",
    relation: "匹配 trustworthy agent workflow。",
    priority: "High",
    code: "unknown",
    relevance_score: 1.3,
    created_at: "2026-07-02T00:00:00+00:00",
  };

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
    await route.fulfill({ json: [] });
  });

  await page.goto("/#paper-table");
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /导出 CSV/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("papers.csv");
});

test("demo project is explicit and does not pollute real project paper table", async ({ page }) => {
  const demoProject = {
    id: "local-bootstrap",
    title: "ScholarFlow Demo",
    description: "seed demo project",
    keyword: "demo",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "demo-preview",
    stage: "seed",
    active_session_id: "session_demo",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const realProject = {
    id: "project_e2e_real_no_demo",
    title: "真实用户项目",
    description: "real project should not receive demo papers",
    keyword: "grounded evidence evaluation",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_real_no_demo",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const demoPaper = {
    id: "paper_seed_demo",
    project_id: demoProject.id,
    title: "Synthetic Example: Demo Paper Should Stay Hidden",
    authors: "Demo",
    abstract: "seed paper",
    year: "2026",
    type: "Method",
    venue: "Demo",
    source: "seed",
    url: "",
    relation: "seed data",
    priority: "High",
    code: "demo",
    relevance_score: 1,
    created_at: "2026-07-02T00:00:00+00:00",
  };

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [demoProject, realProject] });
  });
  for (const project of [demoProject, realProject]) {
    await page.route(`**/projects/${project.id}/timeline`, async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
      await route.fulfill({ json: [] });
    });
  }
  await page.route(`**/projects/${demoProject.id}/papers`, async (route) => {
    await route.fulfill({ json: [demoPaper] });
  });
  await page.route(`**/projects/${realProject.id}/papers`, async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/#paper-table");
  await expect(page.getByRole("heading", { name: realProject.title })).toBeVisible();
  await expect(page.getByText(demoPaper.title, { exact: true })).toHaveCount(0);
  await page.getByLabel("项目").selectOption(demoProject.id);
  await expect(page.getByText(/Demo 项目仅用于界面预览/).first()).toBeVisible();
  await expect(page.getByText(demoPaper.title, { exact: true })).toHaveCount(0);
  await expect(page.getByText("本次没有可展示论文")).toBeVisible();
});

test("workflow shell exposes core steps without synthetic rows", async ({ page }) => {
  const project = {
    id: "project_e2e_shell",
    title: "工作台导航回归",
    description: "workflow shell smoke",
    keyword: "agent reliability",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_shell",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/");
  for (const label of ["新建项目", "Paper Table", "Direction Review", "Deep Paper Card", "Paper Memory", "Gap Board", "Experiment Plan"]) {
    await expect(page.locator(".workflow-step", { hasText: label })).toBeVisible();
  }

  await page.locator(".workflow-step", { hasText: "Paper Table" }).click();
  await expect(page.getByText("本次没有可展示论文")).toBeVisible();
  await expect(page.getByText(/Synthetic Example/)).toHaveCount(0);

  await page.locator(".workflow-step", { hasText: "Gap Board" }).click();
  await expect(page.getByText("尚未生成 Gap Board")).toBeVisible();

  await page.locator(".workflow-step", { hasText: "Experiment Plan" }).click();
  await expect(page.getByText("尚未生成实验计划")).toBeVisible();
});

test("project switch ignores stale resource responses", async ({ page }) => {
  const projectA = {
    id: "project_e2e_stale_a",
    title: "旧请求项目 A",
    description: "slow project",
    keyword: "slow retrieval",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_stale_a",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const projectB = {
    ...projectA,
    id: "project_e2e_stale_b",
    title: "当前项目 B",
    keyword: "current retrieval",
    active_session_id: "session_e2e_stale_b",
  };
  const paperA = {
    id: "paper_e2e_stale_a",
    project_id: projectA.id,
    title: "Stale Paper From Project A",
    authors: "A",
    abstract: "stale",
    year: "2026",
    type: "Method",
    venue: "arXiv",
    source: "arxiv",
    url: "",
    relation: "stale response",
    priority: "High",
    code: "unknown",
    relevance_score: 1,
    created_at: "2026-07-02T00:00:00+00:00",
  };
  const paperB = {
    ...paperA,
    id: "paper_e2e_stale_b",
    project_id: projectB.id,
    title: "Current Paper From Project B",
    relation: "current response",
  };

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [projectA, projectB] });
  });
  await page.route(`**/projects/${projectA.id}/papers`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({ json: [paperA] });
  });
  await page.route(`**/projects/${projectB.id}/papers`, async (route) => {
    await route.fulfill({ json: [paperB] });
  });
  for (const project of [projectA, projectB]) {
    await page.route(`**/projects/${project.id}/timeline`, async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
      await route.fulfill({ json: [] });
    });
  }

  await page.goto("/#paper-table");
  await page.getByLabel("项目").selectOption(projectB.id);
  await expect(page.getByText(paperB.title, { exact: true })).toBeVisible();
  await page.waitForTimeout(900);
  await expect(page.getByText(paperA.title, { exact: true })).toHaveCount(0);
});

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
  let artifactSummaryReads = 0;

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
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    artifactSummaryReads += 1;
    await route.fulfill({ json: artifacts.map(artifactSummary) });
  });
  await page.route(`**/projects/${project.id}/artifacts`, async (route) => {
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
        workflow_steps: [
          {
            step_id: "paper-table",
            status: "partial",
            label: "Paper Table",
            summary: "mocked search returned one paper with retrieval warning",
            warnings: ["mock_api_e2e: 使用 mocked API smoke，不代表真实外部检索质量。"],
            errors: [],
            artifact_refs: [
              {
                id: artifact.id,
                title: artifact.title,
                kind: artifact.kind,
                created_at: artifact.created_at,
              },
            ],
            updated_at: artifact.updated_at,
          },
        ],
      },
    });
  });
  await page.route(`**/artifacts/${artifact.id}`, async (route) => {
    await route.fulfill({ json: artifact });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /新建项目/ }).first().click();
  await expect(page).toHaveURL(/#new-project/);

  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill(project.title);
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill(project.keyword);
  await page.getByRole("button", { name: "创建项目" }).click();

  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByRole("heading", { name: /论文表格/ })).toBeVisible();
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
  await expect(page.getByText(/mock_api_e2e/).first()).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Paper Table" }).getByText("partial")).toBeVisible();
  expect(artifactSummaryReads).toBeGreaterThan(0);

  await page.reload();
  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
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
  const v2DirectionPayload = {
    ...directionPayload,
    schema_version: "direction_review.v2",
    round_read_count: 1,
    papers: directionPayload.papers.map((reading) => ({
      ...reading,
      sections: reading.card.sections,
      weakest_assumption: reading.card.weakest_assumption,
      minimal_reproduction: reading.card.minimal_reproduction,
      counterexample: reading.card.counterexample,
      follow_up_idea: reading.card.follow_up_idea,
    })),
  };
  const v2MemoryPayload = {
    ...memoryPayload,
    schema_version: "research_memory_answer.v2",
    hits: memoryPayload.hits.map((hit) => ({
      paper,
      direction: hit.memory.direction,
      round: hit.memory.round_index,
      score: hit.score,
      title_score: hit.title_score,
      keyword_score: hit.keyword_score,
      section_score: hit.section_score,
      priority_score: hit.priority_score,
      snippets: hit.snippets,
      abstract_translation: hit.memory.abstract_translation,
      weakest_assumption: hit.memory.weakest_assumption,
      minimal_reproduction: hit.memory.minimal_reproduction,
      counterexample: hit.memory.counterexample,
      follow_up_idea: hit.memory.follow_up_idea,
      why_selected: hit.memory.why_selected,
      research_sight: researchSight,
      self_read_priority: true,
    })),
  };
  const v2DirectionArtifact = {
    ...directionArtifact,
    id: "artifact_e2e_direction_shape_v2",
    content_json: JSON.stringify(v2DirectionPayload),
    diff: "+ v2 direction artifact shape",
  };
  const v2MemoryArtifact = {
    ...memoryArtifact,
    id: "artifact_e2e_memory_shape_v2",
    content_json: JSON.stringify(v2MemoryPayload),
    diff: "+ v2 memory artifact shape",
  };
  const malformedArtifact = {
    id: "artifact_e2e_malformed_card",
    project_id: project.id,
    title: "paper_card_malformed.md",
    kind: "json",
    content_markdown: "# Malformed",
    content_json: "{not valid json",
    diff: "+ malformed fixture",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  let servedArtifacts = [directionArtifact, memoryArtifact, malformedArtifact];
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
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: servedArtifacts.map(artifactSummary) });
  });
  await page.route(`**/projects/${project.id}/artifacts`, async (route) => {
    await route.fulfill({ json: servedArtifacts });
  });
  await page.route("**/artifacts/artifact_*", async (route) => {
    const artifactId = route.request().url().split("/").pop();
    const artifact = servedArtifacts.find((item) => item.id === artifactId);
    await route.fulfill({ status: artifact ? 200 : 404, json: artifact ?? { detail: "Artifact not found" } });
  });

  await page.goto("/#direction-review");
  await expect(page.getByRole("button", { name: /Artifact Shape Paper/ }).first()).toBeVisible();
  await expect(page.getByText(/Artifact JSON 解析失败/).first()).toBeVisible();
  await page.getByRole("button", { name: /Artifact Shape Paper/ }).first().click();
  await expect(page.getByText("Selected Paper Detail")).toBeVisible();
  await expect(page.getByText("Paper Signals")).toBeVisible();
  await expect(page.getByText("Research Sight")).toBeVisible();
  await expect(page.locator(".view-error-state")).toHaveCount(0);

  await page.goto("/#paper-memory");
  await expect(page.getByText("Memory-Grounded Answer")).toBeVisible();
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();

  servedArtifacts = [v2DirectionArtifact, v2MemoryArtifact, malformedArtifact];
  await page.goto("/#direction-review");
  await expect(page.getByRole("button", { name: /Artifact Shape Paper/ }).first()).toBeVisible();
  await page.getByRole("button", { name: /Artifact Shape Paper/ }).first().click();
  await expect(page.getByText("研究问题与背景")).toBeVisible();

  await page.goto("/#paper-memory");
  await expect(page.getByText("Memory-Grounded Answer")).toBeVisible();
  await expect(page.locator("dd", { hasText: "构造同答案但视觉证据冲突的样本。" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
