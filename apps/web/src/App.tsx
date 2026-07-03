import { useEffect, useMemo, useState } from "react";
import {
  type ApiAgentPlanResponse,
  type ApiArtifact,
  type ApiArtifactSummary,
  type ApiDirectionReviewResponse,
  type ApiPaper,
  type ApiPaperCard,
  type ApiProject,
  type ApiResearchDecisionResponse,
  type ApiResearchMemoryQueryResponse,
} from "@scholarflow/schemas";
import {
  artifacts,
  navItems,
  type ArtifactContent,
  type PaperRow,
  type TimelineEvent,
  type ViewId,
} from "./mockData";
import {
  createAgentPlan,
  createDirectionReview,
  createProject,
  createProjectPaperCard,
  createResearchDecisions,
  executeAgentRun,
  getArtifact,
  getHealth,
  getProjectTimeline,
  listProjectArtifactSummaries,
  listProjectPapers,
  listProjects,
  queryResearchMemory,
  saveArtifact,
  searchProjectLiterature,
} from "./apiClient";
import { ViewErrorBoundary } from "./components/ViewErrorBoundary";
import {
  artifactSummaryFromDetail,
  hydrateWorkflowStateFromArtifacts,
  loadHydrationArtifacts,
  selectArtifactForView,
  toPaperRow,
  toTimelineEvent,
  upsertArtifactDetail,
  upsertArtifactSummary,
} from "./lib/artifactHydration";
import type { ApiStatus, ArtifactTab, ProjectDraft } from "./types/workflow";
import { ActiveView, ProductTopNav } from "./views/ProductViews";
import "./styles.css";

const viewTitles: Record<ViewId, string> = {
  dashboard: "项目总览",
  "new-project": "新建科研项目",
  "paper-table": "论文表格",
  "direction-review": "方向精读",
  "paper-memory": "论文记忆",
  "paper-reader": "论文精读",
  "gap-board": "Gap Board",
  "experiment-planner": "实验计划",
};

const productViewIds: ViewId[] = [
  "dashboard",
  "new-project",
  "paper-table",
  "direction-review",
  "paper-memory",
  "paper-reader",
  "gap-board",
  "experiment-planner",
];

const ACTIVE_PROJECT_STORAGE_KEY = "scholarflow.activeProjectId";
const viewAliases: Record<string, ViewId> = {
  "experiment-plan": "experiment-planner",
  "deep-paper-card": "paper-reader",
};
const coreViews = new Set<ViewId>([
  "paper-table",
  "direction-review",
  "paper-memory",
  "paper-reader",
  "gap-board",
  "experiment-planner",
]);

function readViewFromHash(): ViewId {
  if (typeof window === "undefined") {
    return "dashboard";
  }
  const hashView = window.location.hash.replace("#", "");
  if (hashView in viewAliases) {
    return viewAliases[hashView];
  }
  return productViewIds.includes(hashView as ViewId) ? (hashView as ViewId) : "dashboard";
}

function readStoredActiveProjectId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
}

function storeActiveProjectId(projectId: string | null) {
  if (typeof window === "undefined") {
    return;
  }
  if (projectId) {
    window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, projectId);
  } else {
    window.localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
  }
}

function isDemoProject(projectId: string | undefined | null): boolean {
  return projectId === "local-bootstrap";
}

function isSeedLikePaper(paper: ApiPaper | PaperRow): boolean {
  const source = paper.source.toLowerCase();
  const venue = paper.venue.toLowerCase();
  const code = paper.code.toLowerCase();
  const title = paper.title.toLowerCase();
  return source === "seed" || venue === "demo" || code === "demo" || title.startsWith("synthetic example:");
}

export function App() {
  const [activeView, setActiveView] = useState<ViewId>(() => readViewFromHash());
  const [artifactTab, setArtifactTab] = useState<ArtifactTab>("markdown");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [apiMessage, setApiMessage] = useState("正在连接 ScholarFlow API...");
  const [projects, setProjects] = useState<ApiProject[]>([]);
  const [activeProject, setActiveProject] = useState<ApiProject | null>(null);
  const [paperRows, setPaperRows] = useState<PaperRow[]>([]);
  const [timelineRows, setTimelineRows] = useState<TimelineEvent[]>([]);
  const [persistedArtifactCount, setPersistedArtifactCount] = useState(0);
  const [lastSavedArtifact, setLastSavedArtifact] = useState<ApiArtifact | null>(null);
  const [projectArtifacts, setProjectArtifacts] = useState<ApiArtifact[]>([]);
  const [projectArtifactSummaries, setProjectArtifactSummaries] = useState<ApiArtifactSummary[]>([]);
  const [artifactDraft, setArtifactDraft] = useState<ArtifactContent | null>(null);
  const [artifactSaving, setArtifactSaving] = useState(false);
  const [projectDraft, setProjectDraft] = useState<ProjectDraft>({
    title: "",
    description: "",
    keyword: "",
    field: "Artificial Intelligence",
  });
  const [agentTask, setAgentTask] = useState(
    "请根据我的研究方向，生成一个从文献检索到可验证 gap 的最小科研任务计划。",
  );
  const [agentPlan, setAgentPlan] = useState<ApiAgentPlanResponse | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [literatureQuery, setLiteratureQuery] = useState("");
  const [literatureBusy, setLiteratureBusy] = useState(false);
  const [literatureErrors, setLiteratureErrors] = useState<string[]>([]);
  const [directionInput, setDirectionInput] = useState("");
  const [directionRound, setDirectionRound] = useState(1);
  const [directionBusy, setDirectionBusy] = useState(false);
  const [directionReview, setDirectionReview] = useState<ApiDirectionReviewResponse | null>(null);
  const [selectedDirectionPaperId, setSelectedDirectionPaperId] = useState("");
  const [memoryQuestion, setMemoryQuestion] = useState("这个方向最值得做的一周验证实验是什么？");
  const [memoryTopK, setMemoryTopK] = useState(5);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryResult, setMemoryResult] = useState<ApiResearchMemoryQueryResponse | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [paperCardInput, setPaperCardInput] = useState("");
  const [paperCardBusy, setPaperCardBusy] = useState(false);
  const [latestPaperCard, setLatestPaperCard] = useState<ApiPaperCard | null>(null);
  const [decisionGoal, setDecisionGoal] = useState(
    "基于当前 paper table 和 paper card，找出最值得做的一周最小实验方向。",
  );
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [researchDecision, setResearchDecision] = useState<ApiResearchDecisionResponse | null>(null);

  const activeArtifact = artifacts[activeView];
  const displayedArtifact: ArtifactContent = lastSavedArtifact
    ? {
        title: lastSavedArtifact.title,
        markdown: lastSavedArtifact.content_markdown,
        json: lastSavedArtifact.content_json,
        diff: lastSavedArtifact.diff,
      }
    : activeArtifact;
  const activeNavItem = useMemo(
    () => navItems.find((item) => item.id === activeView),
    [activeView],
  );
  useEffect(() => {
    let cancelled = false;

    async function loadWorkspace() {
      try {
        await getHealth();
        const loadedProjects = await listProjects();
        const storedProjectId = readStoredActiveProjectId();
        const latestUserProject = loadedProjects.find((project) => !isDemoProject(project.id)) ?? null;
        const storedProject =
          loadedProjects.find((project) => {
            if (project.id !== storedProjectId) {
              return false;
            }
            return !isDemoProject(project.id) || latestUserProject === null;
          }) ?? null;
        const firstProject =
          storedProject ?? latestUserProject ?? loadedProjects[0] ?? null;

        if (cancelled) {
          return;
        }

        setApiStatus("online");
        setProjects(loadedProjects);
        setActiveProject(firstProject);
        setApiMessage(firstProject ? "API 已连接，正在使用 SQLite 工作区。" : "API 已连接，尚未创建项目。");
        if (firstProject && !isDemoProject(firstProject.id)) {
          storeActiveProjectId(firstProject.id);
        }

        if (firstProject) {
          await loadProjectResources(firstProject.id, cancelled);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setApiStatus("offline");
        setPaperRows([]);
        setTimelineRows([]);
        setProjectArtifacts([]);
        setProjectArtifactSummaries([]);
        setPersistedArtifactCount(0);
        setApiMessage("API 未连接，请先启动 ScholarFlow 后端服务。");
      }
    }

    loadWorkspace();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleHashChange() {
      setActiveView(readViewFromHash());
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (activeProject?.keyword && activeProject.keyword !== "你的研究方向关键词") {
      setLiteratureQuery(activeProject.keyword);
      setDirectionInput(activeProject.keyword);
    }
  }, [activeProject?.id, activeProject?.keyword]);

  useEffect(() => {
    const cachedArtifact = selectArtifactForView(projectArtifacts, activeView);
    if (cachedArtifact) {
      setLastSavedArtifact(cachedArtifact);
      return;
    }

    const summary = selectArtifactForView(projectArtifactSummaries, activeView);
    if (!summary) {
      setLastSavedArtifact(null);
      return;
    }

    let cancelled = false;
    getArtifact(summary.id)
      .then((artifact) => {
        if (cancelled) {
          return;
        }
        setProjectArtifacts((items) => upsertArtifactDetail(items, artifact));
        setLastSavedArtifact(artifact);
      })
      .catch(() => {
        if (!cancelled) {
          setLastSavedArtifact(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activeView, projectArtifacts, projectArtifactSummaries]);

  useEffect(() => {
    setArtifactDraft(displayedArtifact);
  }, [displayedArtifact.title, displayedArtifact.markdown, displayedArtifact.json, displayedArtifact.diff]);

  useEffect(() => {
    if (!paperRows.length) {
      setSelectedPaperId("");
      return;
    }
    if (!paperRows.some((paper) => paper.id === selectedPaperId)) {
      setSelectedPaperId(paperRows[0].id);
    }
  }, [paperRows, selectedPaperId]);

  async function loadProjectResources(projectId: string, cancelled = false) {
    const [apiPapers, apiTimeline, artifactSummaries] = await Promise.all([
      listProjectPapers(projectId),
      getProjectTimeline(projectId),
      listProjectArtifactSummaries(projectId),
    ]);

    if (cancelled) {
      return;
    }

    const apiArtifacts = await loadHydrationArtifacts(artifactSummaries);
    if (cancelled) {
      return;
    }

    setPaperRows(apiPapers.filter((paper) => !isSeedLikePaper(paper)).map(toPaperRow));
    setTimelineRows(apiTimeline.map(toTimelineEvent));
    setPersistedArtifactCount(artifactSummaries.length);
    setProjectArtifactSummaries(artifactSummaries);
    setProjectArtifacts(apiArtifacts);
    setLastSavedArtifact(selectArtifactForView(apiArtifacts, activeView));
    const restored = hydrateWorkflowStateFromArtifacts(apiArtifacts);
    if (restored.directionReview) {
      setDirectionReview(restored.directionReview);
    }
    if (restored.memoryResult) {
      setMemoryResult(restored.memoryResult);
    }
    if (restored.paperCard) {
      setLatestPaperCard(restored.paperCard);
    }
    if (restored.researchDecision) {
      setResearchDecision(restored.researchDecision);
    }
  }

  function resetWorkflowState() {
    setDirectionReview(null);
    setSelectedDirectionPaperId("");
    setMemoryResult(null);
    setResearchDecision(null);
    setLatestPaperCard(null);
  }

  async function handleSelectProject(projectId: string) {
    const project = projects.find((item) => item.id === projectId) ?? null;
    setActiveProject(project);
    storeActiveProjectId(project && !isDemoProject(project.id) ? project.id : null);
    setLastSavedArtifact(null);
    setProjectArtifacts([]);
    setProjectArtifactSummaries([]);
    resetWorkflowState();

    if (!project) {
      setPaperRows([]);
      setTimelineRows([]);
      setPersistedArtifactCount(0);
      return;
    }

    setApiMessage(`正在切换项目: ${project.title}`);
    await loadProjectResources(project.id);
    setApiMessage(`已切换项目: ${project.title}`);
  }

  async function handleCreateProject() {
    const keyword = projectDraft.keyword.trim();
    if (!keyword) {
      setApiMessage("请先输入你想研究的方向或关键词。");
      return;
    }

    const title = projectDraft.title.trim() || keyword;
    const description =
      projectDraft.description.trim() || `围绕「${keyword}」检索论文、精读论文、生成 gap 和实验计划。`;
    const field = projectDraft.field.trim() || "Artificial Intelligence";

    setApiMessage("正在创建本地 research project...");
    try {
      const project = await createProject({
        title,
        description,
        keyword,
        field,
        language: "zh-CN",
        workflow: "survey-to-experiment",
      });
      const nextProjects = [project, ...projects.filter((item) => item.id !== project.id)];
      setApiStatus("online");
      setProjects(nextProjects);
      setActiveProject(project);
      resetWorkflowState();
      storeActiveProjectId(project.id);
      setActiveViewAndHash("paper-table");
      setLiteratureQuery(keyword);
      setDirectionInput(keyword);
      setAgentTask(`请基于「${keyword}」方向，生成一个从文献检索到可验证 gap 的最小科研任务计划。`);
      setApiMessage(`已创建项目并初始化 session: ${project.id}`);
      await loadProjectResources(project.id);
    } catch (error) {
      setApiStatus("offline");
      setApiMessage("创建项目失败，请确认 API 服务是否运行在 127.0.0.1:8000。");
    }
  }

  async function handleSaveArtifact() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    const artifactToSave = artifactDraft ?? displayedArtifact;
    setArtifactSaving(true);
    setApiMessage("正在保存右侧 Artifact 编辑内容到 SQLite...");
    try {
      const saved = await saveArtifact({
        project_id: activeProject.id,
        title: artifactToSave.title,
        kind: artifactTab,
        content_markdown: artifactToSave.markdown,
        content_json: artifactToSave.json,
        diff: artifactToSave.diff,
      });
      const reloaded = await getArtifact(saved.id);
      setLastSavedArtifact(reloaded);
      setPersistedArtifactCount((count) => count + 1);
      setApiMessage(`Artifact 已保存并回读: ${reloaded.id}`);
      const refreshedTimeline = await getProjectTimeline(activeProject.id);
      setTimelineRows(refreshedTimeline.map(toTimelineEvent));
      setProjectArtifacts((items) => upsertArtifactDetail(items, reloaded));
      setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(reloaded)));
    } catch (error) {
      setApiMessage("保存 artifact 失败，请确认 API 与 SQLite 工作区可用。");
    } finally {
      setArtifactSaving(false);
    }
  }

  async function handleLoadArtifact(artifactId: string) {
    if (!artifactId) {
      return;
    }
    try {
      const artifact = await getArtifact(artifactId);
      setLastSavedArtifact(artifact);
      setProjectArtifacts((items) => upsertArtifactDetail(items, artifact));
      setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(artifact)));
      setArtifactTab("markdown");
      setApiMessage(`已回读完整 artifact: ${artifact.title}`);
    } catch (error) {
      setApiMessage("读取 artifact 失败，请确认后端 API 与 SQLite 工作区可用。");
    }
  }

  async function handleCreateAgentPlan() {
    if (!activeProject) {
      setApiMessage("没有可运行的项目，请先创建项目或启动 API。");
      return;
    }

    setAgentBusy(true);
    setApiMessage("正在生成 Research Plan...");
    try {
      const plan = await createAgentPlan({
        project_id: activeProject.id,
        task: agentTask,
        provider: "openrouter",
      });
      setAgentPlan(plan);
      setLastSavedArtifact(plan.artifact);
      setApiMessage(`Research Plan 已生成，run: ${plan.run_id}`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("生成 Research Plan 失败，请确认 API 与 SQLite 工作区可用。");
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleExecuteAgentRun() {
    if (!agentPlan) {
      setApiMessage("请先生成 Research Plan。");
      return;
    }

    setAgentBusy(true);
    const stopProgress = startProgressMessages([
      "Agent Run: 正在执行文献检索工具...",
      "Agent Run: 正在生成方向精读与 Paper Memory...",
      "Agent Run: 正在生成 Gap Board、Experiment Plan 并保存 artifact...",
    ]);
    try {
      const result = await executeAgentRun(agentPlan.run_id, { confirmed: true });
      setAgentPlan({
        ...agentPlan,
        status: result.status,
        steps: result.steps,
        artifact: result.artifact,
      });
      setLastSavedArtifact(result.artifact);
      setApiMessage(`Agent Run 已完成，artifact: ${result.artifact.id}`);
      await loadProjectResources(agentPlan.project_id);
    } catch (error) {
      setApiMessage("执行 Agent Run 失败，请查看 API 日志。");
    } finally {
      stopProgress();
      setAgentBusy(false);
    }
  }

  async function handleSearchLiterature() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setLiteratureBusy(true);
    setLiteratureErrors([]);
    setPaperRows([]);
    const stopProgress = startProgressMessages([
      "Literature Search: 正在扩展关键词并查询 arXiv / OpenAlex...",
      "Literature Search: 正在去重、排序并检查低召回...",
      "Literature Search: 正在保存 Paper Table artifact 到 SQLite...",
    ]);
    try {
      const result = await searchProjectLiterature(activeProject.id, {
        query: literatureQuery,
        max_results: 12,
        sources: ["arxiv", "openalex"],
      });
      setPaperRows(result.papers.filter((paper) => !isSeedLikePaper(paper)).map(toPaperRow));
      setLastSavedArtifact(result.artifact);
      setLiteratureErrors(result.errors);
      setApiMessage(`检索完成：${result.papers.length} 篇论文，artifact: ${result.artifact.id}`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setPaperRows([]);
      setLiteratureErrors(["文献检索请求失败。请检查网络、OpenAlex/arXiv 可用性或 API 日志。"]);
      setApiMessage("文献检索失败，请检查网络、OpenAlex/arXiv 可用性或 API 日志。");
    } finally {
      stopProgress();
      setLiteratureBusy(false);
    }
  }

  async function handleGeneratePaperCard() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    const selectedPaper = paperRows.find((paper) => paper.id === selectedPaperId) ?? paperRows[0];
    if (!selectedPaper && !paperCardInput.trim()) {
      setApiMessage("请先选择一篇论文，或粘贴摘要/正文片段。");
      return;
    }

    setPaperCardBusy(true);
    setApiMessage("正在生成 12 段 Deep Paper Card...");
    try {
      const result = await createProjectPaperCard(activeProject.id, {
        paper_id: selectedPaper?.id,
        title: selectedPaper?.title,
        abstract: selectedPaper?.abstract,
        paper_text: paperCardInput,
      });
      setLatestPaperCard(result.card);
      setLastSavedArtifact(result.artifact);
      setApiMessage(`Deep Paper Card 已生成，artifact: ${result.artifact.id}`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("生成 Deep Paper Card 失败，请确认论文属于当前项目，或粘贴足够的摘要/正文。");
    } finally {
      setPaperCardBusy(false);
    }
  }

  async function handleCreateDirectionReview() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setDirectionBusy(true);
    const stopProgress = startProgressMessages([
      `Direction Review: 正在界定第 ${directionRound} 轮研究方向范围...`,
      "Direction Review: 正在检索候选池并构建 BaselineMap...",
      "Direction Review: 正在生成 10 篇 Paper Card、ResearchSight 和 Paper Memory...",
      "Direction Review: 正在保存 artifacts；如果检索源限流，会标记 partial 或 warning。",
    ]);
    try {
      const payload = {
        direction: directionInput,
        round: directionRound,
      };
      const timeout = new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error("Direction Review timeout")), 90000);
      });
      const result = await Promise.race([createDirectionReview(activeProject.id, payload), timeout]);
      setDirectionReview(result);
      setSelectedDirectionPaperId("");
      const reviewArtifactRef =
        result.artifact_refs.find((artifact) => artifact.title.toLowerCase().includes("direction_review")) ??
        result.artifact_refs[0];
      if (reviewArtifactRef) {
        await handleLoadArtifact(reviewArtifactRef.id);
      }
      setApiMessage(
        result.review_status === "partial"
          ? `方向精读 partial：第 ${result.round} 轮仅读取 ${result.round_read_count}/${result.target_paper_count} 篇，不能视为完整 10 篇方向精读。`
          : `方向精读完成：第 ${result.round} 轮，累计 ${result.total_read_count} 篇。`,
      );
      await loadProjectResources(activeProject.id);
    } catch (error) {
      if (error instanceof Error && error.message === "Direction Review timeout") {
        setApiMessage("方向精读超时。建议稍后重试，或先只运行 Literature Search。");
      } else {
        setApiMessage("方向精读失败，请检查网络、检索源可用性或 API 日志。");
      }
    } finally {
      stopProgress();
      setDirectionBusy(false);
    }
  }

  async function handleQueryResearchMemory() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setMemoryBusy(true);
    const stopProgress = startProgressMessages([
      `Paper Memory: 正在从 SQLite memory bank 检索 ${memoryTopK} 篇相关论文...`,
      "Paper Memory: 正在按问题意图匹配 minimal reproduction、counterexample 和 ResearchSight 字段...",
      "Paper Memory: 正在保存 grounded answer artifact...",
    ]);
    try {
      const result = await queryResearchMemory(activeProject.id, {
        question: memoryQuestion,
        direction: directionInput,
        top_k: memoryTopK,
      });
      setMemoryResult(result);
      setLastSavedArtifact(result.artifact);
      setApiMessage(`论文记忆回答已生成：命中 ${result.hits.length} 篇，memory bank 总量 ${result.total_memories}。`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("论文记忆检索失败，请先执行方向精读，或检查 API 日志。");
    } finally {
      stopProgress();
      setMemoryBusy(false);
    }
  }

  async function handleCreateResearchDecision() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setDecisionBusy(true);
    const stopProgress = startProgressMessages([
      "Research Decision: 正在读取 paper table 和 paper cards...",
      "Research Decision: 正在区分 true_gap / engineering_gap / pseudo_gap...",
      "Research Decision: 正在检查 claim、dataset、metric、baseline 与真实 anchor...",
    ]);
    try {
      const result = await createResearchDecisions(activeProject.id, {
        goal: decisionGoal,
      });
      setResearchDecision(result);
      setLastSavedArtifact(result.artifacts[result.artifacts.length - 1] ?? null);
      setApiMessage(`研究决策已生成：${result.gaps.length} gaps + experiment plan`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("生成研究决策失败，请确认已有 paper table 或 paper card。");
    } finally {
      stopProgress();
      setDecisionBusy(false);
    }
  }

  function startProgressMessages(messages: string[], intervalMs = 6500): () => void {
    if (!messages.length) {
      return () => undefined;
    }
    let index = 0;
    setApiMessage(messages[index]);
    const timer = window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      setApiMessage(messages[index]);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }

  function setActiveViewAndHash(view: ViewId) {
    setActiveView(view);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${view}`);
    }
  }

  return (
    <div className={`scholarflow-product-shell view-${activeView}`}>
      <ProductTopNav activeView={activeView} onSelectView={setActiveViewAndHash} />
      <main className="product-page" aria-label={activeNavItem?.label ?? viewTitles[activeView]}>
        <ViewErrorBoundary view={activeView}>
          <ActiveView
            activeProject={activeProject}
            agentBusy={agentBusy}
            agentPlan={agentPlan}
            agentTask={agentTask}
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            artifactCount={persistedArtifactCount}
            artifactSummaries={projectArtifactSummaries}
            decisionBusy={decisionBusy}
            decisionGoal={decisionGoal}
            directionBusy={directionBusy}
            directionInput={directionInput}
            directionReview={directionReview}
            directionRound={directionRound}
            literatureBusy={literatureBusy}
            literatureErrors={literatureErrors}
            literatureQuery={literatureQuery}
            memoryBusy={memoryBusy}
            memoryQuestion={memoryQuestion}
            memoryResult={memoryResult}
            memoryTopK={memoryTopK}
            projectDraft={projectDraft}
            onAgentTaskChange={setAgentTask}
            onCreateProject={handleCreateProject}
            onCreateAgentPlan={handleCreateAgentPlan}
            onCreateDirectionReview={handleCreateDirectionReview}
            onExecuteAgentRun={handleExecuteAgentRun}
            onGeneratePaperCard={handleGeneratePaperCard}
            onCreateResearchDecision={handleCreateResearchDecision}
            onDecisionGoalChange={setDecisionGoal}
            onDirectionInputChange={setDirectionInput}
            onDirectionRoundChange={setDirectionRound}
            onLiteratureQueryChange={setLiteratureQuery}
            onLoadArtifact={handleLoadArtifact}
            onMemoryQuestionChange={setMemoryQuestion}
            onMemoryTopKChange={setMemoryTopK}
            onPaperCardInputChange={setPaperCardInput}
            onQueryResearchMemory={handleQueryResearchMemory}
            onProjectDraftChange={setProjectDraft}
            onSearchLiterature={handleSearchLiterature}
            onSelectedDirectionPaperChange={setSelectedDirectionPaperId}
            onSelectedPaperChange={setSelectedPaperId}
            onSelectView={setActiveViewAndHash}
            paperRows={paperRows}
            paperCardBusy={paperCardBusy}
            paperCardInput={paperCardInput}
            projectCount={projects.length}
            researchDecision={researchDecision}
            selectedDirectionPaperId={selectedDirectionPaperId}
            selectedPaperId={selectedPaperId}
            latestPaperCard={latestPaperCard}
            view={activeView}
          />
        </ViewErrorBoundary>
      </main>
    </div>
  );
}
