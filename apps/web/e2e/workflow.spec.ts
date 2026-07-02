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
