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

test("timeline failure does not erase successfully loaded papers", async ({ page }) => {
  const project = {
    id: "project_e2e_timeline_failure",
    title: "时间线局部失败回归",
    description: "partial resource hydration regression",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "literature-retrieval",
    active_session_id: "session_e2e_timeline_failure",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_timeline_failure",
    project_id: project.id,
    title: "Paper Survives Timeline Failure",
    authors: "A. Researcher",
    abstract: "A grounded VQA evidence faithfulness benchmark.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv cs.CV",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00042",
    relation: "strong evidence faithfulness match",
    priority: "High",
    code: "unknown",
    relevance_score: 1.6,
    relevance_quality: "strong",
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
    await route.fulfill({ status: 500, json: { detail: "timeline validation failed" } });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/paper-cards`, async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/#paper-table");
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
  await expect(page.getByText("本次没有可展示论文")).toHaveCount(0);
});

test("paper table uses structured relevance coverage and partial workflow status", async ({ page }) => {
  const project = {
    id: "project_e2e_relevance_coverage",
    title: "相关性覆盖回归",
    description: "structured relevance coverage regression",
    keyword: "多模态大模型在视觉问答中的证据忠实性评估",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_relevance_coverage",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_relevance_coverage",
    project_id: project.id,
    title: "Evidence Faithfulness Benchmark for Visual Question Answering",
    authors: "A. Researcher",
    abstract: "This benchmark evaluates VQA evidence faithfulness and visual grounding.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv cs.CV",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00005",
    relation: "相关性 strong：标题和摘要同时命中 visual question answering、evidence faithfulness 与 visual grounding，属于当前方向的直接评估证据，而不是仅命中 evaluation 泛词。",
    priority: "High",
    code: "unknown",
    relevance_score: 1.6,
    relevance_quality: "strong",
    matched_terms: ["visual question answering", "faithfulness", "visual grounding"],
    created_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_relevance_coverage",
    project_id: project.id,
    title: "paper_table_relevance_coverage.md",
    kind: "markdown",
    content_markdown: "# Paper Table\n\nEvidence Faithfulness Benchmark for Visual Question Answering",
    content_json: JSON.stringify({
      query: project.keyword,
      papers: [paper],
      errors: ["openalex_cooldown:mock: mocked retrieval degradation"],
      relevance_coverage: {
        candidate_count: 50,
        returned_count: 1,
        strong_match_count: 1,
        medium_match_count: 0,
        weak_match_count: 12,
        off_topic_count: 37,
        filtered_count: 49,
      },
    }),
    diff: "+ relevance coverage regression",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  let papers: typeof paper[] = [];

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: papers });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/literature/search`, async (route) => {
    papers = [paper];
    await route.fulfill({
      status: 201,
      json: {
        query: project.keyword,
        expanded_queries: [project.keyword],
        papers,
        artifact,
        errors: ["openalex_cooldown:mock: mocked retrieval degradation"],
        relevance_coverage: {
          candidate_count: 50,
          returned_count: 1,
          strong_match_count: 1,
          medium_match_count: 0,
          weak_match_count: 12,
          off_topic_count: 37,
          filtered_count: 49,
        },
        workflow_steps: [
          {
            step_id: "paper-table",
            status: "partial",
            label: "Paper Table",
            summary: "50 candidates / 1 returned / 1 strong / 0 medium / 37 off-topic filtered",
            warnings: ["openalex_cooldown:mock: mocked retrieval degradation"],
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

  await page.goto("/#paper-table");
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
  const latestNotice = page.locator(".workflow-latest-notice");
  await expect(latestNotice).toContainText("检索使用了降级、缓存或放宽后的候选");
  await expect(latestNotice).not.toContainText("openalex_cooldown");
  const warningDetails = page.locator(".table-warning-summary details");
  await expect(warningDetails.getByText("查看技术详情", { exact: true })).toBeVisible();
  await warningDetails.getByText("查看技术详情", { exact: true }).click();
  await expect(warningDetails.getByText("openalex_cooldown:mock: mocked retrieval degradation", { exact: true })).toBeVisible();
  await expect(page.locator('.metric-card[aria-label="离题已过滤：37"]')).toBeVisible();
  await expect(page.locator('.metric-card[aria-label="弱相关已过滤：12"]')).toBeVisible();
  await expect(page.getByTestId("project-saved-paper-count")).toHaveText("项目已保存 1");
  await expect(page.getByTestId("current-search-returned-count")).toHaveText("当前检索返回 1");
  await expect(page.getByTestId("current-direction-read-count")).toHaveText("当前方向已读 0");
  const relationCell = page.locator(".paper-relation-cell", { hasText: "相关性 strong" });
  await expect(relationCell.locator("p")).toHaveCSS("-webkit-line-clamp", "2");
  await relationCell.getByRole("button", { name: "展开理由" }).click();
  await expect(relationCell.locator("p")).toHaveClass(/expanded/);
  await expect(relationCell.getByRole("button", { name: "收起理由" })).toBeVisible();
  const titleLayout = await page.locator(".paper-title-cell strong").evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      wordBreak: style.wordBreak,
    };
  });
  expect(titleLayout.wordBreak).toBe("normal");
  expect(titleLayout.scrollWidth).toBeLessThanOrEqual(titleLayout.clientWidth + 1);
  await expect(page.locator(".paper-type")).toHaveCSS("white-space", "nowrap");
  const paperTableStep = page.locator(".workflow-step", { hasText: "Paper Table" });
  await expect(paperTableStep.getByText("partial")).toBeVisible();
  await expect(paperTableStep.getByText("complete")).toHaveCount(0);
});

test("degraded retrieval with no returned papers is not shown as a normal empty result", async ({ page }) => {
  const project = {
    id: "project_e2e_degraded_empty",
    title: "检索降级空结果",
    description: "degraded retrieval empty result regression",
    keyword: "多模态大模型在视觉问答中的证据忠实性评估",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_degraded_empty",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_degraded_empty",
    project_id: project.id,
    title: "paper_table_degraded_empty.md",
    kind: "markdown",
    content_markdown: "# Paper Table\n\nNo papers returned because retrieval degraded.",
    content_json: JSON.stringify({
      query: project.keyword,
      papers: [],
      errors: ["openalex:mock: degraded status=503: Service Unavailable"],
      relevance_coverage: {
        candidate_count: 37,
        returned_count: 0,
        strong_match_count: 0,
        medium_match_count: 0,
        weak_match_count: 0,
        off_topic_count: 37,
        filtered_count: 37,
      },
    }),
    diff: "+ degraded empty regression",
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
  await page.route(`**/projects/${project.id}/literature/search`, async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        query: project.keyword,
        expanded_queries: [project.keyword],
        papers: [],
        artifact,
        errors: ["openalex:mock: degraded status=503: Service Unavailable"],
        relevance_coverage: {
          candidate_count: 37,
          returned_count: 0,
          strong_match_count: 0,
          medium_match_count: 0,
          weak_match_count: 0,
          off_topic_count: 37,
          filtered_count: 37,
        },
        workflow_steps: [
          {
            step_id: "paper-table",
            status: "partial",
            label: "Paper Table",
            summary: "37 candidates / 0 returned / 37 off-topic filtered",
            warnings: ["degraded retrieval: openalex 503"],
            errors: [],
            artifact_refs: [],
            updated_at: artifact.updated_at,
          },
        ],
      },
    });
  });

  await page.goto("/#paper-table");
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByText("外部检索源 degraded retrieval")).toBeVisible();
  await expect(page.locator('.metric-card[aria-label="离题已过滤：37"]')).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Paper Table" }).getByText("partial")).toBeVisible();
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
  await expect(page.locator(".table-warning").getByText(/Demo 项目只用于预览/)).toBeVisible();
  await expect(page.getByText(demoPaper.title, { exact: true })).toHaveCount(0);
  await expect(page.getByText("本次没有可展示论文")).toBeVisible();
  await expect(page.getByRole("button", { name: /重新检索/ })).toBeDisabled();
  await page.locator(".workflow-brand").click();
  await expect(page.locator(".agent-run-panel").getByRole("button", { name: "生成计划", exact: true })).toBeDisabled();
  await expect(page.locator(".agent-run-panel").getByRole("button", { name: "确认执行", exact: true })).toBeDisabled();
});

test("agent execute refreshes timeline artifacts and keeps partial blocked workflow state", async ({ page }) => {
  const project = {
    id: "project_e2e_agent_execute",
    title: "Agent 执行闭环",
    description: "agent execute refresh regression",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "agent-loop",
    active_session_id: "session_e2e_agent_execute",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_agent_execute",
    project_id: project.id,
    title: "Evidence Faithfulness Benchmark for VQA",
    authors: "A. Researcher",
    abstract: "Dataset: POPE. Metric: accuracy. Baseline: LLaVA.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv cs.CV",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.00006",
    relation: "strong evidence faithfulness match",
    priority: "High",
    code: "unknown",
    relevance_score: 1.6,
    relevance_quality: "strong",
    created_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_agent_execute",
    project_id: project.id,
    title: "agent_run_e2e.md",
    kind: "markdown",
    content_markdown: "# Agent Run\n\npartial: experiment blocked",
    content_json: JSON.stringify({
      run_id: "run_e2e_agent_execute",
      artifact_refs: [],
    }),
    diff: "+ agent execute regression",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const planSteps = [
    {
      id: "literature",
      title: "Literature Search",
      detail: "Retrieve candidates",
      tool: "literature_search",
      status: "queued",
      metrics: {},
    },
    {
      id: "decision",
      title: "Research Decision",
      detail: "Generate gap board and experiment plan",
      tool: "research_decision",
      status: "queued",
      metrics: {},
    },
    {
      id: "save",
      title: "Save Artifact",
      detail: "Persist run result",
      tool: "save_artifact",
      status: "queued",
      metrics: {},
    },
  ];
  let runState: "planned" | "running" | "partial" = "planned";
  let statusPolls = 0;

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: runState === "partial" ? [paper] : [] });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({
      json: runState !== "planned"
        ? [
            {
              id: "event_e2e_agent_execute",
              session_id: project.active_session_id,
              time_label: "Now",
              tool: runState === "running" ? "literature_search" : "agent.execute",
              status: runState === "running" ? "running" : "done",
              summary: runState === "running" ? "正在执行 literature_search。" : "Agent Run partial: experiment blocked.",
              created_at: artifact.updated_at,
            },
          ]
        : [],
    });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: runState === "partial" ? [artifactSummary(artifact)] : [] });
  });
  await page.route(`**/artifacts/${artifact.id}`, async (route) => {
    await route.fulfill({ json: artifact });
  });
  await page.route("**/agent/plan", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        run_id: "run_e2e_agent_execute",
        project_id: project.id,
        session_id: project.active_session_id,
        task: "Run the evidence faithfulness workflow",
        provider: "local:heuristic-planner",
        status: "planned",
        rationale: "Run real tools first.",
        steps: planSteps,
        artifact,
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_execute/execute", async (route) => {
    runState = "running";
    await route.fulfill({
      status: 200,
      json: {
        run_id: "run_e2e_agent_execute",
        status: "running",
        artifact: null,
        papers: [],
        paper_count: 0,
        summary_metrics: {},
        run_status_summary: "running: literature_search.",
        warnings: [],
        artifact_refs: [],
        workflow_steps: [],
        current_tool: "literature_search",
        updated_at: artifact.updated_at,
        steps: planSteps.map((step, index) => ({
          ...step,
          status: index === 0 ? "running" : "queued",
        })),
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_execute", async (route) => {
    statusPolls += 1;
    if (statusPolls >= 2) {
      runState = "partial";
    }
    const isFinal = runState === "partial";
    await route.fulfill({
      status: 200,
      json: {
        run_id: "run_e2e_agent_execute",
        status: isFinal ? "partial" : "running",
        artifact: isFinal ? artifact : null,
        paper_count: isFinal ? 1 : 0,
        summary_metrics: isFinal ? { paper_count: 1, warning_count: 2 } : {},
        run_status_summary: isFinal ? "partial: 2 warning(s); latest artifact count=1." : "running: literature_search.",
        current_tool: isFinal ? "" : "literature_search",
        warnings: isFinal
          ? ["Direction Review partial: relevant_read_count=1.", "Experiment Plan blocked: missing reproducible anchor."]
          : [],
        artifact_refs: isFinal
          ? [
              {
                id: artifact.id,
                title: artifact.title,
                kind: artifact.kind,
                created_at: artifact.created_at,
              },
            ]
          : [],
        workflow_steps: isFinal
          ? [
              {
                step_id: "gap-board",
                status: "partial",
                label: "Gap Board",
                summary: "partial: gap evidence=1",
                warnings: ["只有 1 篇论文提供可定位限制证据，尚未形成跨论文一致失败模式。"],
                errors: [],
                artifact_refs: [],
                updated_at: artifact.updated_at,
              },
              {
                step_id: "experiment-planner",
                status: "blocked",
                label: "Experiment Plan",
                summary: "缺少可复现实验 anchor。",
                warnings: ["Experiment Plan blocked: missing reproducible anchor."],
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
            ]
          : [],
        updated_at: artifact.updated_at,
        steps: planSteps.map((step, index) => ({
          ...step,
          status: isFinal ? "done" : index === 0 ? "running" : "queued",
          metrics: isFinal && step.tool === "research_decision" ? { experiment_status: "blocked", warning_count: 1 } : {},
        })),
      },
    });
  });

  await page.goto("/#dashboard");
  const agentPanel = page.locator(".agent-run-panel");
  await expect(agentPanel.getByRole("button", { name: "生成计划", exact: true })).toBeEnabled();
  await agentPanel.getByRole("button", { name: "生成计划", exact: true }).click();
  await expect(page.getByText("Run run_e2e_agent_execute")).toBeVisible();
  await expect(agentPanel.getByRole("button", { name: "确认执行", exact: true })).toBeEnabled();
  await agentPanel.getByRole("button", { name: "确认执行", exact: true }).click();

  await expect(agentPanel.getByText("running: literature_search.")).toBeVisible();
  await expect(agentPanel.getByTestId("agent-run-current-tool")).toContainText("当前工具：literature_search");
  await page.getByRole("button", { name: /研究轨迹/ }).click();
  await expect(page.getByTestId("workflow-timeline")).toContainText("literature_search");
  await expect(agentPanel.getByText("partial: 2 warning(s); latest artifact count=1.")).toBeVisible({ timeout: 5000 });
  await expect(page.locator(".workflow-artifact-list").getByText("agent_run_e2e.md")).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Gap Board" }).locator(".workflow-status.partial")).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Experiment Plan" }).locator(".workflow-status.blocked")).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Experiment Plan" }).getByText("complete")).toHaveCount(0);
});

test("agent execute displays completed_with_warnings distinctly", async ({ page }) => {
  const project = {
    id: "project_e2e_agent_warnings",
    title: "Agent Warnings",
    description: "warning status regression",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "agent-loop",
    active_session_id: "session_e2e_agent_warnings",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_agent_warnings",
    project_id: project.id,
    title: "agent_run_warnings.md",
    kind: "markdown",
    content_markdown: "# Agent Run\n\ncompleted_with_warnings",
    content_json: JSON.stringify({ run_id: "run_e2e_agent_warnings" }),
    diff: "+ warning regression",
    created_at: project.created_at,
    updated_at: project.updated_at,
  };
  const steps = [
    {
      id: "literature",
      title: "Literature Search",
      detail: "Retrieve candidates",
      tool: "literature_search",
      status: "queued",
      metrics: {},
    },
  ];

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
    await route.fulfill({
      json: [
        {
          id: "event_e2e_agent_warnings",
          session_id: project.active_session_id,
          time_label: "Now",
          tool: "agent.execute",
          status: "partial",
          summary: "completed_with_warnings: degraded retrieval.",
          created_at: project.updated_at,
        },
      ],
    });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [artifactSummary(artifact)] });
  });
  await page.route(`**/artifacts/${artifact.id}`, async (route) => {
    await route.fulfill({ json: artifact });
  });
  await page.route("**/agent/plan", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        run_id: "run_e2e_agent_warnings",
        project_id: project.id,
        session_id: project.active_session_id,
        task: "Run workflow",
        provider: "local",
        status: "planned",
        rationale: "Run real tools.",
        steps,
        artifact,
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_warnings/execute", async (route) => {
    await route.fulfill({
      json: {
        run_id: "run_e2e_agent_warnings",
        status: "completed_with_warnings",
        artifact,
        papers: [],
        paper_count: 0,
        summary_metrics: { warning_count: 1 },
        run_status_summary: "completed_with_warnings: 1 warning(s); latest artifact count=1.",
        warnings: ["degraded retrieval: OpenAlex timeout"],
        artifact_refs: [{ id: artifact.id, title: artifact.title, kind: artifact.kind, created_at: artifact.created_at }],
        workflow_steps: [],
        updated_at: project.updated_at,
        steps: steps.map((step) => ({ ...step, status: "done", metrics: { warning_count: 1 } })),
      },
    });
  });

  await page.goto("/#dashboard");
  const agentPanel = page.locator(".agent-run-panel");
  await agentPanel.getByRole("button", { name: "生成计划", exact: true }).click();
  await agentPanel.getByRole("button", { name: "确认执行", exact: true }).click();
  await expect(agentPanel.locator(".run-status.completed_with_warnings")).toBeVisible();
  await expect(agentPanel.getByText("degraded retrieval: OpenAlex timeout")).toBeVisible();
  await expect(agentPanel.locator(".run-status.complete")).toHaveCount(0);
});

test("agent execute can be cancelled from the run panel", async ({ page }) => {
  const project = {
    id: "project_e2e_agent_cancel",
    title: "Agent Cancel",
    description: "cancel regression",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "agent-loop",
    active_session_id: "session_e2e_agent_cancel",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const artifact = {
    id: "artifact_e2e_agent_cancel_plan",
    project_id: project.id,
    title: "agent_plan_cancel.md",
    kind: "markdown",
    content_markdown: "# Plan",
    content_json: "{}",
    diff: "+ cancel regression",
    created_at: project.created_at,
    updated_at: project.updated_at,
  };
  const steps = [
    {
      id: "literature",
      title: "Literature Search",
      detail: "Retrieve candidates",
      tool: "literature_search",
      status: "queued",
      metrics: {},
    },
    {
      id: "decision",
      title: "Research Decision",
      detail: "Generate decision",
      tool: "research_decision",
      status: "queued",
      metrics: {},
    },
  ];
  let cancelled = false;

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
    await route.fulfill({
      json: cancelled
        ? [
            {
              id: "event_e2e_agent_cancel",
              session_id: project.active_session_id,
              time_label: "Now",
              tool: "agent.cancel",
              status: "cancelled",
              summary: "已请求取消 Agent Run。",
              created_at: project.updated_at,
            },
          ]
        : [],
    });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/agent/plan", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        run_id: "run_e2e_agent_cancel",
        project_id: project.id,
        session_id: project.active_session_id,
        task: "Run workflow",
        provider: "local",
        status: "planned",
        rationale: "Run real tools.",
        steps,
        artifact,
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_cancel/execute", async (route) => {
    await route.fulfill({
      json: {
        run_id: "run_e2e_agent_cancel",
        status: "running",
        artifact: null,
        papers: [],
        paper_count: 0,
        summary_metrics: {},
        run_status_summary: "running: literature_search.",
        warnings: [],
        artifact_refs: [],
        workflow_steps: [],
        current_tool: "literature_search",
        updated_at: project.updated_at,
        steps: steps.map((step, index) => ({ ...step, status: index === 0 ? "running" : "queued" })),
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_cancel/cancel", async (route) => {
    cancelled = true;
    await route.fulfill({
      json: {
        run_id: "run_e2e_agent_cancel",
        status: "cancelled",
        artifact: null,
        paper_count: 0,
        summary_metrics: {},
        run_status_summary: "cancelled: stopped before the next tool step.",
        current_tool: "",
        warnings: ["Agent Run cancelled by user request."],
        artifact_refs: [],
        workflow_steps: [],
        updated_at: project.updated_at,
        steps: steps.map((step) => ({ ...step, status: "cancelled" })),
      },
    });
  });
  await page.route("**/agent/runs/run_e2e_agent_cancel", async (route) => {
    await route.fulfill({
      json: {
        run_id: "run_e2e_agent_cancel",
        status: cancelled ? "cancelled" : "running",
        artifact: null,
        paper_count: 0,
        summary_metrics: {},
        run_status_summary: cancelled ? "cancelled: stopped before the next tool step." : "running: literature_search.",
        current_tool: cancelled ? "" : "literature_search",
        warnings: cancelled ? ["Agent Run cancelled by user request."] : [],
        artifact_refs: [],
        workflow_steps: [],
        updated_at: project.updated_at,
        steps: steps.map((step, index) => ({ ...step, status: cancelled ? "cancelled" : index === 0 ? "running" : "queued" })),
      },
    });
  });

  await page.goto("/#dashboard");
  const agentPanel = page.locator(".agent-run-panel");
  await agentPanel.getByRole("button", { name: "生成计划", exact: true }).click();
  await agentPanel.getByRole("button", { name: "确认执行", exact: true }).click();
  await expect(agentPanel.getByRole("button", { name: "取消运行", exact: true })).toBeEnabled();
  await agentPanel.getByRole("button", { name: "取消运行", exact: true }).click();
  await expect(agentPanel.locator(".run-status.cancelled")).toBeVisible();
  await expect(agentPanel.getByText("Agent Run cancelled by user request.")).toBeVisible();
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

test("project switch clears project-specific retrieval state", async ({ page }) => {
  const projectA = {
    id: "project_e2e_retrieval_state_a",
    title: "检索状态项目 A",
    description: "project-specific retrieval state",
    keyword: "object hallucination evaluation",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_retrieval_state_a",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-03T00:00:00+00:00",
  };
  const projectB = {
    ...projectA,
    id: "project_e2e_retrieval_state_b",
    title: "空白项目 B",
    keyword: "unsearched direction",
    active_session_id: "session_e2e_retrieval_state_b",
    created_at: "2026-07-01T00:00:00+00:00",
    updated_at: "2026-07-01T00:00:00+00:00",
  };
  const paper = {
    id: "paper_e2e_retrieval_state_a",
    project_id: projectA.id,
    title: "Object Hallucination Evaluation Benchmark",
    authors: "A. Researcher",
    abstract: "A direct object hallucination evaluation benchmark.",
    year: "2026",
    type: "Benchmark",
    venue: "arXiv cs.CV",
    source: "arxiv",
    url: "",
    relation: "direct object hallucination match",
    priority: "High",
    code: "unknown",
    relevance_score: 1.5,
    relevance_quality: "strong",
    matched_terms: ["object hallucination", "evaluation"],
    created_at: projectA.created_at,
  };
  const artifact = {
    id: "artifact_e2e_retrieval_state_a",
    project_id: projectA.id,
    title: "paper_table_retrieval_state.md",
    kind: "markdown",
    content_markdown: "# Paper Table",
    content_json: JSON.stringify({ papers: [paper] }),
    diff: "+ retrieval state",
    created_at: projectA.created_at,
    updated_at: projectA.updated_at,
  };
  let projectAPapers: typeof paper[] = [];
  const projectWarning = "openalex_cooldown:mock: project A degraded retrieval";

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [projectA, projectB] });
  });
  await page.route(`**/projects/${projectA.id}/papers`, async (route) => {
    await route.fulfill({ json: projectAPapers });
  });
  await page.route(`**/projects/${projectB.id}/papers`, async (route) => {
    await route.fulfill({ json: [] });
  });
  for (const project of [projectA, projectB]) {
    await page.route(`**/projects/${project.id}/timeline`, async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
      await route.fulfill({ json: [] });
    });
  }
  await page.route(`**/projects/${projectA.id}/literature/search`, async (route) => {
    projectAPapers = [paper];
    await route.fulfill({
      status: 201,
      json: {
        query: projectA.keyword,
        expanded_queries: [projectA.keyword],
        papers: projectAPapers,
        artifact,
        errors: [projectWarning],
        relevance_coverage: {
          candidate_count: 20,
          returned_count: 1,
          strong_match_count: 1,
          medium_match_count: 0,
          weak_match_count: 4,
          off_topic_count: 15,
          filtered_count: 19,
        },
        workflow_steps: [
          {
            step_id: "paper-table",
            status: "partial",
            label: "Paper Table",
            summary: "20 candidates / 1 returned",
            warnings: [projectWarning],
            errors: [],
            artifact_refs: [],
            updated_at: artifact.updated_at,
          },
        ],
      },
    });
  });

  await page.goto("/#paper-table");
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByTestId("current-search-returned-count")).toHaveText("当前检索返回 1");
  const projectWarningPanel = page.locator(".table-warning-summary");
  await projectWarningPanel.getByText("查看技术详情", { exact: true }).click();
  await expect(projectWarningPanel.getByText(projectWarning, { exact: true })).toBeVisible();

  await page.getByLabel("项目").selectOption(projectB.id);
  await expect(page.getByTestId("project-saved-paper-count")).toHaveText("项目已保存 0");
  await expect(page.getByTestId("current-search-returned-count")).toHaveText("当前检索返回 0");
  await expect(page.getByText(projectWarning, { exact: true })).toHaveCount(0);
  await expect(page.getByText("本次没有可展示论文")).toBeVisible();
});

test("created Chinese research workflow keeps uploaded full text after refresh and refuses unreliable memory", async ({ page }) => {
  const project = {
    id: "project_e2e_smoke",
    title: "证据忠实性评估",
    description: "E2E smoke project",
    keyword: "多模态大模型对象幻觉评估",
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
    relevance_quality: "strong",
    matched_terms: ["object hallucination", "POPE", "evaluation"],
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
  const readingSections = Array.from({ length: 12 }, (_, index) => ({
    id: `smoke_section_${index + 1}`,
    title: index === 0 ? "研究问题与背景" : `Section ${index + 1}`,
    content: `摘要级阅读提纲 ${index + 1}。证据缺口：需要 PDF 核验。`,
  }));
  const abstractFullText = {
    status: "download_failed",
    pdf_url: "https://arxiv.org/pdf/2601.00002",
    source: "arxiv_pdf",
    page_count: 0,
    character_count: 0,
    error: "certificate verify failed",
    failure_stage: "download",
    recovery_hint: "上传本地 PDF。",
  };
  const signals = {
    task: "visual object hallucination evaluation",
    method: "benchmark evaluation",
    dataset: "POPE",
    metric: "accuracy",
    baseline: "LLaVA",
    claim: "the benchmark exposes object hallucination",
    limitation: "abstract does not report all failure cases",
    contribution_type: "benchmark",
    missing_signals: ["full-text ablation"],
  };
  const researchSight = {
    motivation_sharpness: "摘要支持该任务与对象幻觉评估直接相关。",
    solution_elegance: "摘要证据不足，无法判断。",
    evaluation_integrity: "需要 PDF 核验完整实验设置。",
    paradigm_inspiration: "摘要证据不足，无法判断。",
    why_good: "摘要明确提出对象幻觉评估任务。",
    why_not_good: "摘要未提供完整失败样本。",
    better_angle: "摘要证据不足，无法判断。",
    baseline_comparison: "摘要提及 LLaVA。",
    next_step_proposal: "先核验 PDF 中的 POPE 设置。",
    evidence_pack: {
      evidence_level: "abstract_only",
      confidence: "medium",
      snippets: [],
      missing_evidence: ["full_pdf"],
      grounding_summary: "Only title and abstract are available.",
    },
    critique_evidence: [],
  };
  const directionReading = {
    paper,
    paper_id: paper.id,
    paper_title: paper.title,
    abstract_translation: "本文评估视觉问答中的对象幻觉。",
    evidence_level: "abstract_only",
    full_text: abstractFullText,
    signals,
    sections: readingSections,
    research_sight: researchSight,
    weakest_assumption: "摘要未提供足够证据，无法判断。",
    minimal_reproduction: "Status: blocked; missing full-text evidence.",
    counterexample: "摘要未提供足够证据，无法判断。",
    follow_up_idea: "摘要未提供足够证据，无法判断。",
    why_selected: "匹配 object hallucination、POPE 与 evaluation。",
    venue_signal: "arXiv cs.CV",
    self_read_priority: true,
  };
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
    direction_summary: "当前只有 1 篇直接相关摘要级论文，因此保持 partial。",
    artifact_refs: [] as Array<{ id: string; title: string; kind: string; created_at: string }>,
    errors: ["pdf download failed: certificate verify failed"],
    papers: [directionReading],
    workflow_steps: [],
  };
  const directionArtifact = {
    id: "artifact_e2e_direction_review",
    project_id: project.id,
    title: "direction_review_round_1.md",
    kind: "markdown",
    content_markdown: "# Direction Review\n\npartial 1/10",
    content_json: "",
    diff: "+ direction review",
    created_at: "2026-07-03T00:00:00+00:00",
    updated_at: "2026-07-03T00:00:00+00:00",
  };
  directionPayload.artifact_refs = [
    {
      id: directionArtifact.id,
      title: directionArtifact.title,
      kind: directionArtifact.kind,
      created_at: directionArtifact.created_at,
    },
  ];
  directionArtifact.content_json = JSON.stringify(directionPayload);
  const uploadedFullText = {
    status: "extracted",
    pdf_url: "",
    source: "user_uploaded_pdf",
    page_count: 2,
    character_count: 3200,
    error: "",
    failure_stage: "",
    recovery_hint: "",
  };
  const uploadedCard = {
    id: "paper_card_e2e_workflow_full_text",
    project_id: project.id,
    paper_id: paper.id,
    paper_title: paper.title,
    artifact_id: "artifact_e2e_workflow_full_text",
    source_artifact_title: "paper_card_object-hallucination-full-text.md",
    card_source: "paper_table",
    evidence_level: "full_text",
    full_text: uploadedFullText,
    signals: { ...signals, missing_signals: [] },
    sections: readingSections.map((section) => ({ ...section, content: `全文核验内容：${section.content}` })),
    weakest_assumption: "POPE coverage may not represent deployment failures.",
    minimal_reproduction: "Run POPE accuracy against LLaVA.",
    created_at: "2026-07-04T00:00:00+00:00",
    updated_at: "2026-07-04T00:00:00+00:00",
  };
  const fullTextArtifact = {
    id: "artifact_e2e_workflow_full_text",
    project_id: project.id,
    title: "paper_card_object-hallucination-full-text.md",
    kind: "markdown",
    content_markdown: "# Full-text Paper Card",
    content_json: JSON.stringify({
      schema_version: "paper_card.v2",
      paper,
      paper_id: paper.id,
      evidence_level: "full_text",
      full_text: uploadedFullText,
      card: uploadedCard,
    }),
    diff: "+ verified full text",
    created_at: uploadedCard.created_at,
    updated_at: uploadedCard.updated_at,
  };
  const memoryArtifact = {
    id: "artifact_e2e_workflow_no_memory_hit",
    project_id: project.id,
    title: "research_memory_answer_no_reliable_hit.md",
    kind: "markdown",
    content_markdown: "# Memory\n\nNo reliable hit",
    content_json: JSON.stringify({
      schema_version: "research_memory_answer.v2",
      question: "医学幻觉如何评估？",
      top_k: 5,
      answer: "当前记忆没有可靠证据回答此问题。",
      hits: [],
      direction_memory: null,
      total_memories: 1,
      reliability_status: "no_reliable_hit",
      reliability_reason: "当前对象幻觉记忆不支持医学幻觉问题。",
      warnings: ["当前记忆没有可靠证据回答此问题。"],
    }),
    diff: "+ no reliable hit",
    created_at: "2026-07-05T00:00:00+00:00",
    updated_at: "2026-07-05T00:00:00+00:00",
  };

  let projects: typeof project[] = [];
  let papers: typeof paper[] = [];
  let artifacts: typeof artifact[] = [];
  let paperCards: typeof uploadedCard[] = [];
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
  await page.route(`**/projects/${project.id}/paper-cards`, async (route) => {
    await route.fulfill({ json: paperCards });
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
  let directionRunStarted = false;
  await page.route(`**/projects/${project.id}/direction-review-runs**`, async (route) => {
    const requestUrl = new URL(route.request().url());
    const isLatest = requestUrl.pathname.endsWith("/latest");
    if (isLatest && !directionRunStarted) {
      await route.fulfill({ json: null });
      return;
    }
    if (route.request().method() === "POST") {
      directionRunStarted = true;
      await route.fulfill({
        status: 202,
        json: {
          run_id: "direction_run_e2e",
          project_id: project.id,
          direction: project.keyword,
          round: 1,
          status: "running",
          stage: "retrieving",
          progress: 20,
          message: "正在从 arXiv 与 OpenAlex 检索候选。",
          notices: [],
          result: null,
          created_at: directionArtifact.created_at,
          updated_at: directionArtifact.updated_at,
          completed_at: null,
        },
      });
      return;
    }
    artifacts = [artifact, directionArtifact];
    await route.fulfill({
      json: {
        run_id: "direction_run_e2e",
        project_id: project.id,
        direction: project.keyword,
        round: 1,
        status: "partial",
        stage: "completed",
        progress: 100,
        message: "Direction Review 部分完成：可靠阅读 1/10 篇。",
        notices: [
          {
            severity: "warning",
            code: "direction_review_partial",
            stage: "completed",
            message: "Direction Review 仅部分完成，后续决策必须保留证据不足边界。",
            occurred_at: directionArtifact.updated_at,
          },
        ],
        result: directionPayload,
        created_at: directionArtifact.created_at,
        updated_at: directionArtifact.updated_at,
        completed_at: directionArtifact.updated_at,
      },
    });
  });
  await page.route(`**/projects/${project.id}/papers/${paper.id}/full-text`, async (route) => {
    paperCards = [uploadedCard];
    artifacts = [artifact, directionArtifact, fullTextArtifact];
    await route.fulfill({
      status: 201,
      json: {
        paper_id: paper.id,
        text: "verified full text fixture",
        evidence_level: "full_text",
        evidence_quality: "full_text",
        source: "user_uploaded_pdf",
        page_count: uploadedFullText.page_count,
        char_count: uploadedFullText.character_count,
        updated_at: uploadedCard.updated_at,
        full_text: uploadedFullText,
        card: uploadedCard,
        artifact: fullTextArtifact,
      },
    });
  });
  await page.route(`**/projects/${project.id}/research-memory/query`, async (route) => {
    artifacts = [artifact, directionArtifact, fullTextArtifact, memoryArtifact];
    await route.fulfill({
      status: 201,
      json: {
        question: "医学幻觉如何评估？",
        top_k: 5,
        answer: "当前记忆没有可靠证据回答此问题。",
        hits: [],
        direction_memory: null,
        total_memories: 1,
        reliability_status: "no_reliable_hit",
        reliability_reason: "当前对象幻觉记忆不支持医学幻觉问题。",
        artifact: memoryArtifact,
        warnings: ["当前记忆没有可靠证据回答此问题。"],
        workflow_steps: [],
      },
    });
  });
  await page.route("**/artifacts/*", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (!pathname.startsWith("/artifacts/")) {
      await route.fallback();
      return;
    }
    const artifactId = decodeURIComponent(pathname.split("/").pop() ?? "");
    const item = artifacts.find((candidate) => candidate.id === artifactId);
    if (!item) {
      await route.fulfill({ status: 404, json: { detail: "artifact not found" } });
      return;
    }
    await route.fulfill({ json: item });
  });

  await page.goto("/");
  await page.locator(".workflow-header").getByRole("button", { name: /新建项目/ }).click();
  await expect(page).toHaveURL(/#new-project/);

  await page.getByPlaceholder("例如：多模态大模型在视觉问答证据真实性研究").fill(project.title);
  await page.getByPlaceholder("输入关键词，多个关键词请用英文逗号分隔").fill(project.keyword);
  await page.getByRole("button", { name: "创建项目" }).click();

  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByRole("heading", { name: /论文表格/ })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "论文检索关键词" })).toBeVisible();
  await page.getByRole("button", { name: /重新检索/ }).click();
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: paper.title, exact: true })).toHaveAttribute("href", paper.url);
  await expect(page.getByRole("link", { name: `打开论文来源：${paper.title}` })).toHaveAttribute("href", paper.url);
  const technicalDetails = page.locator(".table-warning-summary .research-warning-details");
  await technicalDetails.locator("summary").click();
  await expect(technicalDetails.getByText(/mock_api_e2e/)).toBeVisible();
  await expect(page.locator(".workflow-step", { hasText: "Paper Table" }).getByText("partial")).toBeVisible();
  expect(artifactSummaryReads).toBeGreaterThan(0);

  await page.reload();
  await expect(page).toHaveURL(/#paper-table/);
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "进入 Direction Review" }).click();
  await expect(page).toHaveURL(/#direction-review/);
  await page.getByRole("button", { name: "生成第 1 轮" }).click();
  await expect(page.getByRole("heading", { name: project.keyword })).toBeVisible();
  await expect(page.locator('[aria-label="direction review server progress"]')).toContainText("后端真实进度");
  await expect(page.locator('[aria-label="direction review server progress"]')).toContainText("100%");
  await expect(
    page
      .locator('[aria-label="direction review server progress"]')
      .getByText("Direction Review 仅部分完成，后续决策必须保留证据不足边界。"),
  ).toBeVisible();
  await expect(page.locator('[aria-label="direction review metrics"]')).toContainText("1/10");

  await page.getByRole("button", { name: `打开 Paper Card：${paper.title}`, exact: true }).click();
  await expect(page).toHaveURL(/#paper-reader\//);
  await expect(page.getByRole("heading", { name: paper.title })).toBeVisible();
  await page.locator('.pdf-upload-control[aria-label="upload paper PDF"] input[type="file"]').setInputFiles({
    name: "object-hallucination.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7 workflow fixture"),
  });
  await expect(page.locator('.reader-evidence-level.full_text').getByText("全文已验证", { exact: true })).toBeVisible();
  await expect(page.getByText("已解析 2 页 / 3,200 字符", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.locator('.reader-evidence-level.full_text').getByText("全文已验证", { exact: true })).toBeVisible();

  await page.locator(".workflow-step", { hasText: "Paper Memory" }).click();
  await page.getByLabel("用户问题").fill("医学幻觉如何评估？");
  await page.getByRole("button", { name: "检索记忆并回答" }).click();
  await expect(page.getByRole("heading", { name: "当前记忆没有可靠证据回答此问题" })).toBeVisible();
  await expect(page.getByText("当前对象幻觉记忆不支持医学幻觉问题。")).toBeVisible();
  await expect(page.locator('[aria-label="memory answer"]')).toHaveCount(0);
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
  const twelveSections = Array.from({ length: 12 }, (_, index) => ({
    id: `section_${index + 1}`,
    title: index === 0 ? "研究问题与背景" : `Section ${index + 1}`,
    content:
      index === 0
        ? "它把 VLM 幻觉问题转化为证据忠实性评估。证据边界：摘要级证据，不是全文结论。"
        : `摘要级阅读提纲 ${index + 1}：需要 PDF 正文进一步核验。`,
  }));
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
      classic_baselines: [
        {
          title: "POPE",
          year: "2023",
          venue: "CVPR",
          source: "paper",
          url: "",
          category: "benchmark",
          reason: "object hallucination baseline",
          strengths: "simple negative probing",
          risks: "limited failure modes",
          evidence_snippets: [],
          confidence: "medium",
          evidence_gap: "needs full paper check",
          comparison_role: "diagnostic_evaluator",
          actionability_status: "blocked",
          next_action: "先补齐可定位的 PDF 全文；未补齐前不进入主结果表。",
          experiment_anchor: {
            dataset: "COCO",
            metric: "POPE accuracy",
            evidence_level: "abstract_only",
          },
          verification: {
            evidence_level: "abstract_only",
            selection_basis: "abstract_topic_evidence",
            citation_status: "not_checked",
            citation_note: "尚未运行引用图验证。",
            code_status: "link_present",
            code_url: "https://github.com/example/pope",
            code_source: "metadata.code",
            reproduction_status: "blocked",
            checks: {
              full_text: "missing",
              method: "ready",
              dataset: "ready",
              metric: "ready",
              baseline: "ready",
              code: "ready",
            },
            missing_evidence: ["可定位的 PDF 全文"],
            summary: "复现仍被 PDF 全文阻塞。",
          },
        },
        {
          title: "POPE",
          year: "2023",
          venue: "CVPR",
          source: "paper",
          url: "",
          category: "benchmark",
          reason: "duplicate-title regression",
          strengths: "same title should not duplicate React key",
          risks: "console warning",
          evidence_snippets: [],
          confidence: "medium",
          evidence_gap: "needs full paper check",
        },
      ],
      recent_strong_baselines: [],
      alternative_paradigms: [],
      common_benchmarks: [],
      evaluation_risks: [],
      open_questions: [],
      action_plan: ["当前没有 reproduction-ready baseline；实验计划应保持 blocked/partial。"],
      generated_from: [paper.id],
      evidence_summary: "E2E artifact shape",
      curator_notes: "mocked",
    },
    papers: [
      {
        paper,
        abstract_translation: "本文研究视觉证据约束下的幻觉评估。",
        evidence_level: "abstract_only",
        signals: {
          task: "VLM hallucination evaluation",
          method: "benchmark construction",
          dataset: "counterfactual visual grounding set",
          metric: "grounding faithfulness",
          baseline: "LLaVA and POPE-style hallucination baseline",
          claim: "benchmark exposes object hallucination",
          limitation: "negative samples may be narrow",
          contribution_type: "benchmark",
          missing_signals: [],
        },
        card: {
          evidence_level: "abstract_only",
          sections: twelveSections,
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
  const consoleWarnings: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "warning" || message.type() === "error") {
      consoleWarnings.push(message.text());
    }
  });

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
  await page.locator(".direction-evidence-details > summary").click();
  const verifiedBaseline = page.getByTestId("baseline-reference-benchmark-0");
  await expect(verifiedBaseline.locator(".baseline-action-row").getByText("阻塞", { exact: true })).toBeVisible();
  await expect(verifiedBaseline).toContainText("diagnostic_evaluator");
  await expect(verifiedBaseline).toContainText("下一步：先补齐可定位的 PDF 全文");
  await verifiedBaseline.getByText("验证与复现条件", { exact: true }).click();
  await expect(verifiedBaseline.getByText("引用关系：未检查。尚未运行引用图验证。", { exact: true })).toBeVisible();
  await expect(verifiedBaseline.getByText("仍缺少：可定位的 PDF 全文。", { exact: true })).toBeVisible();
  await expect(verifiedBaseline.getByText("代码来源：metadata.code ·")).toBeVisible();
  await expect(verifiedBaseline.getByRole("link", { name: "打开代码仓库" })).toHaveAttribute(
    "href",
    "https://github.com/example/pope",
  );
  await expect(page.getByTestId("baseline-reference-benchmark-1").locator(".baseline-verification")).toHaveCount(0);
  const directionPaperList = page.getByRole("region", { name: "direction paper cards" });
  const directionPaperButton = directionPaperList.getByRole("button", {
    name: `打开 Paper Card：${paper.title}`,
    exact: true,
  });
  await expect(directionPaperButton).toBeVisible();
  await page.getByRole("button", { name: /研究轨迹/ }).click();
  const visibleInspector = page.locator('aside[aria-label="workflow artifacts and warnings"]:not([hidden])');
  await expect(visibleInspector.getByTestId("artifact-hydration-warning")).toBeVisible();
  await visibleInspector.getByRole("button", { name: "关闭研究轨迹" }).click();
  await expect(page.getByRole("region", { name: "selected paper detail" })).toHaveCount(0);
  await directionPaperButton.click();
  await expect(page).toHaveURL(/#paper-reader\/paper_e2e_artifact_shape\?from=direction-review/);
  await expect(page.getByText("Selected Paper Detail")).toBeVisible();
  await expect(page.getByRole("heading", { name: paper.title, exact: true })).toBeFocused();
  await expect(page.getByText("Paper Signals")).toBeVisible();
  await expect(page.getByText("Research Sight")).toBeVisible();
  await expect(page.locator(".view-error-state")).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/#direction-review/);
  await expect(page.getByRole("region", { name: "selected paper detail" })).toHaveCount(0);

  await page.goto("/#paper-memory");
  await expect(page.getByText("Memory-Grounded Answer")).toBeVisible();
  await expect(page.getByText(paper.title, { exact: true })).toBeVisible();

  servedArtifacts = [v2DirectionArtifact, v2MemoryArtifact, malformedArtifact];
  await page.goto("/#direction-review");
  await expect(directionPaperButton).toBeVisible();
  await directionPaperButton.click();
  await expect(page).toHaveURL(/#paper-reader\/paper_e2e_artifact_shape\?from=direction-review/);
  await expect(page.getByTestId("direction-paper-section-heading-1")).toHaveText("研究问题与背景");
  await expect(page.locator('[data-testid^="direction-paper-section-heading-"]')).toHaveCount(1);
  await page.getByRole("button", { name: "第 2 节：Section 2" }).click();
  await expect(page.getByTestId("direction-paper-section-heading-2")).toHaveText("Section 2");
  await expect(page.locator('[data-testid^="direction-paper-section-heading-"]')).toHaveCount(1);
  await page.reload();
  await expect(page.getByText("Selected Paper Detail")).toBeVisible();
  await expect(page.getByRole("heading", { name: paper.title, exact: true })).toBeVisible();

  await page.goto("/#paper-reader/missing-paper-id?from=direction-review");
  await expect(page.getByRole("heading", { name: "未找到这篇 Paper Card" })).toBeVisible();
  await expect(page.getByRole("heading", { name: paper.title, exact: true })).toHaveCount(0);

  await page.goto("/#paper-reader");
  await expect(page.getByRole("heading", { name: "摘要级阅读 · Paper Card" })).toBeVisible();
  await expect(page.getByTestId("paper-reader-active-section-heading")).toHaveText("研究问题与背景");
  await expect(page.getByText("12/12 已生成")).toBeVisible();
  await expect(page.getByText("来源：Direction Review artifact", { exact: true })).toBeVisible();
  const limitedEvidence = page.getByRole("region", { name: "limited evidence summary" });
  await expect(limitedEvidence.getByText("能确认什么", { exact: true })).toBeVisible();
  await expect(limitedEvidence.getByText("不能确认什么", { exact: true })).toBeVisible();
  await expect(limitedEvidence.getByText("如何获得全文", { exact: true })).toBeVisible();
  await expect(page.getByText("待生成 Paper Card")).toHaveCount(0);

  await page.goto("/#paper-memory");
  await expect(page.getByText("Memory-Grounded Answer")).toBeVisible();
  await expect(page.locator('[aria-label="memory answer"]').getByText("摘要级证据，不是全文结论", { exact: true })).toBeVisible();
  await page.locator(".memory-hit-details summary").first().click();
  await expect(page.locator("dd", { hasText: "构造同答案但视觉证据冲突的样本。" })).toBeVisible();
  expect(pageErrors).toEqual([]);
  expect(consoleWarnings.filter((message) => message.includes("Encountered two children with the same key"))).toEqual([]);
});

test("manual unbound paper card does not mark selected paper reader complete", async ({ page }) => {
  const project = {
    id: "project_e2e_manual_unbound",
    title: "Manual Unbound Card Regression",
    description: "manual card should not bind to selected papers",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_manual_unbound",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const papers = [
    {
      id: "paper_e2e_bound_target",
      project_id: project.id,
      title: "Target VQA Faithfulness Paper",
      authors: "A. Researcher",
      abstract: "This is the selected real project paper.",
      year: "2026",
      type: "Benchmark",
      venue: "arXiv cs.CV",
      source: "arxiv",
      url: "https://arxiv.org/abs/2601.00008",
      relation: "strong match",
      priority: "High",
      code: "unknown",
      relevance_score: 1.3,
      relevance_quality: "strong",
      created_at: project.created_at,
    },
  ];
  const manualArtifact = {
    id: "artifact_e2e_manual_unbound_card",
    project_id: project.id,
    title: "paper_card_manual_notes.md",
    kind: "markdown",
    content_markdown: "# Manual Card",
    content_json: JSON.stringify({
      paper: {
        id: "",
        project_id: project.id,
        title: "Manual pasted notes that are not a selected paper",
      },
      card: {
        evidence_level: "abstract_only",
        sections: Array.from({ length: 12 }, (_, index) => ({
          id: `manual_section_${index + 1}`,
          title: `Manual section ${index + 1}`,
          content: "Manual unbound card content should not appear for the selected paper.",
        })),
        weakest_assumption: "Manual notes are not bound to a paper.",
        minimal_reproduction: "Status: blocked; missing claim + dataset + metric + baseline.",
      },
      evidence_level: "abstract_only",
    }),
    diff: "+ manual unbound card",
    created_at: project.created_at,
    updated_at: project.updated_at,
  };

  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok", service: "scholarflow-api", version: "0.1.0" } });
  });
  await page.route("**/projects", async (route) => {
    await route.fulfill({ json: [project] });
  });
  await page.route(`**/projects/${project.id}/papers`, async (route) => {
    await route.fulfill({ json: papers });
  });
  await page.route(`**/projects/${project.id}/timeline`, async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route(`**/projects/${project.id}/artifacts/summary`, async (route) => {
    await route.fulfill({ json: [artifactSummary(manualArtifact)] });
  });
  await page.route("**/artifacts/artifact_e2e_manual_unbound_card", async (route) => {
    await route.fulfill({ json: manualArtifact });
  });

  await page.goto("/#paper-reader");
  await expect(page.getByRole("heading", { name: "论文阅读 · Paper Card" })).toBeVisible();
  await expect(page.getByText("待生成 Paper Card")).toBeVisible();
  await expect(page.getByText("0/12 已生成")).toBeVisible();
  await expect(page.getByText("Manual unbound card content should not appear for the selected paper.")).toHaveCount(0);

  await page.goto("/#dashboard");
  const paperReaderStep = page.locator(".workflow-step", { hasText: "Deep Paper Card" });
  await expect(paperReaderStep.getByText("complete")).toHaveCount(0);
});

test("gap and experiment views show abstract-only evidence boundaries", async ({ page }) => {
  const project = {
    id: "project_e2e_decision_boundary",
    title: "Decision Evidence Boundary Regression",
    description: "abstract-only decision boundary",
    keyword: "VQA evidence faithfulness",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "api",
    active_session_id: "session_e2e_decision_boundary",
    created_at: "2026-07-02T00:00:00+00:00",
    updated_at: "2026-07-02T00:00:00+00:00",
  };
  const restoredDecisionGoal =
    "在 7 天内评估 multi-object hallucination，区别于 POPE，并且不要使用 POPE。";
  const decisionPayload = {
    gaps: [
      {
        id: "gap_boundary",
        title: "Need counterfactual evidence grounding",
        kind: "true_gap",
        evidence: "Only one abstract-level benchmark card supports this gap.",
        weakness: "Evidence is not full-text verified.",
        opportunity: "Build a small counterfactual VQA set.",
        novelty_risk: "medium",
        feasibility: "one-week",
        support_status: "single_source",
        confidence: "low",
        paper_ids: ["paper_abstract_gap"],
        evidence_refs: [
          {
            paper_id: "paper_abstract_gap",
            paper_title: "Abstract Gap Candidate",
            snippet_id: "abstract-limitation",
            source: "metadata.abstract",
            section: "abstract",
            page: "",
            text: "The current benchmark covers only a narrow answer distribution.",
            evidence_level: "abstract_only",
          },
        ],
        validation_requirements: [
          "补充第二篇独立论文的同类限制证据。",
          "在统一 dataset、metric 与 baseline 下复核。",
        ],
      },
    ],
    validation: {
      idea: "保守候选：做反事实 evidence grounding probe。",
      why_not_incremental: "It targets a failure mode rather than a metric-only increment.",
      difference_from_existing_work: "Uses counterfactual visual evidence.",
      novelty_risk: "medium",
      feasibility: "one-week",
      key_risks: ["abstract-only evidence"],
    },
    experiment: {
      status: "blocked",
      anchor_paper_id: "",
      anchor_paper_title: "",
      claim: "缺少可复现 anchor",
      dataset: "",
      baseline: "",
      metrics: [],
      ablations: [],
      resources: "Need full paper details.",
      timeline: [],
      success_criterion: "",
      failure_criterion: "",
      unblock_suggestions: ["补充 PDF 或正文方法/实验部分。"],
      goal_alignment: {
        status: "mismatch",
        hard_constraint_checks: {
          "24GB": "blocked",
          "POPE / CHAIR": "ready",
        },
      },
      readiness_checks: {
        goal_constraints: "blocked: 缺少 24GB",
      },
      assumptions: ["24GB"],
    },
    artifacts: [],
    decision_status: "partial",
    evidence_quality: {
      gap_evidence_paper_count: 1,
      minimum_true_gap_paper_count: 2,
      minimum_true_gap_full_text_count: 2,
      minimum_gap_consistency_score: 0.7,
      abstract_only_card_count: 1,
      metadata_only_card_count: 0,
      full_text_card_count: 0,
      grounded_gap_evidence_count: 1,
      corroborated_gap_group_count: 0,
    },
    decision_intent: {
      raw_goal: restoredDecisionGoal,
      focus: "VQA evidence faithfulness",
      required_terms: ["multi-object"],
      contrast_terms: ["POPE"],
      excluded_terms: ["POPE"],
      contribution_type: "evaluation",
      time_budget_days: 7,
    },
    warnings: ["当前 Paper Card 主要是摘要级/元数据级证据，不是全文级深读结论。"],
  };
  const decisionArtifact = {
    id: "artifact_e2e_decision_boundary",
    project_id: project.id,
    title: "gap_board_decision_boundary.md",
    kind: "markdown",
    content_markdown: "# Gap Board",
    content_json: JSON.stringify(decisionPayload),
    diff: "+ decision boundary",
    created_at: project.created_at,
    updated_at: project.updated_at,
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
    await route.fulfill({ json: [artifactSummary(decisionArtifact)] });
  });
  await page.route("**/artifacts/artifact_e2e_decision_boundary", async (route) => {
    await route.fulfill({ json: decisionArtifact });
  });

  await page.goto("/#gap-board");
  await expect(page.getByRole("textbox", { name: "决策目标" })).toHaveValue(restoredDecisionGoal);
  await expect(page.getByText("摘要级证据，不是全文结论", { exact: true })).toBeVisible();
  await expect(page.getByText(/保守提示：当前不是确定科研结论。Only one abstract-level benchmark card supports this gap./)).toBeVisible();
  await expect(page.getByText("single_source · low", { exact: true })).toBeVisible();
  await page.getByText("查看原文证据锚点（1）", { exact: true }).click();
  await expect(page.getByText("The current benchmark covers only a narrow answer distribution.", { exact: true })).toBeVisible();
  await expect(page.getByText("补充第二篇独立论文的同类限制证据。", { exact: true })).toBeVisible();

  await page.goto("/#experiment-planner");
  await expect(page.getByText("摘要级证据，不是全文结论", { exact: true })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "补充 PDF 或正文方法/实验部分。" })).toBeVisible();
  await expect(page.getByText("24GB: blocked；POPE / CHAIR: ready", { exact: true })).toBeVisible();
  await expect(page.getByText("[object Object]", { exact: true })).toHaveCount(0);
});

test("experiment planner keeps verified anchors partial until execution details are known", async ({ page }) => {
  const project = {
    id: "project_e2e_partial_experiment",
    title: "Partial Experiment Contract",
    description: "verified research anchor with incomplete execution details",
    keyword: "hallucination evaluation",
    field: "Artificial Intelligence",
    language: "zh-CN",
    workflow: "survey-to-experiment",
    stage: "experiment-planning",
    active_session_id: "session_e2e_partial_experiment",
    created_at: "2026-07-03T00:00:00+00:00",
    updated_at: "2026-07-03T00:00:00+00:00",
  };
  const decisionPayload = {
    gaps: [],
    validation: {
      idea: "Evaluate object hallucination under controlled visual evidence removal.",
      why_not_incremental: "It isolates a concrete failure mode.",
      difference_from_existing_work: "Uses controlled evidence removal.",
      novelty_risk: "medium",
      feasibility: "one-month",
      key_risks: [],
    },
    experiment: {
      status: "partial",
      anchor_paper_id: "paper_verified_anchor",
      anchor_paper_title: "Verified Hallucination Benchmark",
      claim: "Test whether evidence removal increases object hallucination.",
      dataset: "POPE",
      baseline: "LLaVA-1.5",
      metrics: ["accuracy", "hallucination rate"],
      ablations: ["remove visual evidence"],
      resources: "Research fields are verified; execution details remain unknown.",
      timeline: ["Confirm model/API access", "Run registered evaluation"],
      success_criterion: "A preregistered reduction in hallucination rate.",
      failure_criterion: "Stop if the registered sample size cannot be obtained.",
      unblock_suggestions: ["补齐执行条件 `sample_size: 未提供样本量`。"],
      goal_alignment: {
        status: "aligned",
        score: 100,
        constraint_groups: [
          { mode: "any_of", terms: ["POPE", "CHAIR", "AMBER"], satisfied_by: ["POPE"] },
        ],
      },
      readiness_checks: {
        anchor: "ready: verified PDF evidence",
        dataset: "ready: POPE",
        baseline: "ready: LLaVA-1.5",
        metric: "ready: accuracy",
        sample_size: "unknown: 未提供样本量",
      },
      assumptions: ["sample_size"],
    },
    artifacts: [],
    decision_status: "partial",
    evidence_quality: {
      grounded_gap_evidence_count: 2,
      specific_gap_evidence_count: 2,
      corroborated_gap_group_count: 1,
      conflicted_gap_group_count: 0,
      full_text_card_count: 2,
      abstract_only_card_count: 0,
      metadata_only_card_count: 0,
    },
    warnings: [],
  };
  const decisionArtifact = {
    id: "artifact_e2e_partial_experiment",
    project_id: project.id,
    title: "experiment_plan_partial.md",
    kind: "markdown",
    content_markdown: "# Partial Experiment Plan",
    content_json: JSON.stringify(decisionPayload),
    diff: "+ partial experiment contract",
    created_at: project.created_at,
    updated_at: project.updated_at,
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
    await route.fulfill({ json: [artifactSummary(decisionArtifact)] });
  });
  await page.route("**/artifacts/artifact_e2e_partial_experiment", async (route) => {
    await route.fulfill({ json: decisionArtifact });
  });

  await page.goto("/#experiment-planner");
  await expect(page.getByRole("heading", { name: "科研锚点已确认，执行条件待补齐" })).toBeVisible();
  await expect(page.getByRole("status", { name: "experiment partial reason" })).toBeVisible();
  await expect(page.locator(".experiment-detail").getByText("partial", { exact: true })).toBeVisible();
  await expect(page.getByText("unknown: 未提供样本量", { exact: true })).toBeVisible();
  await expect(page.getByText(/mode: any_of/)).toBeVisible();

  await page.goto("/#dashboard");
  const experimentStep = page.locator(".workflow-step", { hasText: "Experiment Plan" });
  await expect(experimentStep.getByText("partial", { exact: true })).toBeVisible();
  await expect(experimentStep.getByText("科研锚点已核验，执行参数尚未补齐", { exact: true })).toBeVisible();
});
