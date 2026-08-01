import { useEffect, useMemo, useState } from "react";
import type {
  ApiArtifact,
  ApiArtifactSummary,
  ApiDirectionReviewResponse,
  ApiDirectionReviewRunStatusResponse,
  ApiPaper,
  ApiPaperCard,
  ApiProject,
  ApiRagAnswerResponse,
  ApiResearchDecisionResponse,
  ApiResearchMemoryQueryResponse,
  ApiWorkflowStepState,
} from "@scholarflow/schemas";
import { isAbortError, isRetrievalWarning, normalizeApiError } from "../apiClient";
import { getArtifact, saveArtifact } from "../services/artifactService";
import { searchProjectLiterature } from "../services/literatureService";
import {
  createProjectPaperCard,
  extractProjectPaperFullText,
} from "../services/paperService";
import {
  createProject,
  getHealth,
  getProjectTimeline,
  listProjects,
} from "../services/projectService";
import { askProjectRag } from "../services/ragService";
import {
  createResearchDecisions,
  queryResearchMemory,
} from "../services/researchService";
import type { ArtifactContent, PaperRow, TimelineEvent, ViewId } from "../mockData";
import {
  artifactSummaryFromDetail,
  collectArtifactHydrationWarnings,
  hydrateWorkflowStateFromArtifacts,
  preferPaperCard,
  resolvePaperCardForPaper,
  selectArtifactForView,
  toPaperRow,
  toTimelineEvent,
  upsertArtifactDetail,
  upsertArtifactSummary,
} from "../lib/artifactHydration";
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
import {
  useRequestCoordinator,
  type RequestGuard,
  type RequestScope,
} from "./useRequestCoordinator";
import { useAgentRunController } from "./useAgentRunController";
import {
  isTerminalDirectionRunStatus,
  useDirectionReviewController,
} from "./useDirectionReviewController";
import {
  fetchProjectResourceSnapshot,
  useProjectResources,
  type ProjectResourceSnapshot,
} from "./useProjectResources";

const ACTIVE_PROJECT_STORAGE_KEY = "scholarflow.activeProjectId";

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
  const [literatureQuery, setLiteratureQuery] = useState("");
  const [literatureBusy, setLiteratureBusy] = useState(false);
  const [literatureErrors, setLiteratureErrors] = useState<string[]>([]);
  const [literatureCoverage, setLiteratureCoverage] = useState<RelevanceCoverage>({});
  const [memoryQuestion, setMemoryQuestion] = useState("这个方向最值得做的一周验证实验是什么？");
  const [memoryTopK, setMemoryTopK] = useState(5);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryResult, setMemoryResult] = useState<ApiResearchMemoryQueryResponse | null>(null);
  const [memoryMessage, setMemoryMessage] = useState("结构化记忆尚未查询。");
  const [ragBusy, setRagBusy] = useState(false);
  const [ragAnswer, setRagAnswer] = useState<ApiRagAnswerResponse | null>(null);
  const [ragQuestion, setRagQuestion] = useState("原文中有哪些直接证据支持或反驳这个研究判断？");
  const [ragTopK, setRagTopK] = useState(5);
  const [ragMessage, setRagMessage] = useState("原文 RAG 尚未查询。");
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [paperCardInput, setPaperCardInput] = useState("");
  const [paperCardBusy, setPaperCardBusy] = useState(false);
  const [latestPaperCard, setLatestPaperCard] = useState<ApiPaperCard | null>(null);
  const [paperCards, setPaperCards] = useState<ApiPaperCard[]>([]);
  const [decisionGoal, setDecisionGoal] = useState(
    "基于当前 paper table 和 paper card，找出最值得做的一周最小实验方向。",
  );
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [researchDecision, setResearchDecision] = useState<ApiResearchDecisionResponse | null>(null);
  const [hydrationWarnings, setHydrationWarnings] = useState<string[]>([]);
  const [backendWorkflowSteps, setBackendWorkflowSteps] = useState<ApiWorkflowStepState[]>([]);

  const { activeProjectIdRef, beginRequest, cancelRequests } =
    useRequestCoordinator(activeProject?.id ?? null);
  const {
    applyRunSnapshot: applyDirectionRunSnapshot,
    createDirectionReview: handleCreateDirectionReview,
    directionBusy,
    directionInput,
    directionMessage,
    directionReview,
    directionRound,
    directionRun,
    hydrateReview: hydrateDirectionReview,
    reset: resetDirectionReview,
    selectedDirectionPaperId,
    setDirectionInput,
    setDirectionRound,
    setSelectedDirectionPaperId,
    startPolling: startDirectionRunPolling,
    stopPolling: stopDirectionPolling,
  } = useDirectionReviewController({
    activeProject,
    activeProjectIdRef,
    applyBackendWorkflowSteps,
    beginDirectionRequest: () => beginRequest("direction"),
    blockDemoProjectAction,
    formatApiFailure,
    isDemoProject,
    onArtifact: (artifact) => {
      setLastSavedArtifact(artifact);
      setProjectArtifacts((items) =>
        upsertArtifactDetail(items, artifact),
      );
      setProjectArtifactSummaries((items) =>
        upsertArtifactSummary(
          items,
          artifactSummaryFromDetail(artifact),
        ),
      );
      setArtifactTab("markdown");
    },
    onProjectResources: applyProjectResources,
    setApiMessage,
  });
  const { loadProjectResources } = useProjectResources({
    activeProjectIdRef,
    beginResourceRequest: () => beginRequest("resources"),
    onLoadError: (error) => {
      setApiMessage(
        formatApiFailure(
          error,
          "读取项目资源失败，请确认 API 与 SQLite 工作区可用。",
        ),
      );
    },
    onSnapshot: (projectId, snapshot) => {
      applyProjectResources(projectId, snapshot);
      if (
        snapshot.directionRun &&
        !isTerminalDirectionRunStatus(snapshot.directionRun.status)
      ) {
        startDirectionRunPolling(
          snapshot.directionRun.run_id,
          projectId,
        );
      }
    },
  });
  const {
    agentBusy,
    agentPlan,
    agentRunStatus,
    agentRunWarnings,
    agentTask,
    cancelRun: handleCancelAgentRun,
    createPlan: handleCreateAgentPlan,
    executeRun: handleExecuteAgentRun,
    reset: resetAgentRun,
    setAgentTask,
    stopPolling: stopAgentPolling,
  } = useAgentRunController({
    activeProject,
    activeProjectIdRef,
    applyBackendWorkflowSteps,
    beginAgentRequest: () => beginRequest("agent"),
    blockDemoProjectAction,
    formatApiFailure,
    isDemoProject,
    loadProjectResources: (projectId, guard) =>
      loadProjectResources(projectId, guard),
    onArtifact: (artifact) => {
      setLastSavedArtifact(artifact);
      setProjectArtifacts((items) =>
        upsertArtifactDetail(items, artifact),
      );
      setProjectArtifactSummaries((items) =>
        upsertArtifactSummary(
          items,
          artifactSummaryFromDetail(artifact),
        ),
      );
    },
    refreshProjectResources: refreshAgentProjectResources,
    setApiMessage,
  });

  useEffect(() => {
    const guard = beginRequest("workspace");
    loadWorkspace(guard);
    return () => {
      stopAgentPolling();
      stopDirectionPolling();
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

  const selectedPaper = paperRows.find((paper) => paper.id === selectedPaperId) ?? paperRows[0];
  const effectivePaperCard = useMemo(() => {
    const candidates = latestPaperCard ? [latestPaperCard, ...paperCards] : paperCards;
    const match = resolvePaperCardForPaper(candidates, directionReview, selectedPaper);
    return match?.card ?? (!selectedPaper ? latestPaperCard : null);
  }, [directionReview, latestPaperCard, paperCards, selectedPaper]);

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
        directionRun,
        paperCardBusy,
        latestPaperCard: effectivePaperCard,
        selectedPaperId,
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
      directionRun,
      effectivePaperCard,
      selectedPaperId,
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
        directionRun,
        memoryResult,
        ragAnswer,
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
      directionRun,
      memoryResult,
      ragAnswer,
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
      activeProjectIdRef.current = firstProject?.id ?? null;
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

  function applyProjectResources(
    projectId: string,
    snapshot: ProjectResourceSnapshot,
  ) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    if (snapshot.papers) {
      setPaperRows(snapshot.papers.filter((paper) => !isSeedLikePaper(paper)).map(toPaperRow));
    }
    if (snapshot.timeline) {
      setTimelineRows(snapshot.timeline.map(toTimelineEvent));
    }
    if (snapshot.artifactSummaries) {
      setPersistedArtifactCount(snapshot.artifactSummaries.length);
      setProjectArtifactSummaries(snapshot.artifactSummaries);
    }
    if (snapshot.paperCards) {
      setPaperCards(snapshot.paperCards);
    }
    if (snapshot.directionRun !== undefined) {
      applyDirectionRunSnapshot(projectId, snapshot.directionRun);
    }
    if (!snapshot.artifacts) {
      setHydrationWarnings(snapshot.warnings);
      return;
    }

    const apiArtifacts = snapshot.artifacts;
    setProjectArtifacts(apiArtifacts);
    setLastSavedArtifact(selectArtifactForView(apiArtifacts, activeView));
    setHydrationWarnings([...snapshot.warnings, ...collectArtifactHydrationWarnings(apiArtifacts)]);
    const restored = hydrateWorkflowStateFromArtifacts(apiArtifacts);
    if (Object.keys(restored.literatureCoverage).length) {
      setLiteratureCoverage(restored.literatureCoverage);
    }
    if (restored.directionReview) {
      // The saved review direction is the identity of the memory scope. Project
      // keywords are only a search default and may differ from the direction
      // that produced the persisted paper memories.
      hydrateDirectionReview(restored.directionReview);
    }
    if (restored.memoryResult) {
      setMemoryResult(restored.memoryResult);
      if (restored.memoryResult.question.trim()) {
        setMemoryQuestion(restored.memoryResult.question);
      }
      setMemoryTopK(restored.memoryResult.top_k);
    }
    if (restored.ragAnswer) {
      setRagAnswer(restored.ragAnswer);
      if (restored.ragAnswer.question.trim()) {
        setRagQuestion(restored.ragAnswer.question);
      }
    }
    if (restored.paperCard) {
      // A refresh can hydrate an older abstract card for the same paper. Do not
      // downgrade a verified uploaded-PDF card while project resources reload.
      setLatestPaperCard((current) => preferPaperCard(current, restored.paperCard));
      setPaperCards((current) => upsertPaperCard(current, restored.paperCard as ApiPaperCard));
    }
    if (restored.researchDecision) {
      setResearchDecision(restored.researchDecision);
      const restoredGoal = restored.researchDecision.decision_intent?.raw_goal?.trim();
      if (restoredGoal) {
        setDecisionGoal(restoredGoal);
      }
    }
  }

  function resetWorkflowState() {
    resetAgentRun();
    resetDirectionReview();
    setLiteratureBusy(false);
    setLiteratureErrors([]);
    setMemoryResult(null);
    setMemoryBusy(false);
    setMemoryMessage("结构化记忆尚未查询。");
    setRagAnswer(null);
    setRagBusy(false);
    setRagMessage("原文 RAG 尚未查询。");
    setResearchDecision(null);
    setDecisionBusy(false);
    setLatestPaperCard(null);
    setPaperCards([]);
    setSelectedPaperId("");
    setPaperCardBusy(false);
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
          ? `检索完成：${result.relevance_coverage.candidate_count ?? result.papers.length} 篇候选 / ${result.relevance_coverage.eligible_count ?? result.papers.length} 篇通过门槛 / ${result.relevance_coverage.returned_count ?? result.papers.length} 篇实际展示，artifact: ${result.artifact.id}`
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
      setPaperCards((current) => upsertPaperCard(current, result.card));
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

  async function handlePaperPdfUpload(paperId: string, file: File) {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }
    const paper = paperRows.find((item) => item.id === paperId);
    if (!paper) {
      setApiMessage("当前项目中没有找到这篇论文，无法绑定上传的 PDF。");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf") && file.type !== "application/pdf") {
      setApiMessage("请选择 PDF 文件。");
      return;
    }
    if (file.size === 0 || file.size > 20 * 1024 * 1024) {
      setApiMessage("PDF 必须大于 0 字节且不超过 20 MB。");
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("paper-card");
    setPaperCardBusy(true);
    setApiMessage(`正在解析 PDF 并重建 Paper Card：${file.name}`);
    try {
      const extraction = await extractProjectPaperFullText(projectId, paperId, file, { signal: guard.signal });
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      if (
        extraction.full_text.status !== "extracted" ||
        extraction.evidence_qualification.level !== "full_text" ||
        !extraction.evidence_qualification.verified ||
        !extraction.text.trim() ||
        !extraction.card ||
        !extraction.artifact
      ) {
        setApiMessage(
          extraction.full_text.error || "PDF 没有可解析的文本层；请改用可复制文本的 PDF，或粘贴正文片段。",
        );
        return;
      }
      const uploadedCard = extraction.card;
      setLatestPaperCard({
        ...uploadedCard,
        paper_id: uploadedCard.paper_id || paperId,
        paper_title: uploadedCard.paper_title || paper.title,
        evidence_level: extraction.evidence_qualification.level,
        evidence_qualification: extraction.evidence_qualification,
        full_text: extraction.full_text,
        updated_at: extraction.updated_at || uploadedCard.updated_at || uploadedCard.created_at,
      });
      setPaperCards((current) =>
        upsertPaperCard(current, {
          ...uploadedCard,
          paper_id: uploadedCard.paper_id || paperId,
          paper_title: uploadedCard.paper_title || paper.title,
          evidence_level: extraction.evidence_qualification.level,
          evidence_qualification: extraction.evidence_qualification,
          full_text: extraction.full_text,
          updated_at: extraction.updated_at || uploadedCard.created_at,
        } as ApiPaperCard),
      );
      setLastSavedArtifact(extraction.artifact);
      setPaperCardInput("");
      setApiMessage(
        `PDF 已解析 ${extraction.full_text.page_count} 页 / ${extraction.full_text.character_count.toLocaleString("zh-CN")} 字符，全文级 Paper Card 已更新。`,
      );
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(formatApiFailure(error, "PDF 解析或 Paper Card 生成失败，请检查文件文本层与 API 日志。"));
      }
    } finally {
      setPaperCardBusy(false);
      guard.finish();
    }
  }

  async function handleQueryResearchMemory() {
    if (!activeProject) {
      setMemoryMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("memory");
    setMemoryBusy(true);
    const stopProgress = startOperationMessages(setMemoryMessage, [
      `Paper Memory: 正在从 SQLite memory bank 检索 ${memoryTopK} 篇相关论文...`,
      "Paper Memory: 正在按问题意图匹配 minimal reproduction、counterexample 和 ResearchSight 字段...",
      "Paper Memory: 正在保存 grounded answer artifact...",
    ]);
    try {
      const result = await queryResearchMemory(
        projectId,
        {
          question: memoryQuestion,
          // Query the memory scope that actually produced the persisted cards.
          // When no review has been restored yet, omit the direction so the API
          // can use the project's latest/only memory scope safely.
          direction: directionReview?.direction?.trim() || undefined,
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
      setMemoryMessage(
        result.reliability_status === "no_reliable_hit"
          ? "当前记忆没有可靠证据回答此问题。建议重新检索或补充 PDF。"
          : `论文记忆回答已生成：命中 ${result.hits.length} 篇，memory bank 总量 ${result.total_memories}。`,
      );
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setMemoryMessage(formatApiFailure(error, "论文记忆检索失败，请先执行方向精读，或检查 API 日志。"));
      }
    } finally {
      stopProgress();
      setMemoryBusy(false);
      guard.finish();
    }
  }

  async function handleQueryRag() {
    if (!activeProject) {
      setRagMessage("没有可检索的后端项目，请先创建或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginRequest("rag");
    setRagBusy(true);
    const stopProgress = startOperationMessages(setRagMessage, [
      `原文 RAG: 正在检索最多 ${ragTopK} 个项目内论文 chunk...`,
      "原文 RAG: 正在核对 section、页码、证据等级与 citation ID...",
      "原文 RAG: 正在校验每条主张是否具有有效引用...",
    ]);
    try {
      const result = await askProjectRag(
        projectId,
        {
          query: ragQuestion,
          top_k: ragTopK,
          evidence_levels: ["abstract_only", "full_text"],
          min_score: 0.18,
          max_chunks_per_paper: 3,
          refresh_embeddings: true,
          language: "zh-CN",
        },
        { signal: guard.signal },
      );
      if (!guard.isCurrent() || activeProjectIdRef.current !== projectId) {
        return;
      }
      setRagAnswer(result);
      if (result.artifact) {
        setLastSavedArtifact(result.artifact);
      }
      setRagMessage(
        result.status === "no_reliable_hit"
          ? "原文索引没有达到门槛的证据，系统已拒绝生成回答。"
          : `原文 RAG 已返回 ${result.citations.length} 条引用、${result.claims.length} 条通过校验的主张。`,
      );
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setRagMessage(formatApiFailure(error, "原文 RAG 问答失败，请检查索引、embedding 配置或 API 日志。"));
      }
    } finally {
      stopProgress();
      setRagBusy(false);
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

  function cancelLongRequests() {
    stopAgentPolling();
    stopDirectionPolling();
    cancelRequests([
      "resources",
      "literature",
      "direction",
      "paper-card",
      "memory",
      "rag",
      "decision",
      "agent",
    ] satisfies RequestScope[]);
  }

  function startProgressMessages(messages: string[], intervalMs = 6500): () => void {
    return startOperationMessages(setApiMessage, messages, intervalMs);
  }

  function startOperationMessages(
    setMessage: (message: string) => void,
    messages: string[],
    intervalMs = 6500,
  ): () => void {
    if (!messages.length) {
      return () => undefined;
    }
    let index = 0;
    setMessage(messages[index]);
    const timer = window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      setMessage(messages[index]);
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

  async function refreshAgentProjectResources(projectId: string) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    try {
      const snapshot = await fetchProjectResourceSnapshot(projectId);
      if (activeProjectIdRef.current !== projectId) {
        return;
      }
      applyProjectResources(projectId, snapshot);
    } catch (error) {
      if (!isAbortError(error)) {
        setApiMessage(formatApiFailure(error, "刷新 Bounded Research Agent 进度失败，请查看 API 日志。"));
      }
    }
  }

  function blockDemoProjectAction() {
    setApiMessage("Demo 项目仅用于界面预览，不会运行或保存真实 workflow。请创建真实项目后再操作。");
  }

  const viewModel: WorkflowViewModel = {
    activeArtifact,
    activeProject,
    agentPlan,
    agentRunStatus,
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
      rag: ragBusy,
    },
    decisionGoal,
    directionInput,
    directionReview,
    directionRun,
    directionMessage,
    directionRound,
    latestPaperCard: effectivePaperCard,
    lastSavedArtifact,
    literatureErrors,
    literatureCoverage,
    literatureQuery,
    memoryQuestion,
    memoryMessage,
    memoryResult,
    memoryTopK,
    ragMessage,
    ragAnswer,
    ragQuestion,
    ragTopK,
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
    onCancelAgentRun: handleCancelAgentRun,
    onGeneratePaperCard: handleGeneratePaperCard,
    onLiteratureQueryChange: setLiteratureQuery,
    onLoadArtifact: handleLoadArtifact,
    onMemoryQuestionChange: setMemoryQuestion,
    onMemoryTopKChange: setMemoryTopK,
    onRagQuestionChange: setRagQuestion,
    onRagTopKChange: setRagTopK,
    onPaperCardInputChange: setPaperCardInput,
    onPaperPdfUpload: handlePaperPdfUpload,
    onProjectDraftChange: setProjectDraft,
    onQueryResearchMemory: handleQueryResearchMemory,
    onQueryRag: handleQueryRag,
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
  directionRun: ApiDirectionReviewRunStatusResponse | null;
  paperCardBusy: boolean;
  latestPaperCard: ApiPaperCard | null;
  selectedPaperId: string;
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
  const directionRunActive = Boolean(
    input.directionRun && !isTerminalDirectionRunStatus(input.directionRun.status),
  );
  const directionRunFailed = input.directionRun?.status === "failed";
  const experimentStatus = input.researchDecision?.experiment?.status;
  const decisionStatus = input.researchDecision?.decision_status ?? "complete";
  const decisionEvidencePartial = isDecisionEvidencePartial(input.researchDecision);
  const selectedPaper = input.paperRows.find((paper) => paper.id === input.selectedPaperId) ?? input.paperRows[0];
  const selectedPaperCardMatch = resolvePaperCardForPaper(input.latestPaperCard, input.directionReview, selectedPaper);
  const selectedPaperCard = selectedPaperCardMatch?.card ?? null;
  const selectedCardHasVerifiedFullText = Boolean(
    selectedPaperCard?.evidence_qualification?.level === "full_text" &&
    selectedPaperCard.evidence_qualification.verified,
  );
  const manualUnboundPaperCard = Boolean(input.latestPaperCard && !selectedPaperCard && input.latestPaperCard.card_source === "manual_unbound");
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
        ? `${input.literatureCoverage.candidate_count ?? input.paperRows.length} candidates / ${input.literatureCoverage.eligible_count ?? returnedCount} eligible / ${returnedCount} shown / ${input.literatureCoverage.truncated_count ?? 0} truncated`
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
      summary: directionRunActive || directionRunFailed
        ? `${input.directionRun?.progress ?? 0}% · ${input.directionRun?.stage ?? "queued"}`
        : input.directionReview
          ? `${input.directionReview.relevant_read_count ?? input.directionReview.round_read_count}/${input.directionReview.target_paper_count} 强/中相关精读`
          : "每轮最多 10 篇方向精读",
      status: directionRunFailed
        ? "error"
        : resolveStepStatus({
            running: input.directionBusy,
            partial: directionStatus === "partial",
            blocked: directionStatus === "blocked" || !hasProject || !hasPapers || input.apiStatus === "offline",
            complete: directionStatus === "complete",
          }),
      warnings: [
        ...(input.directionReview?.errors ?? []),
        ...(input.directionRun?.notices
          .filter((notice) => notice.severity === "warning")
          .map((notice) => notice.message) ?? []),
      ],
      errors:
        input.directionRun?.notices
          .filter((notice) => notice.severity === "error")
          .map((notice) => notice.message) ?? [],
      updatedAt: input.directionRun?.updated_at || updatedAt,
    }),
    toWorkflowStepView({
      id: "paper-reader",
      label: "Deep Paper Card",
      summary: selectedPaperCard
        ? `当前论文 ${selectedPaperCard.sections.length} 个 section`
        : manualUnboundPaperCard
          ? "存在 manual/unbound card，未绑定当前论文"
          : "选择论文生成 12 条阅读",
      status: resolveStepStatus({
        blocked: !hasProject || (!hasPapers && !selectedPaperCard && !manualUnboundPaperCard) || input.apiStatus === "offline",
        running: input.paperCardBusy,
        complete: Boolean(
          selectedPaperCard &&
          selectedPaperCard.sections.length >= 12 &&
          selectedCardHasVerifiedFullText
        ),
        partial: Boolean(
          manualUnboundPaperCard ||
            (selectedPaperCard && selectedPaperCard.sections.length < 12) ||
            (selectedPaperCard && !selectedCardHasVerifiedFullText),
        ),
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
      summary:
        experimentStatus === "blocked"
          ? input.researchDecision?.experiment?.anchor_paper_title
            ? "实验硬约束尚未满足"
            : "缺少可复现 anchor"
          : experimentStatus === "partial"
            ? "科研锚点已核验，执行参数尚未补齐"
          : input.researchDecision
            ? "已生成实验计划"
            : "检查 anchor 后生成计划",
      status: resolveStepStatus({
        blocked: !hasProject || input.apiStatus === "offline" || experimentStatus === "blocked",
        running: input.decisionBusy,
        partial: experimentStatus === "partial",
        complete: experimentStatus === "ready",
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
  const groundedCount = Number(quality.grounded_gap_evidence_count ?? 0);
  const specificCount = Number(quality.specific_gap_evidence_count ?? 0);
  const corroboratedCount = Number(quality.corroborated_gap_group_count ?? 0);
  const conflictedCount = Number(quality.conflicted_gap_group_count ?? 0);
  return (
    !Number.isFinite(groundedCount) ||
    groundedCount < 2 ||
    !Number.isFinite(specificCount) ||
    specificCount < 2 ||
    !Number.isFinite(corroboratedCount) ||
    corroboratedCount < 1 ||
    (Number.isFinite(conflictedCount) && conflictedCount > 0)
  );
}

function upsertPaperCard(cards: ApiPaperCard[], incoming: ApiPaperCard): ApiPaperCard[] {
  const exactIndex = incoming.paper_id
    ? cards.findIndex((card) => Boolean(card.paper_id) && card.paper_id === incoming.paper_id)
    : -1;
  if (exactIndex >= 0) {
    const next = [...cards];
    next[exactIndex] = preferPaperCard(cards[exactIndex], incoming) as ApiPaperCard;
    return next;
  }
  const incomingTitle = (incoming.paper_title ?? "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "");
  const titleIndex = incomingTitle
    ? cards.findIndex(
        (card) =>
          !card.paper_id &&
          (card.paper_title ?? "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "") === incomingTitle,
      )
    : -1;
  if (titleIndex >= 0) {
    const next = [...cards];
    next[titleIndex] = preferPaperCard(cards[titleIndex], incoming) as ApiPaperCard;
    return next;
  }
  return [incoming, ...cards];
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
  directionRun: ApiDirectionReviewRunStatusResponse | null;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  ragAnswer: ApiRagAnswerResponse | null;
  researchDecision: ApiResearchDecisionResponse | null;
}): WorkflowNotice[] {
  const notices: WorkflowNotice[] = [];
  if (input.apiStatus === "offline") {
    notices.push({ id: "api-offline", kind: "error", message: input.apiMessage || "API 未连接" });
  }
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
  input.hydrationWarnings.forEach((message, index) => {
    notices.push({ id: `hydration-${index}`, kind: "warning", message });
  });
  if (input.directionRun?.notices.length) {
    input.directionRun.notices.forEach((notice, index) => {
      notices.push({
        id: `direction-run-${notice.code || index}`,
        kind: notice.severity,
        message: notice.message,
      });
    });
  } else {
    input.directionReview?.errors.forEach((message, index) => {
      notices.push({ id: `direction-${index}`, kind: "warning", message });
    });
  }
  input.memoryResult?.warnings.forEach((message, index) => {
    notices.push({ id: `memory-${index}`, kind: "warning", message });
  });
  input.ragAnswer?.warnings.forEach((message, index) => {
    notices.push({ id: `rag-${index}`, kind: "warning", message });
  });
  input.researchDecision?.experiment?.unblock_suggestions.forEach((message, index) => {
    notices.push({ id: `experiment-unblock-${index}`, kind: "warning", message });
  });
  input.researchDecision?.warnings?.forEach((message, index) => {
    notices.push({ id: `decision-warning-${index}`, kind: "warning", message });
  });
  return notices.slice(0, 8);
}
