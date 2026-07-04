import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ApiAgentPlanResponse,
  ApiArtifact,
  ApiArtifactSummary,
  ApiDirectionReviewResponse,
  ApiPaper,
  ApiPaperCard,
  ApiProject,
  ApiResearchDecisionResponse,
  ApiResearchMemoryQueryResponse,
  ApiWorkflowStepState,
} from "@scholarflow/schemas";
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
  isAbortError,
  isRetrievalWarning,
  listProjectArtifactSummaries,
  listProjectPapers,
  listProjects,
  normalizeApiError,
  queryResearchMemory,
  saveArtifact,
  searchProjectLiterature,
} from "../apiClient";
import type { ArtifactContent, PaperRow, TimelineEvent, ViewId } from "../mockData";
import {
  artifactSummaryFromDetail,
  collectArtifactHydrationWarnings,
  hydrateWorkflowStateFromArtifacts,
  loadHydrationArtifacts,
  selectArtifactForView,
  toPaperRow,
  toTimelineEvent,
  upsertArtifactDetail,
  upsertArtifactSummary,
} from "./artifactHydration";
import type {
  ApiStatus,
  ArtifactTab,
  ProjectDraft,
  WorkflowActions,
  WorkflowController,
  WorkflowNotice,
  WorkflowStepStatus,
  WorkflowStepView,
  WorkflowViewModel,
  RelevanceCoverage,
} from "../types/workflow";

const ACTIVE_PROJECT_STORAGE_KEY = "scholarflow.activeProjectId";

type RequestScope =
  | "workspace"
  | "resources"
  | "artifact"
  | "agent"
  | "literature"
  | "direction"
  | "paper-card"
  | "memory"
  | "decision";

type RequestGuard = {
  signal: AbortSignal;
  isCurrent: () => boolean;
  isAborted: () => boolean;
  finish: () => void;
};

const workflowLabels: Record<ViewId, string> = {
  dashboard: "项目总览",
  "new-project": "新建项目",
  "paper-table": "Paper Table",
  "direction-review": "Direction Review",
  "paper-reader": "Deep Paper Card",
  "paper-memory": "Paper Memory",
  "gap-board": "Gap Board",
  "experiment-planner": "Experiment Plan",
};

export function useWorkflowController(activeView: ViewId, onSelectView: (view: ViewId) => void): WorkflowController {
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
  const [agentRunWarnings, setAgentRunWarnings] = useState<string[]>([]);
  const [literatureQuery, setLiteratureQuery] = useState("");
  const [literatureBusy, setLiteratureBusy] = useState(false);
  const [literatureErrors, setLiteratureErrors] = useState<string[]>([]);
  const [literatureCoverage, setLiteratureCoverage] = useState<RelevanceCoverage>({});
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
  const [hydrationWarnings, setHydrationWarnings] = useState<string[]>([]);
  const [backendWorkflowSteps, setBackendWorkflowSteps] = useState<ApiWorkflowStepState[]>([]);

  const activeProjectIdRef = useRef<string | null>(null);
  const requestStateRef = useRef<Record<RequestScope, { id: number; controller: AbortController | null }>>({
    workspace: { id: 0, controller: null },
    resources: { id: 0, controller: null },
    artifact: { id: 0, controller: null },
    agent: { id: 0, controller: null },
    literature: { id: 0, controller: null },
    direction: { id: 0, controller: null },
    "paper-card": { id: 0, controller: null },
    memory: { id: 0, controller: null },
    decision: { id: 0, controller: null },
  });

  useEffect(() => {
    activeProjectIdRef.current = activeProject?.id ?? null;
  }, [activeProject?.id]);

  useEffect(() => {
    const guard = beginRequest("workspace");
    loadWorkspace(guard);
    return () => {
      guard.finish();
    };
  }, []);

  useEffect(() => {
    if (activeProject?.keyword && activeProject.keyword !== "你的研究方向关键词") {
      setLiteratureQuery(activeProject.keyword);
      setDirectionInput(activeProject.keyword);
    }
  }, [activeProject?.id, activeProject?.keyword]);

  useEffect(() => {
    if (!paperRows.length) {
      setSelectedPaperId("");
      return;
    }
    if (!paperRows.some((paper) => paper.id === selectedPaperId)) {
      setSelectedPaperId(paperRows[0].id);
    }
  }, [paperRows, selectedPaperId]);

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

    const guard = beginRequest("artifact");
    getArtifact(summary.id, { signal: guard.signal })
      .then((artifact) => {
        if (!guard.isCurrent()) {
          return;
        }
        setProjectArtifacts((items) => upsertArtifactDetail(items, artifact));
        setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(artifact)));
        setLastSavedArtifact(artifact);
      })
      .catch((error) => {
        if (!guard.isCurrent() || isAbortError(error)) {
          return;
        }
        setLastSavedArtifact(null);
      })
      .finally(guard.finish);
  }, [activeView, projectArtifacts, projectArtifactSummaries]);

  const activeArtifact = lastSavedArtifact
    ? {
        title: lastSavedArtifact.title,
        markdown: lastSavedArtifact.content_markdown,
        json: lastSavedArtifact.content_json,
        diff: lastSavedArtifact.diff,
      }
    : emptyArtifactForView(activeView);

  useEffect(() => {
    setArtifactDraft(activeArtifact);
  }, [activeArtifact.title, activeArtifact.markdown, activeArtifact.json, activeArtifact.diff]);

  const workflowSteps = useMemo(
    () =>
      buildWorkflowSteps({
        apiStatus,
        activeProject,
        paperRows,
        literatureBusy,
        literatureErrors,
        literatureCoverage,
        directionBusy,
        directionReview,
        paperCardBusy,
        latestPaperCard,
        memoryBusy,
        memoryResult,
        decisionBusy,
        researchDecision,
        backendWorkflowSteps,
      }),
    [
      activeProject,
      apiStatus,
      backendWorkflowSteps,
      decisionBusy,
      directionBusy,
      directionReview,
      latestPaperCard,
      literatureCoverage,
      literatureBusy,
      literatureErrors,
      memoryBusy,
      memoryResult,
      paperCardBusy,
      paperRows,
      researchDecision,
    ],
  );

  const warnings = useMemo(
    () =>
      buildWorkflowWarnings({
        apiStatus,
        apiMessage,
        hydrationWarnings,
        literatureErrors,
        directionReview,
        memoryResult,
        agentRunWarnings,
        researchDecision,
      }),
    [
      agentRunWarnings,
      apiMessage,
      apiStatus,
      hydrationWarnings,
      literatureErrors,
      directionReview,
      memoryResult,
      researchDecision,
    ],
  );

  async function loadWorkspace(guard: RequestGuard) {
    try {
      await getHealth({ signal: guard.signal });
      const loadedProjects = await listProjects({ signal: guard.signal });
      if (!guard.isCurrent()) {
        return;
      }

      const firstProject = selectInitialProject(loadedProjects);
      setApiStatus("online");
      setProjects(loadedProjects);
      setActiveProject(firstProject);
      setApiMessage(firstProject ? "API 已连接，正在使用 SQLite 工作区。" : "API 已连接，尚未创建项目。");
      if (firstProject && !isDemoProject(firstProject.id)) {
        storeActiveProjectId(firstProject.id);
      }

      if (firstProject) {
        await loadProjectResources(firstProject.id, guard);
      }
    } catch (error) {
      if (!guard.isCurrent() || isAbortError(error)) {
        return;
      }
      resetRuntimeResources();
      setApiStatus("offline");
      setApiMessage(formatApiFailure(error, "API 未连接，请先启动 ScholarFlow 后端服务。"));
    }
  }

  async function loadProjectResources(projectId: string, outerGuard?: RequestGuard) {
    const guard = outerGuard ?? beginRequest("resources");
    try {
      const [apiPapers, apiTimeline, artifactSummaries] = await Promise.all([
        listProjectPapers(projectId, { signal: guard.signal }),
        getProjectTimeline(projectId, { signal: guard.signal }),
        listProjectArtifactSummaries(projectId, { signal: guard.signal }),
      ]);

      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }

      const apiArtifacts = await loadHydrationArtifacts(artifactSummaries, { signal: guard.signal });
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }

      applyProjectResources(projectId, apiPapers, apiTimeline, artifactSummaries, apiArtifacts);
    } catch (error) {
      if (!guard.isCurrent() || isAbortError(error)) {
        return;
      }
      setApiMessage(formatApiFailure(error, "读取项目资源失败，请确认 API 与 SQLite 工作区可用。"));
    } finally {
      if (!outerGuard) {
        guard.finish();
      }
    }
  }

  function applyProjectResources(
    projectId: string,
    apiPapers: ApiPaper[],
    apiTimeline: Awaited<ReturnType<typeof getProjectTimeline>>,
    artifactSummaries: ApiArtifactSummary[],
    apiArtifacts: ApiArtifact[],
  ) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    setPaperRows(apiPapers.filter((paper) => !isSeedLikePaper(paper)).map(toPaperRow));
    setTimelineRows(apiTimeline.map(toTimelineEvent));
    setPersistedArtifactCount(artifactSummaries.length);
    setProjectArtifactSummaries(artifactSummaries);
    setProjectArtifacts(apiArtifacts);
    setLastSavedArtifact(selectArtifactForView(apiArtifacts, activeView));
    setHydrationWarnings(collectArtifactHydrationWarnings(apiArtifacts));
    const restored = hydrateWorkflowStateFromArtifacts(apiArtifacts);
    if (Object.keys(restored.literatureCoverage).length) {
      setLiteratureCoverage(restored.literatureCoverage);
    }
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
    setHydrationWarnings([]);
    setBackendWorkflowSteps([]);
    setLiteratureCoverage({});
  }

  function resetRuntimeResources() {
    setPaperRows([]);
    setTimelineRows([]);
    setProjectArtifacts([]);
    setProjectArtifactSummaries([]);
    setPersistedArtifactCount(0);
    setLastSavedArtifact(null);
    resetWorkflowState();
  }

  async function handleSelectProject(projectId: string) {
    cancelLongRequests();
    const project = projects.find((item) => item.id === projectId) ?? null;
    setActiveProject(project);
    activeProjectIdRef.current = project?.id ?? null;
    storeActiveProjectId(project && !isDemoProject(project.id) ? project.id : null);
    resetRuntimeResources();

    if (!project) {
      return;
    }

    setApiMessage(`正在切换项目: ${project.title}`);
    const guard = beginRequest("resources");
    await loadProjectResources(project.id, guard);
    if (guard.isCurrent()) {
      setApiMessage(`已切换项目: ${project.title}`);
    }
    guard.finish();
  }

  async function handleCreateProject() {
    const keyword = projectDraft.keyword.trim();
    if (!keyword) {
      setApiMessage("请先输入你想研究的方向或关键词。");
      return;
    }

    const guard = beginRequest("resources");
    const title = projectDraft.title.trim() || keyword;
    const description =
      projectDraft.description.trim() || `围绕「${keyword}」检索论文、精读论文、生成 gap 和实验计划。`;
    const field = projectDraft.field.trim() || "Artificial Intelligence";

    setApiMessage("正在创建本地 research project...");
    try {
      const project = await createProject(
        {
          title,
          description,
          keyword,
          field,
          language: "zh-CN",
          workflow: "survey-to-experiment",
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent()) {
        return;
      }
      const nextProjects = [project, ...projects.filter((item) => item.id !== project.id)];
      setApiStatus("online");
      setProjects(nextProjects);
      setActiveProject(project);
      activeProjectIdRef.current = project.id;
      resetWorkflowState();
      storeActiveProjectId(project.id);
      onSelectView("paper-table");
      setLiteratureQuery(keyword);
      setDirectionInput(keyword);
      setAgentTask(`请基于「${keyword}」方向，生成一个从文献检索到可验证 gap 的最小科研任务计划。`);
      setApiMessage(`已创建项目并初始化 session: ${project.id}`);
      await loadProjectResources(project.id, guard);
    } catch (error) {
      if (isAbortError(error) || !guard.isCurrent()) {
        return;
      }
      setApiStatus("offline");
      setApiMessage(formatApiFailure(error, "创建项目失败，请确认 API 服务是否运行在 127.0.0.1:8000。"));
    } finally {
      guard.finish();
    }
  }

  async function handleSaveArtifact() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const guard = beginRequest("artifact");
    const artifactToSave = artifactDraft ?? activeArtifact;
    setArtifactSaving(true);
    setApiMessage("正在保存右侧 Artifact 编辑内容到 SQLite...");
    try {
      const saved = await saveArtifact(
        {
          project_id: activeProject.id,
          title: artifactToSave.title,
          kind: artifactTab,
          content_markdown: artifactToSave.markdown,
          content_json: artifactToSave.json,
          diff: artifactToSave.diff,
        },
        { signal: guard.signal },
      );
      const reloaded = await getArtifact(saved.id, { signal: guard.signal });
      if (!guard.isCurrent() || activeProjectIdRef.current !== activeProject.id) {
        return;
      }
      setLastSavedArtifact(reloaded);
      setApiMessage(`Artifact 已保存并回读: ${reloaded.id}`);
      const refreshedTimeline = await getProjectTimeline(activeProject.id, { signal: guard.signal });
      if (!guard.isCurrent() || activeProjectIdRef.current !== activeProject.id) {
        return;
      }
      setTimelineRows(refreshedTimeline.map(toTimelineEvent));
      setProjectArtifacts((items) => upsertArtifactDetail(items, reloaded));
      setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(reloaded)));
      setPersistedArtifactCount((count) => Math.max(count, projectArtifactSummaries.length + 1));
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "保存 artifact 失败，请确认 API 与 SQLite 工作区可用。"));
      }
    } finally {
      setArtifactSaving(false);
      guard.finish();
    }
  }

  async function handleLoadArtifact(artifactId: string) {
    if (!artifactId) {
      return;
    }
    const guard = beginRequest("artifact");
    try {
      const artifact = await getArtifact(artifactId, { signal: guard.signal });
      if (!guard.isCurrent()) {
        return;
      }
      setLastSavedArtifact(artifact);
      setProjectArtifacts((items) => upsertArtifactDetail(items, artifact));
      setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(artifact)));
      setArtifactTab("markdown");
      setApiMessage(`已回读完整 artifact: ${artifact.title}`);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "读取 artifact 失败，请确认后端 API 与 SQLite 工作区可用。"));
      }
    } finally {
      guard.finish();
    }
  }

  async function handleCreateAgentPlan() {
    if (!activeProject) {
      setApiMessage("没有可运行的项目，请先创建项目或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("agent");
    setAgentBusy(true);
    setApiMessage("正在生成 Research Plan...");
    try {
      const plan = await createAgentPlan(
        {
          project_id: projectId,
          task: agentTask,
          provider: "openrouter",
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setAgentPlan(plan);
      setAgentRunWarnings([]);
      setLastSavedArtifact(plan.artifact);
      setApiMessage(`Research Plan 已生成，run: ${plan.run_id}`);
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "生成 Research Plan 失败，请确认 API 与 SQLite 工作区可用。"));
      }
    } finally {
      setAgentBusy(false);
      guard.finish();
    }
  }

  async function handleExecuteAgentRun() {
    if (!agentPlan) {
      setApiMessage("请先生成 Research Plan。");
      return;
    }
    if (isDemoProject(agentPlan.project_id) || isDemoProject(activeProject)) {
      blockDemoProjectAction();
      return;
    }

    const guard = beginRequest("agent");
    setAgentBusy(true);
    const stopProgress = startProgressMessages([
      "Agent Run: 正在执行文献检索工具...",
      "Agent Run: 正在生成方向精读与 Paper Memory...",
      "Agent Run: 正在生成 Gap Board、Experiment Plan 并保存 artifact...",
    ]);
    try {
      const result = await executeAgentRun(agentPlan.run_id, { confirmed: true }, { signal: guard.signal });
      if (!guard.isCurrent() || activeProjectIdRef.current !== agentPlan.project_id) {
        return;
      }
      setAgentPlan({
        ...agentPlan,
        status: result.status,
        steps: result.steps,
        artifact: result.artifact,
      });
      setAgentRunWarnings(result.warnings ?? []);
      setLastSavedArtifact(result.artifact);
      applyBackendWorkflowSteps(result.workflow_steps);
      setApiMessage(
        result.run_status_summary
          ? `Agent Run ${result.run_status_summary} artifact: ${result.artifact.id}`
          : `Agent Run 已完成，artifact: ${result.artifact.id}`,
      );
      await loadProjectResources(agentPlan.project_id, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "执行 Agent Run 失败，请查看 API 日志。"));
      }
    } finally {
      stopProgress();
      setAgentBusy(false);
      guard.finish();
    }
  }

  async function handleSearchLiterature() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("literature");
    setLiteratureBusy(true);
    setLiteratureErrors([]);
    setLiteratureCoverage({});
    setPaperRows([]);
    const stopProgress = startProgressMessages([
      "Literature Search: 正在扩展关键词并查询 arXiv / OpenAlex...",
      "Literature Search: 正在去重、排序并检查低召回...",
      "Literature Search: 正在保存 Paper Table artifact 到 SQLite...",
    ]);
    try {
      const result = await searchProjectLiterature(
        projectId,
        {
          query: literatureQuery,
          max_results: 12,
          sources: ["arxiv", "openalex"],
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setPaperRows(result.papers.filter((paper) => !isSeedLikePaper(paper)).map(toPaperRow));
      setLastSavedArtifact(result.artifact);
      setLiteratureErrors(result.errors);
      setLiteratureCoverage(result.relevance_coverage ?? {});
      applyBackendWorkflowSteps(result.workflow_steps);
      setApiMessage(
        result.relevance_coverage
          ? `检索完成：${result.relevance_coverage.candidate_count ?? result.papers.length} candidates / ${result.relevance_coverage.strong_match_count ?? 0} strong matches / ${result.relevance_coverage.off_topic_count ?? 0} off-topic filtered，artifact: ${result.artifact.id}`
          : `检索完成：${result.papers.length} 篇论文，artifact: ${result.artifact.id}`,
      );
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setPaperRows([]);
        setLiteratureErrors(["文献检索请求失败。请检查网络、OpenAlex/arXiv 可用性或 API 日志。"]);
        setLiteratureCoverage({});
        setApiMessage(formatApiFailure(error, "文献检索失败，请检查网络、OpenAlex/arXiv 可用性或 API 日志。"));
      }
    } finally {
      stopProgress();
      setLiteratureBusy(false);
      guard.finish();
    }
  }

  async function handleGeneratePaperCard() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const selectedPaper = paperRows.find((paper) => paper.id === selectedPaperId) ?? paperRows[0];
    if (!selectedPaper && !paperCardInput.trim()) {
      setApiMessage("请先选择一篇论文，或粘贴摘要/正文片段。");
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("paper-card");
    setPaperCardBusy(true);
    setApiMessage("正在生成 12 段 Deep Paper Card...");
    try {
      const result = await createProjectPaperCard(
        projectId,
        {
          paper_id: selectedPaper?.id,
          title: selectedPaper?.title,
          abstract: selectedPaper?.abstract,
          paper_text: paperCardInput,
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setLatestPaperCard(result.card);
      setLastSavedArtifact(result.artifact);
      setApiMessage(`Deep Paper Card 已生成，artifact: ${result.artifact.id}`);
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "生成 Deep Paper Card 失败，请确认论文属于当前项目，或粘贴足够的摘要/正文。"));
      }
    } finally {
      setPaperCardBusy(false);
      guard.finish();
    }
  }

  async function handleCreateDirectionReview() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("direction");
    setDirectionBusy(true);
    const stopProgress = startProgressMessages([
      `Direction Review: 正在界定第 ${directionRound} 轮研究方向范围...`,
      "Direction Review: 正在检索候选池并构建 BaselineMap...",
      "Direction Review: 正在生成 10 篇 Paper Card、ResearchSight 和 Paper Memory...",
      "Direction Review: 正在保存 artifacts；如果检索源限流，会标记 partial 或 warning。",
    ]);
    try {
      const result = await createDirectionReview(
        projectId,
        {
          direction: directionInput,
          round: directionRound,
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setDirectionReview(result);
      setSelectedDirectionPaperId("");
      applyBackendWorkflowSteps(result.workflow_steps);
      const reviewArtifactRef =
        result.artifact_refs.find((artifact) => artifact.title.toLowerCase().includes("direction_review")) ??
        result.artifact_refs[0];
      if (reviewArtifactRef) {
        const artifact = await getArtifact(reviewArtifactRef.id, { signal: guard.signal });
        if (guard.isCurrent() && activeProjectIdRef.current === projectId) {
          setLastSavedArtifact(artifact);
          setProjectArtifacts((items) => upsertArtifactDetail(items, artifact));
          setProjectArtifactSummaries((items) => upsertArtifactSummary(items, artifactSummaryFromDetail(artifact)));
          setArtifactTab("markdown");
        }
      }
      setApiMessage(
        result.review_status !== "complete"
          ? `方向精读 ${result.review_status}：第 ${result.round} 轮仅读取 ${result.relevant_read_count ?? result.round_read_count}/${result.target_paper_count} 篇强/中相关论文，off-topic=${result.off_topic_count ?? 0}。`
          : `方向精读完成：第 ${result.round} 轮，累计 ${result.total_read_count} 篇。`,
      );
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        const normalized = normalizeApiError(error);
        setApiMessage(
          normalized.kind === "timeout"
            ? "方向精读超时。建议稍后重试，或先只运行 Literature Search。"
            : formatApiFailure(error, "方向精读失败，请检查网络、检索源可用性或 API 日志。"),
        );
      }
    } finally {
      stopProgress();
      setDirectionBusy(false);
      guard.finish();
    }
  }

  async function handleQueryResearchMemory() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("memory");
    setMemoryBusy(true);
    const stopProgress = startProgressMessages([
      `Paper Memory: 正在从 SQLite memory bank 检索 ${memoryTopK} 篇相关论文...`,
      "Paper Memory: 正在按问题意图匹配 minimal reproduction、counterexample 和 ResearchSight 字段...",
      "Paper Memory: 正在保存 grounded answer artifact...",
    ]);
    try {
      const result = await queryResearchMemory(
        projectId,
        {
          question: memoryQuestion,
          direction: directionInput,
          top_k: memoryTopK,
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setMemoryResult(result);
      setLastSavedArtifact(result.artifact);
      applyBackendWorkflowSteps(result.workflow_steps);
      setApiMessage(`论文记忆回答已生成：命中 ${result.hits.length} 篇，memory bank 总量 ${result.total_memories}。`);
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "论文记忆检索失败，请先执行方向精读，或检查 API 日志。"));
      }
    } finally {
      stopProgress();
      setMemoryBusy(false);
      guard.finish();
    }
  }

  async function handleCreateResearchDecision() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("decision");
    setDecisionBusy(true);
    const stopProgress = startProgressMessages([
      "Research Decision: 正在读取 paper table 和 paper cards...",
      "Research Decision: 正在区分 true_gap / engineering_gap / pseudo_gap...",
      "Research Decision: 正在检查 claim、dataset、metric、baseline 与真实 anchor...",
    ]);
    try {
      const result = await createResearchDecisions(
        projectId,
        {
          goal: decisionGoal,
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setResearchDecision(result);
      setLastSavedArtifact(result.artifacts[result.artifacts.length - 1] ?? null);
      applyBackendWorkflowSteps(result.workflow_steps);
      setApiMessage(`研究决策已生成：${result.gaps.length} gaps + experiment plan`);
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "生成研究决策失败，请确认已有 paper table 或 paper card。"));
      }
    } finally {
      stopProgress();
      setDecisionBusy(false);
      guard.finish();
    }
  }

  function beginRequest(scope: RequestScope): RequestGuard {
    const previous = requestStateRef.current[scope];
    previous.controller?.abort("superseded");
    const controller = new AbortController();
    const requestId = previous.id + 1;
    requestStateRef.current[scope] = { id: requestId, controller };
    return {
      signal: controller.signal,
      isCurrent: () => requestStateRef.current[scope].id === requestId && !controller.signal.aborted,
      isAborted: () => controller.signal.aborted,
      finish: () => {
        if (requestStateRef.current[scope].id === requestId) {
          requestStateRef.current[scope].controller = null;
        }
      },
    };
  }

  function cancelLongRequests() {
    (["resources", "literature", "direction", "paper-card", "memory", "decision", "agent"] as RequestScope[]).forEach(
      (scope) => {
        requestStateRef.current[scope].controller?.abort("project-switch");
        requestStateRef.current[scope].controller = null;
      },
    );
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

  function applyBackendWorkflowSteps(steps: ApiWorkflowStepState[] | undefined) {
    if (!steps?.length) {
      return;
    }
    setBackendWorkflowSteps((current) => {
      const byStepId = new Map(current.map((step) => [step.step_id, step]));
      steps.forEach((step) => byStepId.set(step.step_id, step));
      return [...byStepId.values()];
    });
  }

  function blockDemoProjectAction() {
    setApiMessage("Demo 项目仅用于界面预览，不会运行或保存真实 workflow。请创建真实项目后再操作。");
  }

  const viewModel: WorkflowViewModel = {
    activeArtifact,
    activeProject,
    agentPlan,
    agentTask,
    apiMessage,
    apiStatus,
    artifactCount: persistedArtifactCount,
    artifactDraft,
    artifactSummaries: projectArtifactSummaries,
    artifactTab,
    busy: {
      agent: agentBusy,
      artifactSaving,
      decision: decisionBusy,
      direction: directionBusy,
      literature: literatureBusy,
      memory: memoryBusy,
      paperCard: paperCardBusy,
    },
    decisionGoal,
    directionInput,
    directionReview,
    directionRound,
    latestPaperCard,
    lastSavedArtifact,
    literatureErrors,
    literatureCoverage,
    literatureQuery,
    memoryQuestion,
    memoryResult,
    memoryTopK,
    paperCardInput,
    paperRows,
    projectCount: projects.length,
    projectDraft,
    projects,
    researchDecision,
    selectedDirectionPaperId,
    selectedPaperId,
    timelineRows,
    warnings,
    workflowSteps,
  };

  const actions: WorkflowActions = {
    onAgentTaskChange: setAgentTask,
    onArtifactChange: setArtifactDraft,
    onArtifactTabChange: setArtifactTab,
    onCreateAgentPlan: handleCreateAgentPlan,
    onCreateDirectionReview: handleCreateDirectionReview,
    onCreateProject: handleCreateProject,
    onCreateResearchDecision: handleCreateResearchDecision,
    onDecisionGoalChange: setDecisionGoal,
    onDirectionInputChange: setDirectionInput,
    onDirectionRoundChange: setDirectionRound,
    onExecuteAgentRun: handleExecuteAgentRun,
    onGeneratePaperCard: handleGeneratePaperCard,
    onLiteratureQueryChange: setLiteratureQuery,
    onLoadArtifact: handleLoadArtifact,
    onMemoryQuestionChange: setMemoryQuestion,
    onMemoryTopKChange: setMemoryTopK,
    onPaperCardInputChange: setPaperCardInput,
    onProjectDraftChange: setProjectDraft,
    onQueryResearchMemory: handleQueryResearchMemory,
    onSaveArtifact: handleSaveArtifact,
    onSearchLiterature: handleSearchLiterature,
    onSelectProject: handleSelectProject,
    onSelectedDirectionPaperChange: setSelectedDirectionPaperId,
    onSelectedPaperChange: setSelectedPaperId,
  };

  return { actions, viewModel };
}

function selectInitialProject(loadedProjects: ApiProject[]): ApiProject | null {
  const storedProjectId = readStoredActiveProjectId();
  const latestUserProject = loadedProjects.find((project) => !isDemoProject(project.id)) ?? null;
  const storedProject =
    loadedProjects.find((project) => {
      if (project.id !== storedProjectId) {
        return false;
      }
      return !isDemoProject(project.id);
    }) ?? null;
  return storedProject ?? latestUserProject;
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

function isDemoProject(projectOrId: ApiProject | string | undefined | null): boolean {
  if (!projectOrId) {
    return false;
  }
  if (typeof projectOrId === "string") {
    return projectOrId === "local-bootstrap";
  }
  return (
    projectOrId.is_demo === true ||
    projectOrId.id === "local-bootstrap" ||
    projectOrId.workflow === "demo-preview" ||
    projectOrId.stage === "seed" ||
    projectOrId.stage === "demo"
  );
}

function isSeedLikePaper(paper: ApiPaper | PaperRow): boolean {
  const source = paper.source.toLowerCase();
  const venue = paper.venue.toLowerCase();
  const code = paper.code.toLowerCase();
  const title = paper.title.toLowerCase();
  return source === "seed" || venue === "demo" || code === "demo" || title.startsWith("synthetic example:");
}

function formatApiFailure(error: unknown, fallback: string): string {
  const normalized = normalizeApiError(error);
  if (normalized.kind === "aborted") {
    return "";
  }
  if (normalized.kind === "timeout") {
    return `${fallback} 请求超时。`;
  }
  if (normalized.kind === "offline") {
    return `${fallback} API 未连接。`;
  }
  if (normalized.kind === "validation") {
    return `${fallback} 请求参数未通过后端校验：${normalized.detail}`;
  }
  if (normalized.kind === "retrieval-degraded") {
    return `${fallback} 外部检索源降级：${normalized.detail}`;
  }
  if (normalized.kind === "backend") {
    return `${fallback} 后端返回 5xx：${normalized.detail}`;
  }
  return normalized.detail ? `${fallback} ${normalized.detail}` : fallback;
}

function emptyArtifactForView(view: ViewId): ArtifactContent {
  return {
    title: `${workflowLabels[view]} Artifact`,
    markdown: "尚未加载真实 artifact。请运行当前步骤，或从右侧 Local Assets 选择已保存内容。",
    json: "{}",
    diff: "",
  };
}

function buildWorkflowSteps(input: {
  apiStatus: ApiStatus;
  activeProject: ApiProject | null;
  backendWorkflowSteps: ApiWorkflowStepState[];
  paperRows: PaperRow[];
  literatureBusy: boolean;
  literatureErrors: string[];
  literatureCoverage: RelevanceCoverage;
  directionBusy: boolean;
  directionReview: ApiDirectionReviewResponse | null;
  paperCardBusy: boolean;
  latestPaperCard: ApiPaperCard | null;
  memoryBusy: boolean;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  decisionBusy: boolean;
  researchDecision: ApiResearchDecisionResponse | null;
}): WorkflowStepView[] {
  const hasProject = Boolean(input.activeProject && !isDemoProject(input.activeProject.id));
  const hasPapers = input.paperRows.length > 0;
  const returnedCount = input.literatureCoverage.returned_count ?? input.paperRows.length;
  const hasCoverageWarnings =
    (input.literatureCoverage.off_topic_count ?? 0) > 0 ||
    (input.literatureCoverage.weak_match_count ?? 0) > 0 ||
    (hasPapers && returnedCount < 5);
  const directionStatus = input.directionReview?.review_status ?? null;
  const experimentStatus = input.researchDecision?.experiment?.status;
  const decisionStatus = input.researchDecision?.decision_status ?? "complete";
  const decisionEvidencePartial = isDecisionEvidencePartial(input.researchDecision);
  const updatedAt = input.activeProject?.updated_at ?? "";

  const localSteps: WorkflowStepView[] = [
    toWorkflowStepView({
      id: "new-project",
      label: "新建项目",
      summary: hasProject ? input.activeProject?.title ?? "项目已选择" : "先创建研究项目",
      status: input.apiStatus === "offline" ? "blocked" : hasProject ? "complete" : "ready",
      warnings: [],
      errors: input.apiStatus === "offline" ? ["API 未连接"] : [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "paper-table",
      label: "Paper Table",
      summary: hasPapers
        ? `${input.literatureCoverage.candidate_count ?? input.paperRows.length} candidates / ${returnedCount} returned / ${input.literatureCoverage.strong_match_count ?? 0} strong / ${input.literatureCoverage.medium_match_count ?? 0} medium`
        : "运行 Literature Search",
      status: resolveStepStatus({
        blocked: !hasProject || input.apiStatus === "offline",
        running: input.literatureBusy,
        partial: hasPapers && (input.literatureErrors.length > 0 || hasCoverageWarnings),
        complete: hasPapers,
      }),
      warnings: input.literatureErrors,
      errors: [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "direction-review",
      label: "Direction Review",
      summary: input.directionReview
        ? `${input.directionReview.relevant_read_count ?? input.directionReview.round_read_count}/${input.directionReview.target_paper_count} 强/中相关精读`
        : "每轮最多 10 篇方向精读",
      status: resolveStepStatus({
        running: input.directionBusy,
        partial: directionStatus === "partial",
        blocked: directionStatus === "blocked" || !hasProject || !hasPapers || input.apiStatus === "offline",
        complete: directionStatus === "complete",
      }),
      warnings: input.directionReview?.errors ?? [],
      errors: [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "paper-reader",
      label: "Deep Paper Card",
      summary: input.latestPaperCard ? `${input.latestPaperCard.sections.length} 个 section` : "选择论文生成 12 条阅读",
      status: resolveStepStatus({
        blocked: !hasProject || (!hasPapers && !input.latestPaperCard) || input.apiStatus === "offline",
        running: input.paperCardBusy,
        complete: Boolean(input.latestPaperCard),
        partial: Boolean(input.latestPaperCard && input.latestPaperCard.sections.length < 12),
      }),
      warnings: [],
      errors: [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "paper-memory",
      label: "Paper Memory",
      summary: input.memoryResult ? `${input.memoryResult.hits.length} 条命中` : "基于已读论文检索 3-8 篇",
      status: resolveStepStatus({
        blocked: !hasProject || !input.directionReview || input.apiStatus === "offline",
        running: input.memoryBusy,
        partial: Boolean(input.memoryResult && input.memoryResult.hits.length === 0),
        complete: Boolean(input.memoryResult && input.memoryResult.hits.length > 0),
      }),
      warnings: input.memoryResult?.warnings ?? [],
      errors: [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "gap-board",
      label: "Gap Board",
      summary: input.researchDecision ? `${input.researchDecision.gaps.length} 个 gap` : "生成 novelty / feasibility 判断",
      status: resolveStepStatus({
        blocked: !hasProject || (!hasPapers && !input.latestPaperCard) || input.apiStatus === "offline",
        running: input.decisionBusy,
        partial: Boolean(
          input.researchDecision &&
            (input.researchDecision.gaps.length === 0 || decisionStatus !== "complete" || decisionEvidencePartial),
        ),
        complete: Boolean(input.researchDecision && input.researchDecision.gaps.length > 0),
      }),
      warnings: input.researchDecision?.warnings ?? [],
      errors: [],
      updatedAt,
    }),
    toWorkflowStepView({
      id: "experiment-planner",
      label: "Experiment Plan",
      summary: experimentStatus === "blocked" ? "缺少可复现 anchor" : input.researchDecision ? "已生成实验计划" : "检查 anchor 后生成计划",
      status: resolveStepStatus({
        blocked: !hasProject || input.apiStatus === "offline" || experimentStatus === "blocked",
        running: input.decisionBusy,
        complete: Boolean(experimentStatus && experimentStatus !== "blocked"),
      }),
      warnings: input.researchDecision?.experiment?.unblock_suggestions ?? [],
      errors: [],
      updatedAt,
    }),
  ];

  return mergeBackendWorkflowSteps(localSteps, input.backendWorkflowSteps);
}

function isDecisionEvidencePartial(decision: ApiResearchDecisionResponse | null): boolean {
  const quality = decision?.evidence_quality;
  if (!quality) {
    return false;
  }
  const gapEvidenceCount = Number(quality.gap_evidence_paper_count ?? 0);
  const threshold = Number(quality.minimum_gap_evidence_threshold ?? 5);
  return Number.isFinite(gapEvidenceCount) && Number.isFinite(threshold) && gapEvidenceCount < threshold;
}

function toWorkflowStepView(input: {
  id: ViewId;
  label: string;
  status: WorkflowStepStatus;
  summary: string;
  warnings: string[];
  errors: string[];
  updatedAt: string;
}): WorkflowStepView {
  return {
    id: input.id,
    step_id: input.id,
    status: input.status,
    label: input.label,
    summary: input.summary,
    warnings: input.warnings,
    errors: input.errors,
    artifact_refs: [],
    updated_at: input.updatedAt,
  };
}

function mergeBackendWorkflowSteps(localSteps: WorkflowStepView[], backendSteps: ApiWorkflowStepState[]): WorkflowStepView[] {
  if (!backendSteps.length) {
    return localSteps;
  }
  const backendById = new Map(backendSteps.map((step) => [step.step_id, step]));
  return localSteps.map((localStep) => {
    const backendStep = backendById.get(localStep.step_id);
    if (!backendStep || !isViewId(backendStep.step_id)) {
      return localStep;
    }
    return {
      ...localStep,
      ...backendStep,
      id: backendStep.step_id,
      status: mergeWorkflowStatus(localStep.status, backendStep.status),
      warnings: backendStep.warnings ?? localStep.warnings,
      errors: backendStep.errors ?? localStep.errors,
      artifact_refs: backendStep.artifact_refs ?? localStep.artifact_refs,
    };
  });
}

function mergeWorkflowStatus(localStatus: WorkflowStepStatus, backendStatus: WorkflowStepStatus): WorkflowStepStatus {
  const severity: Record<WorkflowStepStatus, number> = {
    idle: 0,
    ready: 1,
    complete: 2,
    partial: 3,
    running: 4,
    blocked: 5,
    error: 6,
  };
  return severity[localStatus] > severity[backendStatus] ? localStatus : backendStatus;
}

function isViewId(value: string): value is ViewId {
  return value in workflowLabels;
}

function resolveStepStatus(input: {
  blocked?: boolean;
  running?: boolean;
  partial?: boolean;
  complete?: boolean;
}): WorkflowStepStatus {
  if (input.running) {
    return "running";
  }
  if (input.blocked) {
    return "blocked";
  }
  if (input.partial) {
    return "partial";
  }
  if (input.complete) {
    return "complete";
  }
  return "ready";
}

function buildWorkflowWarnings(input: {
  apiStatus: ApiStatus;
  apiMessage: string;
  agentRunWarnings: string[];
  hydrationWarnings: string[];
  literatureErrors: string[];
  directionReview: ApiDirectionReviewResponse | null;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  researchDecision: ApiResearchDecisionResponse | null;
}): WorkflowNotice[] {
  const notices: WorkflowNotice[] = [];
  if (input.apiStatus === "offline") {
    notices.push({ id: "api-offline", kind: "error", message: input.apiMessage || "API 未连接" });
  }
  input.hydrationWarnings.forEach((message, index) => {
    notices.push({ id: `hydration-${index}`, kind: "warning", message });
  });
  input.agentRunWarnings.forEach((message, index) => {
    notices.push({ id: `agent-run-${index}`, kind: "warning", message });
  });
  input.literatureErrors.forEach((message, index) => {
    notices.push({
      id: `literature-${index}`,
      kind: isRetrievalWarning(message) ? "warning" : "error",
      message,
    });
  });
  input.directionReview?.errors.forEach((message, index) => {
    notices.push({ id: `direction-${index}`, kind: "warning", message });
  });
  input.memoryResult?.warnings.forEach((message, index) => {
    notices.push({ id: `memory-${index}`, kind: "warning", message });
  });
  input.researchDecision?.experiment?.unblock_suggestions.forEach((message, index) => {
    notices.push({ id: `experiment-unblock-${index}`, kind: "warning", message });
  });
  input.researchDecision?.warnings?.forEach((message, index) => {
    notices.push({ id: `decision-warning-${index}`, kind: "warning", message });
  });
  return notices.slice(0, 8);
}
