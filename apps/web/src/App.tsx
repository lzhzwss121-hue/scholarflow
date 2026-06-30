import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  Circle,
  Clock3,
  FileText,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Play,
  Plus,
  Save,
  Search,
  Table2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  SCHOLARFLOW_VERSION,
  type ApiAgentPlanResponse,
  type ApiAgentPlanStep,
  type ApiArtifact,
  type ApiDirectionPaperReading,
  type ApiDirectionReviewResponse,
  type ApiPaper,
  type ApiPaperCard,
  type ApiProject,
  type ApiResearchDecisionResponse,
  type ApiResearchMemoryQueryResponse,
  type ApiToolEvent,
} from "@scholarflow/schemas";
import {
  artifacts,
  experiments,
  gapItems,
  navItems,
  papers as fallbackPapers,
  planSteps,
  timelineEvents as fallbackTimelineEvents,
  type ArtifactContent,
  type PaperRow,
  type PlanStep,
  type PlanStatus,
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
  listProjectArtifacts,
  listProjectPapers,
  listProjects,
  queryResearchMemory,
  saveArtifact,
  searchProjectLiterature,
} from "./apiClient";
import "./styles.css";

type ArtifactTab = "markdown" | "json" | "diff";
type ApiStatus = "checking" | "online" | "offline";
type ProjectDraft = {
  title: string;
  description: string;
  keyword: string;
  field: string;
};

const navIcons: Record<ViewId, LucideIcon> = {
  dashboard: LayoutDashboard,
  "new-project": Plus,
  "paper-table": Table2,
  "direction-review": FileText,
  "paper-memory": BrainCircuit,
  "paper-reader": BookOpen,
  "gap-board": GitBranch,
  "experiment-planner": FlaskConical,
};

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

export function App() {
  const [activeView, setActiveView] = useState<ViewId>("dashboard");
  const [artifactTab, setArtifactTab] = useState<ArtifactTab>("markdown");
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [apiMessage, setApiMessage] = useState("正在连接 ScholarFlow API...");
  const [projects, setProjects] = useState<ApiProject[]>([]);
  const [activeProject, setActiveProject] = useState<ApiProject | null>(null);
  const [paperRows, setPaperRows] = useState<PaperRow[]>(fallbackPapers);
  const [timelineRows, setTimelineRows] = useState<TimelineEvent[]>(fallbackTimelineEvents);
  const [persistedArtifactCount, setPersistedArtifactCount] = useState(0);
  const [lastSavedArtifact, setLastSavedArtifact] = useState<ApiArtifact | null>(null);
  const [projectArtifacts, setProjectArtifacts] = useState<ApiArtifact[]>([]);
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
  const checklistSteps = agentPlan ? agentPlan.steps.map(toPlanStep) : planSteps;

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspace() {
      try {
        await getHealth();
        const loadedProjects = await listProjects();
        const firstProject = loadedProjects[0] ?? null;

        if (cancelled) {
          return;
        }

        setApiStatus("online");
        setProjects(loadedProjects);
        setActiveProject(firstProject);
        setApiMessage(firstProject ? "API 已连接，正在使用 SQLite 工作区。" : "API 已连接，尚未创建项目。");

        if (firstProject) {
          await loadProjectResources(firstProject.id, cancelled);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setApiStatus("offline");
        setApiMessage("API 未连接，当前显示静态 mock 工作台。");
      }
    }

    loadWorkspace();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeProject?.keyword && activeProject.keyword !== "你的研究方向关键词") {
      setLiteratureQuery(activeProject.keyword);
      setDirectionInput(activeProject.keyword);
    }
    setDirectionReview(null);
    setSelectedDirectionPaperId("");
    setMemoryResult(null);
  }, [activeProject?.id, activeProject?.keyword]);

  useEffect(() => {
    setLastSavedArtifact(selectArtifactForView(projectArtifacts, activeView));
  }, [activeView, projectArtifacts]);

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
    const [apiPapers, apiTimeline, apiArtifacts] = await Promise.all([
      listProjectPapers(projectId),
      getProjectTimeline(projectId),
      listProjectArtifacts(projectId),
    ]);

    if (cancelled) {
      return;
    }

    setPaperRows(apiPapers.map(toPaperRow));
    setTimelineRows(apiTimeline.map(toTimelineEvent));
    setPersistedArtifactCount(apiArtifacts.length);
    setProjectArtifacts(apiArtifacts);
    setLastSavedArtifact(selectArtifactForView(apiArtifacts, activeView));
  }

  async function handleSelectProject(projectId: string) {
    const project = projects.find((item) => item.id === projectId) ?? null;
    setActiveProject(project);
    setLastSavedArtifact(null);
    setProjectArtifacts([]);
    setDirectionReview(null);
    setMemoryResult(null);
    setResearchDecision(null);
    setLatestPaperCard(null);
    setSelectedDirectionPaperId("");

    if (!project) {
      setPaperRows(fallbackPapers);
      setTimelineRows(fallbackTimelineEvents);
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
      setActiveView("dashboard");
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
      setProjectArtifacts((items) => [reloaded, ...items.filter((item) => item.id !== reloaded.id)]);
    } catch (error) {
      setApiMessage("保存 artifact 失败，请确认 API 与 SQLite 工作区可用。");
    } finally {
      setArtifactSaving(false);
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
    setApiMessage("正在执行已确认的 Agent Plan...");
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
    setApiMessage("正在检索 arXiv / OpenAlex 并生成 paper table...");
    try {
      const result = await searchProjectLiterature(activeProject.id, {
        query: literatureQuery,
        max_results: 12,
        sources: ["arxiv", "openalex"],
      });
      setPaperRows(result.papers.map(toPaperRow));
      setLastSavedArtifact(result.artifact);
      setLiteratureErrors(result.errors);
      setApiMessage(`检索完成：${result.papers.length} 篇论文，artifact: ${result.artifact.id}`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("文献检索失败，请检查网络、OpenAlex/arXiv 可用性或 API 日志。");
    } finally {
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
    setApiMessage(`正在执行第 ${directionRound} 轮方向精读：近三年 10 篇高相关论文...`);
    try {
      const result = await createDirectionReview(activeProject.id, {
        direction: directionInput,
        round: directionRound,
      });
      setDirectionReview(result);
      setSelectedDirectionPaperId("");
      setLastSavedArtifact(result.artifacts[0] ?? null);
      setApiMessage(`方向精读完成：第 ${result.round} 轮，累计 ${result.total_read_count} 篇。`);
      await loadProjectResources(activeProject.id);
    } catch (error) {
      setApiMessage("方向精读失败，请检查网络、检索源可用性或 API 日志。");
    } finally {
      setDirectionBusy(false);
    }
  }

  async function handleQueryResearchMemory() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setMemoryBusy(true);
    setApiMessage(`正在从 Paper Memory Bank 检索 ${memoryTopK} 篇相关论文...`);
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
      setMemoryBusy(false);
    }
  }

  async function handleCreateResearchDecision() {
    if (!activeProject) {
      setApiMessage("没有可写入的后端项目，请先创建或启动 API。");
      return;
    }

    setDecisionBusy(true);
    setApiMessage("正在生成 Gap / Novelty / Experiment Plan...");
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
      setDecisionBusy(false);
    }
  }

  return (
    <div className="scholarflow-app">
      <ProjectNavigator
        activeProject={activeProject}
        activeView={activeView}
        apiStatus={apiStatus}
        artifactCount={persistedArtifactCount}
        onSelect={setActiveView}
        onSelectProject={handleSelectProject}
        paperCount={paperRows.length}
        projectCount={projects.length}
        projects={projects}
      />

      <main className="agent-workspace">
        <header className="workspace-header">
          <div>
            <p className="phase-label">v0.1.0 / Open-Source Preview</p>
            <h1>{viewTitles[activeView]}</h1>
          </div>
          <div className="toolbar" aria-label="workspace actions">
            <button
              className="icon-button"
              disabled={apiStatus !== "online" || artifactSaving}
              title="保存右侧 Artifact 编辑内容"
              type="button"
              onClick={handleSaveArtifact}
            >
              <Save size={17} />
            </button>
          </div>
        </header>

        <div className={`api-banner ${apiStatus}`}>
          <span className="api-dot" />
          <p>{apiMessage}</p>
        </div>

        <section className="workspace-body" aria-label={activeNavItem?.label}>
          <div className="primary-view">
            <ActiveView
              activeProject={activeProject}
              agentBusy={agentBusy}
              agentPlan={agentPlan}
              agentTask={agentTask}
              apiMessage={apiMessage}
              apiStatus={apiStatus}
              artifactCount={persistedArtifactCount}
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
              onMemoryQuestionChange={setMemoryQuestion}
              onMemoryTopKChange={setMemoryTopK}
              onPaperCardInputChange={setPaperCardInput}
              onQueryResearchMemory={handleQueryResearchMemory}
              onProjectDraftChange={setProjectDraft}
              onSearchLiterature={handleSearchLiterature}
              onSelectedDirectionPaperChange={setSelectedDirectionPaperId}
              onSelectedPaperChange={setSelectedPaperId}
              onSelectView={setActiveView}
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
          </div>
          <aside className="agent-rail" aria-label="agent progress">
            <PlanChecklist steps={checklistSteps} />
            <ToolTimeline events={timelineRows} />
          </aside>
        </section>
      </main>

      <ArtifactPreview
        activeTab={artifactTab}
        apiStatus={apiStatus}
        artifact={artifactDraft ?? displayedArtifact}
        isSaving={artifactSaving}
        lastSavedArtifact={lastSavedArtifact}
        onArtifactChange={setArtifactDraft}
        onSave={handleSaveArtifact}
        onTabChange={setArtifactTab}
      />
    </div>
  );
}

interface NavigatorProps {
  activeProject: ApiProject | null;
  activeView: ViewId;
  apiStatus: ApiStatus;
  artifactCount: number;
  onSelect: (view: ViewId) => void;
  onSelectProject: (projectId: string) => void;
  paperCount: number;
  projectCount: number;
  projects: ApiProject[];
}

function ProjectNavigator({
  activeProject,
  activeView,
  apiStatus,
  artifactCount,
  onSelect,
  onSelectProject,
  paperCount,
  projectCount,
  projects,
}: NavigatorProps) {
  return (
    <aside className="project-navigator">
      <div className="brand">
        <div className="brand-mark">SF</div>
        <div>
          <strong>ScholarFlow</strong>
          <span>v{SCHOLARFLOW_VERSION}</span>
        </div>
      </div>

      <div className={`api-pill ${apiStatus}`}>
        <span className="api-dot" />
        {apiStatus === "online" ? "API Online" : apiStatus === "checking" ? "API Checking" : "Mock Mode"}
      </div>

      <label className="project-selector-field">
        <span>Project</span>
        <select
          className="project-selector"
          value={activeProject?.id ?? ""}
          onChange={(event) => onSelectProject(event.target.value)}
        >
          {projects.length ? null : (
            <option disabled value="">
              暂无项目
            </option>
          )}
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.title}
            </option>
          ))}
        </select>
      </label>

      <button
        className="primary-command"
        type="button"
        onClick={() => onSelect("new-project")}
        title="新建科研项目"
      >
        <Plus size={17} />
        新建项目
      </button>

      <nav className="nav-list" aria-label="project navigation">
        {navItems.map((item) => {
          const Icon = navIcons[item.id];
          return (
            <button
              className={item.id === activeView ? "nav-item active" : "nav-item"}
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              title={item.label}
            >
              <Icon size={17} />
              <span>{item.label}</span>
              {item.count ? <small>{item.count}</small> : null}
            </button>
          );
        })}
      </nav>

      <section className="navigator-section">
        <p className="section-kicker">Project</p>
        <h2>{activeProject?.title ?? "等待创建研究项目"}</h2>
        <div className="tag-row">
          <span>{activeProject?.field || "AI Research"}</span>
          <span>{activeProject?.workflow || "survey-to-experiment"}</span>
          <span>{activeProject?.language || "zh-CN"}</span>
        </div>
      </section>

      <section className="navigator-section">
        <p className="section-kicker">Local Assets</p>
        <ul className="asset-list">
          <li>{projectCount || 1} project</li>
          <li>{paperCount} papers</li>
          <li>{artifactCount} persisted artifacts</li>
          <li>SQLite workspace</li>
        </ul>
      </section>
    </aside>
  );
}

interface ActiveViewProps {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentTask: string;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  decisionBusy: boolean;
  decisionGoal: string;
  directionBusy: boolean;
  directionInput: string;
  directionReview: ApiDirectionReviewResponse | null;
  directionRound: number;
  literatureBusy: boolean;
  literatureErrors: string[];
  literatureQuery: string;
  latestPaperCard: ApiPaperCard | null;
  memoryBusy: boolean;
  memoryQuestion: string;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  memoryTopK: number;
  projectDraft: ProjectDraft;
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onCreateDirectionReview: () => void;
  onCreateProject: () => void;
  onCreateResearchDecision: () => void;
  onDecisionGoalChange: (goal: string) => void;
  onDirectionInputChange: (direction: string) => void;
  onDirectionRoundChange: (round: number) => void;
  onExecuteAgentRun: () => void;
  onGeneratePaperCard: () => void;
  onLiteratureQueryChange: (query: string) => void;
  onMemoryQuestionChange: (question: string) => void;
  onMemoryTopKChange: (topK: number) => void;
  onPaperCardInputChange: (value: string) => void;
  onProjectDraftChange: (draft: ProjectDraft) => void;
  onQueryResearchMemory: () => void;
  onSearchLiterature: () => void;
  onSelectedDirectionPaperChange: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperRows: PaperRow[];
  paperCardBusy: boolean;
  paperCardInput: string;
  projectCount: number;
  researchDecision: ApiResearchDecisionResponse | null;
  selectedDirectionPaperId: string;
  selectedPaperId: string;
  view: ViewId;
}

function ActiveView({
  activeProject,
  agentBusy,
  agentPlan,
  agentTask,
  apiMessage,
  apiStatus,
  artifactCount,
  decisionBusy,
  decisionGoal,
  directionBusy,
  directionInput,
  directionReview,
  directionRound,
  literatureBusy,
  literatureErrors,
  literatureQuery,
  latestPaperCard,
  memoryBusy,
  memoryQuestion,
  memoryResult,
  memoryTopK,
  projectDraft,
  onAgentTaskChange,
  onCreateAgentPlan,
  onCreateDirectionReview,
  onCreateProject,
  onCreateResearchDecision,
  onDecisionGoalChange,
  onDirectionInputChange,
  onDirectionRoundChange,
  onExecuteAgentRun,
  onGeneratePaperCard,
  onLiteratureQueryChange,
  onMemoryQuestionChange,
  onMemoryTopKChange,
  onPaperCardInputChange,
  onProjectDraftChange,
  onQueryResearchMemory,
  onSearchLiterature,
  onSelectedDirectionPaperChange,
  onSelectedPaperChange,
  onSelectView,
  paperRows,
  paperCardBusy,
  paperCardInput,
  projectCount,
  researchDecision,
  selectedDirectionPaperId,
  selectedPaperId,
  view,
}: ActiveViewProps) {
  switch (view) {
    case "new-project":
      return (
        <NewProjectView
          apiMessage={apiMessage}
          apiStatus={apiStatus}
          draft={projectDraft}
          onCreateProject={onCreateProject}
          onDraftChange={onProjectDraftChange}
        />
      );
    case "paper-table":
      return (
        <PaperTableView
          apiStatus={apiStatus}
          errors={literatureErrors}
          isSearching={literatureBusy}
          onQueryChange={onLiteratureQueryChange}
          onSearch={onSearchLiterature}
          papers={paperRows}
          query={literatureQuery}
        />
      );
    case "paper-reader":
      return (
        <PaperReaderView
          apiStatus={apiStatus}
          card={latestPaperCard}
          isGenerating={paperCardBusy}
          onGenerate={onGeneratePaperCard}
          onInputChange={onPaperCardInputChange}
          onSelectedPaperChange={onSelectedPaperChange}
          papers={paperRows}
          selectedPaperId={selectedPaperId}
          supplementalInput={paperCardInput}
        />
      );
    case "direction-review":
      return (
        <DirectionReviewView
          apiStatus={apiStatus}
          direction={directionInput}
          isGenerating={directionBusy}
          onDirectionChange={onDirectionInputChange}
          onGenerate={onCreateDirectionReview}
          onRoundChange={onDirectionRoundChange}
          onSelectedPaperChange={onSelectedDirectionPaperChange}
          review={directionReview}
          round={directionRound}
          selectedPaperId={selectedDirectionPaperId}
        />
      );
    case "paper-memory":
      return (
        <ResearchMemoryView
          apiStatus={apiStatus}
          direction={directionInput}
          isQuerying={memoryBusy}
          onQuestionChange={onMemoryQuestionChange}
          onQuery={onQueryResearchMemory}
          onTopKChange={onMemoryTopKChange}
          question={memoryQuestion}
          result={memoryResult}
          topK={memoryTopK}
        />
      );
    case "gap-board":
      return (
        <GapBoardView
          apiStatus={apiStatus}
          decision={researchDecision}
          goal={decisionGoal}
          isGenerating={decisionBusy}
          onGenerate={onCreateResearchDecision}
          onGoalChange={onDecisionGoalChange}
        />
      );
    case "experiment-planner":
      return (
        <ExperimentPlannerView
          apiStatus={apiStatus}
          decision={researchDecision}
          goal={decisionGoal}
          isGenerating={decisionBusy}
          onGenerate={onCreateResearchDecision}
          onGoalChange={onDecisionGoalChange}
        />
      );
    case "dashboard":
    default:
      return (
        <DashboardView
          activeProject={activeProject}
          agentBusy={agentBusy}
          agentPlan={agentPlan}
          agentTask={agentTask}
          apiStatus={apiStatus}
          artifactCount={artifactCount}
          onAgentTaskChange={onAgentTaskChange}
          onCreateAgentPlan={onCreateAgentPlan}
          onExecuteAgentRun={onExecuteAgentRun}
          onSelectView={onSelectView}
          paperCount={paperRows.length}
          projectCount={projectCount}
        />
      );
  }
}

function DashboardView({
  activeProject,
  agentBusy,
  agentPlan,
  agentTask,
  apiStatus,
  artifactCount,
  onAgentTaskChange,
  onCreateAgentPlan,
  onExecuteAgentRun,
  onSelectView,
  paperCount,
  projectCount,
}: {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentTask: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onExecuteAgentRun: () => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
}) {
  return (
    <div className="view-stack">
      <section className="brief-panel">
        <div>
          <p className="section-kicker">Current Task</p>
          <h2>{activeProject?.title ?? "输入你的研究方向，开始一次科研任务流程"}</h2>
        </div>
        <p>
          当前版本已经贯通 Research Plan、文献检索、Deep Paper Card、Gap Board 和 Experiment Plan。
          系统会把关键工具调用写入 session timeline，并把研究输出保存为 artifact。
        </p>
      </section>

      <WorkflowGuide
        apiStatus={apiStatus}
        hasProject={Boolean(activeProject)}
        onSelectView={onSelectView}
        paperCount={paperCount}
        artifactCount={artifactCount}
      />

      <AgentRuntimePanel
        apiStatus={apiStatus}
        artifactCount={artifactCount}
        paperCount={paperCount}
        stage={activeProject?.stage ?? "mock"}
      />

      <AgentRunPanel
        agentBusy={agentBusy}
        agentPlan={agentPlan}
        agentTask={agentTask}
        apiStatus={apiStatus}
        onAgentTaskChange={onAgentTaskChange}
        onCreateAgentPlan={onCreateAgentPlan}
        onExecuteAgentRun={onExecuteAgentRun}
      />

      <section className="metric-grid" aria-label="research status">
        <Metric label="后端状态" value={apiStatus === "online" ? "ON" : "OFF"} detail="FastAPI + SQLite" />
        <Metric label="项目数" value={String(projectCount || 1)} detail="projects table" />
        <Metric label="论文记录" value={String(paperCount)} detail="papers table" />
        <Metric label="Artifacts" value={String(artifactCount)} detail="artifacts table" />
      </section>

    </div>
  );
}

function WorkflowGuide({
  apiStatus,
  artifactCount,
  hasProject,
  onSelectView,
  paperCount,
}: {
  apiStatus: ApiStatus;
  artifactCount: number;
  hasProject: boolean;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
}) {
  const steps: Array<{
    id: string;
    title: string;
    detail: string;
    action: string;
    target: ViewId;
    status: "ready" | "blocked" | "done";
  }> = [
    {
      id: "project",
      title: "1. 创建或选择研究项目",
      detail: "先确定研究方向、关键词和工作流。后续论文、记忆和 artifact 都会归到这个项目下。",
      action: hasProject ? "查看项目" : "新建项目",
      target: hasProject ? "dashboard" : "new-project",
      status: hasProject ? "done" : "ready",
    },
    {
      id: "search",
      title: "2. 检索近三年相关论文",
      detail: "用研究方向作为 query，生成 Paper Table，作为方向精读和记忆库的输入。",
      action: "去检索论文",
      target: "paper-table",
      status: !hasProject ? "blocked" : paperCount > 0 ? "done" : "ready",
    },
    {
      id: "read",
      title: "3. 方向精读与论文卡片",
      detail: "每轮读取 10 篇高相关论文，生成摘要翻译、12 条精读、ResearchSight 和 round summary。",
      action: "开始方向精读",
      target: "direction-review",
      status: paperCount > 0 ? "ready" : "blocked",
    },
    {
      id: "memory",
      title: "4. 查询 Paper Memory",
      detail: "读完多篇后不要把 30 篇全塞上下文，而是按问题检索最相关的 3-8 篇再回答。",
      action: "问论文记忆",
      target: "paper-memory",
      status: artifactCount > 0 ? "ready" : "blocked",
    },
    {
      id: "decision",
      title: "5. 生成 Gap 与一周实验",
      detail: "基于已读论文找真 gap、判断 novelty risk，并给出可复现 anchor 和最小实验计划。",
      action: "生成研究决策",
      target: "gap-board",
      status: artifactCount > 0 ? "ready" : "blocked",
    },
  ];

  return (
    <section className="workflow-guide" aria-label="research workflow guide">
      <div className="workflow-guide-header">
        <div>
          <p className="section-kicker">Recommended Path</p>
          <h2>按这个顺序完成一次科研任务</h2>
        </div>
        <span className={`run-status ${apiStatus === "online" ? "completed" : "queued"}`}>
          {apiStatus === "online" ? "API ready" : "需要启动 API"}
        </span>
      </div>
      <div className="workflow-guide-list">
        {steps.map((step) => (
          <article className={`workflow-guide-step ${step.status}`} key={step.id}>
            <div>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
            </div>
            <button
              className="secondary-command"
              disabled={step.status === "blocked" || apiStatus !== "online"}
              type="button"
              onClick={() => onSelectView(step.target)}
            >
              {step.action}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

function AgentRuntimePanel({
  apiStatus,
  artifactCount,
  paperCount,
  stage,
}: {
  apiStatus: ApiStatus;
  artifactCount: number;
  paperCount: number;
  stage: string;
}) {
  const items = [
    {
      icon: BrainCircuit,
      label: "Plan Mode",
      value: stage === "agent-loop" ? "planning" : "ready",
      detail: "生成计划后再确认执行",
    },
    {
      icon: Search,
      label: "Paper Memory",
      value: `${paperCount} papers`,
      detail: "按问题检索 3-8 篇论文记忆",
    },
    {
      icon: FileText,
      label: "Context",
      value: "structured",
      detail: "论文卡片、round summary、direction memory 分层保存",
    },
    {
      icon: Save,
      label: "Artifacts",
      value: String(artifactCount),
      detail: apiStatus === "online" ? "SQLite 持久化" : "mock preview",
    },
  ];

  return (
    <section className="runtime-panel" aria-label="agent runtime">
      <div className="runtime-heading">
        <div>
          <p className="section-kicker">Agent Runtime</p>
          <h2>运行状态</h2>
        </div>
        <span className={`run-status ${apiStatus === "online" ? "completed" : "queued"}`}>
          {apiStatus === "online" ? "online" : apiStatus}
        </span>
      </div>
      <div className="runtime-grid">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <article className="runtime-card" key={item.label}>
              <Icon size={17} />
              <div>
                <strong>{item.label}</strong>
                <span>{item.value}</span>
                <p>{item.detail}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AgentRunPanel({
  agentBusy,
  agentPlan,
  agentTask,
  apiStatus,
  onAgentTaskChange,
  onCreateAgentPlan,
  onExecuteAgentRun,
}: {
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentTask: string;
  apiStatus: ApiStatus;
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onExecuteAgentRun: () => void;
}) {
  const canExecute = Boolean(agentPlan && agentPlan.status !== "completed" && !agentBusy && apiStatus === "online");
  const isDemoMode = Boolean(agentPlan?.steps.some((step) => step.tool === "search_mock_papers"));

  return (
    <section className="agent-run-panel" aria-label="agent plan mode">
      <div className="agent-run-header">
        <div>
          <p className="section-kicker">Research Plan Mode</p>
          <h2>{agentPlan ? `Run ${agentPlan.run_id}` : "Agent Task"}</h2>
        </div>
        <div className="agent-run-badges">
          {agentPlan ? (
            <span className={`tool-mode-badge ${isDemoMode ? "demo" : "real"}`}>
              {isDemoMode ? "Demo Mode" : "Real Tools"}
            </span>
          ) : null}
          <span className={`run-status ${agentPlan?.status ?? "idle"}`}>{agentPlan?.status ?? "idle"}</span>
        </div>
      </div>

      <label className="agent-task-field">
        任务
        <textarea value={agentTask} onChange={(event) => onAgentTaskChange(event.target.value)} />
      </label>

      <div className="agent-action-row">
        <button
          className="secondary-command"
          disabled={agentBusy || apiStatus !== "online" || agentTask.trim().length === 0}
          type="button"
          onClick={onCreateAgentPlan}
        >
          <BrainCircuit size={17} />
          生成计划
        </button>
        <button className="secondary-command" disabled={!canExecute} type="button" onClick={onExecuteAgentRun}>
          <Play size={17} />
          确认执行
        </button>
      </div>

      {agentPlan ? (
        <div className="agent-plan-box">
          <p>{agentPlan.rationale}</p>
          <div className="agent-plan-list">
            {agentPlan.steps.map((step) => (
              <div className="agent-plan-row" key={step.id}>
                <StatusIcon status={toPlanStatus(step.status)} />
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.tool}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function NewProjectView({
  apiMessage,
  apiStatus,
  draft,
  onCreateProject,
  onDraftChange,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  draft: ProjectDraft;
  onCreateProject: () => void;
  onDraftChange: (draft: ProjectDraft) => void;
}) {
  function updateDraft(field: keyof ProjectDraft, value: string) {
    onDraftChange({
      ...draft,
      [field]: value,
    });
  }

  return (
    <div className="view-stack">
      <section className="form-panel">
        <label>
          项目名称
          <div className="input-shell">
            <FileText size={17} />
            <input
              placeholder="例如：大语言模型推理可靠性评估"
              value={draft.title}
              onChange={(event) => updateDraft("title", event.target.value)}
            />
          </div>
        </label>
        <label>
          研究方向 / 关键词
          <div className="input-shell">
            <Search size={17} />
            <input
              placeholder="输入你真正想研究的方向，例如：AI agent 工具调用可靠性"
              value={draft.keyword}
              onChange={(event) => updateDraft("keyword", event.target.value)}
            />
          </div>
        </label>
        <label>
          研究目标
          <textarea
            placeholder="简要说明你想解决的问题、应用场景或希望 ScholarFlow 帮你调研的范围。"
            value={draft.description}
            onChange={(event) => updateDraft("description", event.target.value)}
          />
        </label>
        <div className="form-grid">
          <label>
            领域
            <input
              placeholder="例如：Artificial Intelligence / NLP / Robotics"
              value={draft.field}
              onChange={(event) => updateDraft("field", event.target.value)}
            />
          </label>
          <label>
            输出语言
            <input readOnly value="中文为主，保留英文术语" />
          </label>
        </div>
        <p className="form-helper">
          ScholarFlow 不预设研究方向。这里输入什么，后续文献检索、方向精读、Paper Memory 和实验计划就围绕什么展开。
        </p>
        <div className="api-action-row">
          <button className="secondary-command" disabled={apiStatus === "checking"} type="button" onClick={onCreateProject}>
            <Plus size={17} />
            创建到 SQLite
          </button>
          <span>{apiMessage}</span>
        </div>
      </section>

      <section className="brief-panel compact">
        <BrainCircuit size={20} />
        <div>
          <h2>推荐工作流</h2>
          <p>Survey {"->"} Paper Table {"->"} Deep Paper Card {"->"} Gap Board {"->"} Experiment Plan</p>
        </div>
      </section>
    </div>
  );
}

function PaperTableView({
  apiStatus,
  errors,
  isSearching,
  onQueryChange,
  onSearch,
  papers,
  query,
}: {
  apiStatus: ApiStatus;
  errors: string[];
  isSearching: boolean;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  papers: PaperRow[];
  query: string;
}) {
  return (
    <div className="view-stack">
      <section className="literature-search-panel" aria-label="literature search">
        <label>
          检索关键词
          <div className="search-control">
            <Search size={17} />
            <input value={query} onChange={(event) => onQueryChange(event.target.value)} />
            <button
              className="secondary-command"
              disabled={apiStatus !== "online" || isSearching || query.trim().length === 0}
              type="button"
              onClick={onSearch}
            >
              <Search size={17} />
              {isSearching ? "检索中" : "检索论文"}
            </button>
          </div>
        </label>
        <div className="source-row">
          <span>arXiv</span>
          <span>OpenAlex</span>
          <span>Query Expansion</span>
          <span>Dedup + Ranking</span>
        </div>
        {errors.length ? (
          <div className="retrieval-errors">
            <strong>检索警告</strong>
            <p>{errors.slice(0, 2).join(" / ")}</p>
          </div>
        ) : null}
      </section>

      <section className="table-shell" aria-label="paper table">
        <table>
          <thead>
            <tr>
              <th>论文</th>
              <th>年份</th>
              <th>作者</th>
              <th>来源</th>
              <th>相关性理由</th>
              <th>优先级</th>
              <th>链接</th>
            </tr>
          </thead>
          <tbody>
            {papers.map((paper) => (
              <tr key={`${paper.source}-${paper.title}`}>
                <td>
                  <strong>{paper.title}</strong>
                  <small>{paper.type}</small>
                </td>
                <td>{paper.year}</td>
                <td>{paper.authors || "unknown"}</td>
                <td>
                  <span className="source-badge">{paper.source}</span>
                  <small>{paper.venue}</small>
                </td>
                <td>{paper.relation}</td>
                <td>
                  <span className={`priority ${paper.priority.toLowerCase()}`}>{paper.priority}</span>
                </td>
                <td>
                  {paper.url ? (
                    <a href={paper.url} rel="noreferrer" target="_blank">
                      open
                    </a>
                  ) : (
                    "none"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function DirectionReviewView({
  apiStatus,
  direction,
  isGenerating,
  onDirectionChange,
  onGenerate,
  onRoundChange,
  onSelectedPaperChange,
  review,
  round,
  selectedPaperId,
}: {
  apiStatus: ApiStatus;
  direction: string;
  isGenerating: boolean;
  onDirectionChange: (direction: string) => void;
  onGenerate: () => void;
  onRoundChange: (round: number) => void;
  onSelectedPaperChange: (paperId: string) => void;
  review: ApiDirectionReviewResponse | null;
  round: number;
  selectedPaperId: string;
}) {
  const selectedReading = review?.papers.find((reading) => reading.paper.id === selectedPaperId) ?? null;
  const recommendedReadings =
    review?.papers.filter((reading) => review.recommended_paper_ids.includes(reading.paper.id) || reading.self_read_priority) ??
    [];
  const canGenerate = apiStatus === "online" && !isGenerating && direction.trim().length > 0;

  return (
    <div className="direction-review-stack">
      <section className="direction-review-controls" aria-label="direction review controls">
        <div className="direction-control-header">
          <div>
            <p className="section-kicker">Direction Review</p>
            <h2>方向级三轮论文精读</h2>
          </div>
          <button className="secondary-command" disabled={!canGenerate} type="button" onClick={onGenerate}>
            <BrainCircuit size={17} />
            {isGenerating ? "生成中" : `生成第 ${round} 轮`}
          </button>
        </div>

        <div className="direction-control-grid">
          <label>
            研究方向
            <textarea
              placeholder="例如：AI agent 工具调用可靠性 / 大模型推理评估 / 医学图像分割泛化"
              value={direction}
              onChange={(event) => onDirectionChange(event.target.value)}
            />
          </label>
          <label>
            阅读轮次
            <select value={round} onChange={(event) => onRoundChange(Number(event.target.value))}>
              <option value={1}>第 1 轮：10 篇</option>
              <option value={2}>第 2 轮：累计 20 篇</option>
              <option value={3}>第 3 轮：累计 30 篇上限</option>
            </select>
          </label>
        </div>

        <div className="direction-chip-row">
          <span>近三年</span>
          <span>每轮 10 篇</span>
          <span>顶会/顶刊优先</span>
          <span>点击卡片查看细节</span>
        </div>
      </section>

      {review ? (
        <>
          <section className="direction-summary-panel" aria-label="direction summary">
            <div className="direction-summary-header">
              <div>
                <p className="section-kicker">Cumulative Understanding</p>
                <h2>{review.direction}</h2>
              </div>
              <div className="direction-stat-grid">
                <span>Round {review.round}</span>
                <span>{review.total_read_count} papers</span>
                <span>{review.scope.year_range}</span>
              </div>
            </div>
            <p>{review.direction_summary}</p>
            <div className="direction-scope-grid">
              <div>
                <strong>纳入范围</strong>
                <span>{review.scope.included_scope}</span>
              </div>
              <div>
                <strong>排除范围</strong>
                <span>{review.scope.excluded_scope}</span>
              </div>
            </div>
            <div className="direction-chip-row">
              {review.scope.subtopics.map((subtopic) => (
                <span key={subtopic}>{subtopic}</span>
              ))}
            </div>
            <div className="baseline-map-panel" aria-label="baseline map">
              <div className="baseline-map-header">
                <div>
                  <p className="section-kicker">BaselineMap</p>
                  <h3>方向背景与对比参照</h3>
                </div>
                <span>{review.baseline_map.generated_from.length} candidates</span>
              </div>
              <p>{review.baseline_map.task_definition}</p>
              <div className="baseline-map-grid">
                <BaselineReferenceList title="经典 baseline" references={review.baseline_map.classic_baselines} />
                <BaselineReferenceList title="近三年强 baseline" references={review.baseline_map.recent_strong_baselines} />
                <BaselineReferenceList title="异质范式" references={review.baseline_map.alternative_paradigms} />
              </div>
              <div className="baseline-risk-grid">
                <div>
                  <strong>证据约束</strong>
                  <span>{review.baseline_map.evidence_summary}</span>
                </div>
                <div>
                  <strong>常见 benchmark</strong>
                  <span>{review.baseline_map.common_benchmarks.slice(0, 5).join(" / ")}</span>
                </div>
                <div>
                  <strong>评价风险</strong>
                  <span>{review.baseline_map.evaluation_risks.slice(0, 2).join("；")}</span>
                </div>
                <div>
                  <strong>开放问题</strong>
                  <span>{review.baseline_map.open_questions.slice(0, 2).join("；")}</span>
                </div>
              </div>
            </div>
            {review.errors.length ? (
              <div className="retrieval-errors">
                <strong>检索警告</strong>
                <p>{review.errors.slice(0, 2).join(" / ")}</p>
              </div>
            ) : null}
          </section>

          <section className="recommendation-panel" aria-label="recommended papers">
            <div>
              <p className="section-kicker">Personal Deep Reading</p>
              <h2>最值得用户本人精读的 3 篇</h2>
            </div>
            <div className="recommendation-list">
              {recommendedReadings.slice(0, 3).map((reading, index) => (
                <button
                  className="recommendation-item"
                  key={reading.paper.id}
                  type="button"
                  onClick={() => onSelectedPaperChange(reading.paper.id)}
                >
                  <span>{index + 1}</span>
                  <div>
                    <strong>{reading.paper.title}</strong>
                    <small>{reading.why_selected}</small>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <div className="direction-reader-layout">
            <section className="direction-paper-grid" aria-label="direction paper cards">
              {review.papers.map((reading, index) => {
                const isActive = selectedPaperId === reading.paper.id;
                return (
                  <button
                    className={isActive ? "direction-paper-card active" : "direction-paper-card"}
                    key={reading.paper.id}
                    type="button"
                    onClick={() => onSelectedPaperChange(reading.paper.id)}
                  >
                    <div className="direction-paper-card-header">
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      {reading.self_read_priority ? <strong>推荐精读</strong> : null}
                    </div>
                    <h3>{reading.paper.title}</h3>
                    <p>{reading.why_selected}</p>
                    <div className="direction-paper-meta">
                      <span>{reading.paper.year || "year unknown"}</span>
                      <span>{reading.paper.venue || reading.paper.source || "source unknown"}</span>
                    </div>
                    <small>{reading.venue_signal}</small>
                  </button>
                );
              })}
            </section>

            {selectedReading ? (
              <DirectionPaperDetail reading={selectedReading} />
            ) : (
              <section className="direction-detail empty" aria-label="paper detail placeholder">
                <BookOpen size={20} />
                <h2>选择一张论文卡片</h2>
                <p>摘要中文内容和 12 条精读结果会在这里显示，列表页不会直接铺开长文本。</p>
              </section>
            )}
          </div>
        </>
      ) : (
        <section className="direction-empty-state">
          <BookOpen size={22} />
          <div>
            <h2>输入一个研究方向后开始第一轮</h2>
            <p>
              ScholarFlow 会为该方向检索近三年高相关候选论文，选择 10 篇进行结构化精读，并输出方向总结和 3
              篇最值得亲自精读的论文。
            </p>
          </div>
        </section>
      )}
    </div>
  );
}

function BaselineReferenceList({
  references,
  title,
}: {
  references: ApiDirectionReviewResponse["baseline_map"]["classic_baselines"];
  title: string;
}) {
  return (
    <div className="baseline-reference-list">
      <strong>{title}</strong>
      {references.length ? (
        references.slice(0, 3).map((reference) => (
          <article key={`${title}-${reference.title}`}>
            <span>{reference.year || "year unknown"} · {reference.confidence || "unknown"} confidence</span>
            <h4>{reference.title}</h4>
            <p>{reference.reason}</p>
            <small>{reference.evidence_gap}</small>
          </article>
        ))
      ) : (
        <p>当前候选池没有稳定参照。</p>
      )}
    </div>
  );
}

function DirectionPaperDetail({ reading }: { reading: ApiDirectionPaperReading }) {
  const signals = reading.signals;
  const missingSignals = signals?.missing_signals ?? [];
  const critiqueEvidence = new Map(
    (reading.research_sight.critique_evidence ?? []).map((item) => [item.field, item]),
  );
  const renderCritiqueEvidence = (field: string) => {
    const evidence = critiqueEvidence.get(field);
    if (!evidence) {
      return null;
    }
    return (
      <small className="critique-evidence-note">
        evidence: {evidence.evidence_snippet_id || "none"} · confidence: {evidence.confidence || "low"}
        {evidence.rationale ? ` · ${evidence.rationale}` : ""}
      </small>
    );
  };

  return (
    <section className="direction-detail" aria-label="selected paper detail">
      <div className="direction-detail-header">
        <div>
          <p className="section-kicker">Selected Paper Detail</p>
          <h2>{reading.paper.title}</h2>
        </div>
        {reading.paper.url ? (
          <a href={reading.paper.url} rel="noreferrer" target="_blank">
            open paper
          </a>
        ) : null}
      </div>

      <article className="direction-abstract">
        <h3>摘要中文内容</h3>
        <p>{reading.abstract_translation}</p>
      </article>

      {signals ? (
        <article className="paper-signals-panel" aria-label="paper evidence signals">
          <div className="paper-signals-header">
            <div>
              <p className="section-kicker">Paper Signals</p>
              <h3>论文证据信号</h3>
            </div>
            <FileText size={18} />
          </div>
          <div className="paper-signals-grid">
            <div>
              <strong>任务</strong>
              <span>{signals.task || "暂无"}</span>
            </div>
            <div>
              <strong>类型</strong>
              <span>{signals.contribution_type || "unknown"}</span>
            </div>
            <div>
              <strong>方法</strong>
              <span>{signals.method || "暂无"}</span>
            </div>
            <div>
              <strong>数据集</strong>
              <span>{signals.dataset || "暂无"}</span>
            </div>
            <div>
              <strong>指标</strong>
              <span>{signals.metric || "暂无"}</span>
            </div>
            <div>
              <strong>Claim</strong>
              <span>{signals.claim || "暂无"}</span>
            </div>
            <div>
              <strong>Limitation</strong>
              <span>{signals.limitation || "暂无"}</span>
            </div>
            <div>
              <strong>缺失字段</strong>
              <span>{missingSignals.length ? missingSignals.join(", ") : "none"}</span>
            </div>
          </div>
        </article>
      ) : null}

      <article className="research-sight-panel">
        <div className="research-sight-header">
          <div>
            <p className="section-kicker">Research Sight</p>
            <h3>科研审美评价</h3>
          </div>
          <BrainCircuit size={18} />
        </div>
        <div className="research-sight-score-grid">
          <div>
            <strong>证据等级</strong>
            <span>{reading.research_sight.evidence_pack.grounding_summary}</span>
          </div>
          <div>
            <strong>动机锋利度</strong>
            <span>{reading.research_sight.motivation_sharpness}</span>
          </div>
          <div>
            <strong>解法优雅性</strong>
            <span>{reading.research_sight.solution_elegance}</span>
          </div>
          <div>
            <strong>评估真实性</strong>
            <span>{reading.research_sight.evaluation_integrity}</span>
          </div>
          <div>
            <strong>范式启发性</strong>
            <span>{reading.research_sight.paradigm_inspiration}</span>
          </div>
        </div>
        <div className="research-sight-critique">
          <div>
            <strong>为什么好</strong>
            <p>{reading.research_sight.why_good}</p>
            {renderCritiqueEvidence("why_good")}
          </div>
          <div>
            <strong>为什么不好</strong>
            <p>{reading.research_sight.why_not_good}</p>
            {renderCritiqueEvidence("why_not_good")}
          </div>
          <div>
            <strong>更好角度</strong>
            <p>{reading.research_sight.better_angle}</p>
            {renderCritiqueEvidence("better_angle")}
          </div>
          <div>
            <strong>Baseline 对比</strong>
            <p>{reading.research_sight.baseline_comparison}</p>
            {renderCritiqueEvidence("baseline_comparison")}
          </div>
          <div>
            <strong>下一步 proposal</strong>
            <p>{reading.research_sight.next_step_proposal}</p>
            {renderCritiqueEvidence("next_step_proposal")}
          </div>
        </div>
        <div className="sight-evidence-grid" aria-label="research sight evidence">
          <div>
            <strong>证据片段</strong>
            {reading.research_sight.evidence_pack.snippets.length ? (
              reading.research_sight.evidence_pack.snippets.slice(0, 4).map((snippet) => (
                <article key={`${snippet.source}-${snippet.id}`}>
                  <span>{snippet.source} · {snippet.kind} · {snippet.confidence}</span>
                  <p>{snippet.text}</p>
                  <small>{snippet.note}</small>
                </article>
              ))
            ) : (
              <p>当前没有可用证据片段。</p>
            )}
          </div>
          <div>
            <strong>缺失证据</strong>
            {reading.research_sight.evidence_pack.missing_evidence.length ? (
              <ul>
                {reading.research_sight.evidence_pack.missing_evidence.slice(0, 5).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>当前没有显式缺失项。</p>
            )}
          </div>
        </div>
      </article>

      <div className="direction-key-findings">
        <div>
          <strong>最脆弱假设</strong>
          <span>{reading.weakest_assumption}</span>
        </div>
        <div>
          <strong>一周最小复现</strong>
          <span>{reading.minimal_reproduction}</span>
        </div>
        <div>
          <strong>反例设计</strong>
          <span>{reading.counterexample}</span>
        </div>
        <div>
          <strong>Follow-up Idea</strong>
          <span>{reading.follow_up_idea}</span>
        </div>
      </div>

      <div className="direction-section-list">
        {reading.sections.map((section, index) => (
          <article className="direction-detail-section" key={section.id}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <h3>{section.title}</h3>
              <p>{section.content}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ResearchMemoryView({
  apiStatus,
  direction,
  isQuerying,
  onQuestionChange,
  onQuery,
  onTopKChange,
  question,
  result,
  topK,
}: {
  apiStatus: ApiStatus;
  direction: string;
  isQuerying: boolean;
  onQuestionChange: (question: string) => void;
  onQuery: () => void;
  onTopKChange: (topK: number) => void;
  question: string;
  result: ApiResearchMemoryQueryResponse | null;
  topK: number;
}) {
  const canQuery = apiStatus === "online" && !isQuerying && question.trim().length > 0;

  return (
    <div className="memory-stack">
      <section className="memory-control-panel" aria-label="paper memory query">
        <div className="memory-control-header">
          <div>
            <p className="section-kicker">Paper Memory Bank</p>
            <h2>基于已读论文的长期记忆问答</h2>
          </div>
          <button className="secondary-command" disabled={!canQuery} type="button" onClick={onQuery}>
            <Search size={17} />
            {isQuerying ? "检索中" : "检索记忆并回答"}
          </button>
        </div>

        <div className="memory-control-grid">
          <label>
            用户问题
            <textarea value={question} onChange={(event) => onQuestionChange(event.target.value)} />
          </label>
          <label>
            检索论文数
            <select value={topK} onChange={(event) => onTopKChange(Number(event.target.value))}>
              <option value={3}>3 篇</option>
              <option value={5}>5 篇</option>
              <option value={8}>8 篇</option>
            </select>
          </label>
        </div>

        <div className="memory-chip-row">
          <span>当前方向：{direction || "未指定"}</span>
          <span>每轮 10 篇</span>
          <span>30 篇上限</span>
          <span>检索 3-8 篇后回答</span>
        </div>
      </section>

      {result ? (
        <>
          <section className="memory-answer-panel" aria-label="memory answer">
            <div className="memory-answer-header">
              <div>
                <p className="section-kicker">Memory-Grounded Answer</p>
                <h2>{result.question}</h2>
              </div>
              <div className="memory-stat-grid">
                <span>{result.total_memories} memories</span>
                <span>{result.hits.length} hits</span>
                <span>top {result.top_k}</span>
              </div>
            </div>
            <p>{result.answer}</p>
            {result.direction_memory ? (
              <div className="memory-direction-box">
                <strong>{result.direction_memory.direction}</strong>
                <span>{result.direction_memory.summary}</span>
                {result.direction_memory.baseline_map ? (
                  <small>
                    BaselineMap：
                    {result.direction_memory.baseline_map.recent_strong_baselines
                      .slice(0, 2)
                      .map((reference) => reference.title)
                      .join(" / ") || "暂无强参照"}
                  </small>
                ) : null}
              </div>
            ) : null}
            {result.warnings.length ? (
              <div className="retrieval-errors">
                <strong>Memory 警告</strong>
                <p>{result.warnings.join(" / ")}</p>
              </div>
            ) : null}
          </section>

          <section className="memory-hit-list" aria-label="retrieved paper memories">
            {result.hits.map((hit, index) => (
              <article className="memory-hit-card" key={`${hit.paper.id}-${index}`}>
                <div className="memory-hit-header">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{hit.score.toFixed(2)}</strong>
                  {hit.self_read_priority ? <small>推荐精读</small> : null}
                </div>
                <h3>{hit.paper.title}</h3>
                <div className="memory-hit-meta">
                  <span>Round {hit.round}</span>
                  <span>{hit.paper.year || "year unknown"}</span>
                  <span>{hit.paper.venue || hit.paper.source || "source unknown"}</span>
                </div>
                <div className="memory-hit-score-grid" aria-label="memory score breakdown">
                  <span>title {hit.title_score.toFixed(2)}</span>
                  <span>keyword {hit.keyword_score.toFixed(2)}</span>
                  <span>section {hit.section_score.toFixed(2)}</span>
                  <span>priority {hit.priority_score.toFixed(2)}</span>
                </div>
                <p>{hit.snippets[0]}</p>
                <dl>
                  <div>
                    <dt>最脆弱假设</dt>
                    <dd>{hit.weakest_assumption}</dd>
                  </div>
                  <div>
                    <dt>一周验证</dt>
                    <dd>{hit.minimal_reproduction}</dd>
                  </div>
                  <div>
                    <dt>反例设计</dt>
                    <dd>{hit.counterexample}</dd>
                  </div>
                  <div>
                    <dt>审美批判</dt>
                    <dd>{hit.research_sight.why_not_good || "暂无 ResearchSight 批判字段"}</dd>
                  </div>
                  <div>
                    <dt>更好角度</dt>
                    <dd>{hit.research_sight.better_angle || "暂无 ResearchSight 破局视角"}</dd>
                  </div>
                  <div>
                    <dt>证据等级</dt>
                    <dd>{hit.research_sight.evidence_pack.grounding_summary || "暂无 EvidencePack"}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </section>
        </>
      ) : (
        <section className="memory-empty-state">
          <BrainCircuit size={22} />
          <div>
            <h2>先执行方向精读，再提问</h2>
            <p>
              Paper Memory Bank 会从方向精读生成的论文卡片中提取结构化记忆。用户提问时，系统只检索最相关的
              3-8 篇论文，再基于这些命中回答。
            </p>
          </div>
        </section>
      )}
    </div>
  );
}

function PaperReaderView({
  apiStatus,
  card,
  isGenerating,
  onGenerate,
  onInputChange,
  onSelectedPaperChange,
  papers,
  selectedPaperId,
  supplementalInput,
}: {
  apiStatus: ApiStatus;
  card: ApiPaperCard | null;
  isGenerating: boolean;
  onGenerate: () => void;
  onInputChange: (value: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  papers: PaperRow[];
  selectedPaperId: string;
  supplementalInput: string;
}) {
  const sections = [
    "研究问题与背景",
    "已有研究与不足",
    "作者思考路径重建",
    "核心 intuition",
    "方法 pipeline",
    "数学与理论解释",
    "实验如何验证 claim",
    "Take-aways",
    "最脆弱的假设",
    "一周最小复现实验",
    "反例设计",
    "非增量 follow-up idea",
  ];
  const selectedPaper = papers.find((paper) => paper.id === selectedPaperId) ?? papers[0];

  return (
    <div className="reader-stack">
      <section className="paper-reader-controls">
        <div className="paper-reader-header">
          <div>
            <p className="section-kicker">Deep Paper Card</p>
            <h2>{selectedPaper?.title ?? "选择一篇论文生成 12 段精读卡片"}</h2>
          </div>
          <button
            className="secondary-command"
            disabled={apiStatus !== "online" || isGenerating || (!selectedPaper && supplementalInput.trim().length === 0)}
            type="button"
            onClick={onGenerate}
          >
            <BrainCircuit size={17} />
            {isGenerating ? "生成中" : "生成 Paper Card"}
          </button>
        </div>

        <div className="paper-reader-grid">
          <label>
            选择论文
            <select value={selectedPaperId} onChange={(event) => onSelectedPaperChange(event.target.value)}>
              {papers.map((paper) => (
                <option key={paper.id} value={paper.id}>
                  {paper.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            补充摘要 / 正文片段
            <textarea
              placeholder="可选：粘贴 abstract、method 或 experiment 片段。当前阶段不会下载 PDF。"
              value={supplementalInput}
              onChange={(event) => onInputChange(event.target.value)}
            />
          </label>
        </div>

        <div className="quote-block">
          <AlertTriangle size={18} />
          <span>Phase 7 输出结构化 paper card；不会编造完整 PDF 细节，缺失信息会明确标记为基于有限输入的推断。</span>
        </div>
      </section>

      <div className="reader-layout">
        <section className="paper-summary">
          <p className="section-kicker">Selected Paper</p>
          <h2>{selectedPaper?.title ?? "No paper selected"}</h2>
          <p>{selectedPaper?.abstract || selectedPaper?.relation || "先在 Paper Table 检索或选择论文。"}</p>
          {card ? (
            <div className="quote-block">
              <AlertTriangle size={18} />
              <span>{card.weakest_assumption}</span>
            </div>
          ) : null}
        </section>

        <section className="protocol-list" aria-label="deep paper card sections">
          {card
            ? card.sections.map((section, index) => (
                <article className="paper-card-section" key={section.id}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{section.title}</h3>
                    <p>{section.content}</p>
                  </div>
                </article>
              ))
            : sections.map((section, index) => (
                <div className="protocol-row" key={section}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <p>{section}</p>
                </div>
              ))}
        </section>
      </div>
    </div>
  );
}

function GapBoardView({
  apiStatus,
  decision,
  goal,
  isGenerating,
  onGenerate,
  onGoalChange,
}: {
  apiStatus: ApiStatus;
  decision: ApiResearchDecisionResponse | null;
  goal: string;
  isGenerating: boolean;
  onGenerate: () => void;
  onGoalChange: (goal: string) => void;
}) {
  const gaps = decision?.gaps ?? gapItems.map((gap, index) => ({
    id: `mock_${index}`,
    title: gap.title,
    kind: index === 0 ? "true_gap" : index === 1 ? "engineering_gap" : "pseudo_gap",
    evidence: "静态示例，生成后会替换为基于 paper table / paper card 的证据。",
    weakness: gap.weakness,
    opportunity: gap.opportunity,
    novelty_risk: gap.risk,
    feasibility: index === 0 ? "one-week" : index === 1 ? "one-week" : "one-month",
  }));

  return (
    <div className="view-stack">
      <section className="decision-panel" aria-label="research decision generator">
        <div className="decision-header">
          <div>
            <p className="section-kicker">Research Decision</p>
            <h2>Gap / Novelty / Experiment Plan</h2>
          </div>
          <button
            className="secondary-command"
            disabled={apiStatus !== "online" || isGenerating}
            type="button"
            onClick={onGenerate}
          >
            <GitBranch size={17} />
            {isGenerating ? "生成中" : "生成研究决策"}
          </button>
        </div>
        <label>
          决策目标
          <textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} />
        </label>
        {decision ? (
          <div className="validation-summary">
            <strong>Idea Validation</strong>
            <p>{decision.validation.idea}</p>
            <span className={`risk ${decision.validation.novelty_risk}`}>{decision.validation.novelty_risk}</span>
            <span>{decision.validation.feasibility}</span>
          </div>
        ) : null}
      </section>

      <div className="gap-board">
        {gaps.map((gap) => (
          <article className="gap-card" key={gap.id}>
            <div className="gap-card-header">
              <h2>{gap.title}</h2>
              <span className={`risk ${gap.novelty_risk}`}>{gap.novelty_risk}</span>
            </div>
            <div className={`gap-kind ${gap.kind}`}>{gap.kind}</div>
            <dl>
              <div>
                <dt>Evidence</dt>
                <dd>{gap.evidence}</dd>
              </div>
              <div>
                <dt>Weakness</dt>
                <dd>{gap.weakness}</dd>
              </div>
              <div>
                <dt>Opportunity</dt>
                <dd>{gap.opportunity}</dd>
              </div>
              <div>
                <dt>Feasibility</dt>
                <dd>{gap.feasibility}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}

function ExperimentPlannerView({
  apiStatus,
  decision,
  goal,
  isGenerating,
  onGenerate,
  onGoalChange,
}: {
  apiStatus: ApiStatus;
  decision: ApiResearchDecisionResponse | null;
  goal: string;
  isGenerating: boolean;
  onGenerate: () => void;
  onGoalChange: (goal: string) => void;
}) {
  const plan = decision?.experiment;
  const isBlocked = plan?.status === "blocked";

  return (
    <div className="view-stack">
      <section className="decision-panel" aria-label="experiment plan generator">
        <div className="decision-header">
          <div>
            <p className="section-kicker">Experiment Plan</p>
            <h2>{plan ? (isBlocked ? "缺少可复现实验 anchor" : "One-week Minimal Experiment") : "从 gap 生成实验计划"}</h2>
          </div>
          <button
            className="secondary-command"
            disabled={apiStatus !== "online" || isGenerating}
            type="button"
            onClick={onGenerate}
          >
            <FlaskConical size={17} />
            {isGenerating ? "生成中" : "生成实验计划"}
          </button>
        </div>
        <label>
          实验目标
          <textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} />
        </label>
      </section>

      {plan ? (
        <section className={`experiment-detail ${isBlocked ? "blocked" : "ready"}`}>
          <h2>{plan.claim}</h2>
          <dl>
            <div>
              <dt>Status</dt>
              <dd>{plan.status}</dd>
            </div>
            <div>
              <dt>Anchor</dt>
              <dd>{plan.anchor_paper_title || "N/A"}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>{plan.dataset || "N/A"}</dd>
            </div>
            <div>
              <dt>Baseline</dt>
              <dd>{plan.baseline || "N/A"}</dd>
            </div>
            <div>
              <dt>Metrics</dt>
              <dd>{plan.metrics.join(", ")}</dd>
            </div>
            <div>
              <dt>Ablations</dt>
              <dd>{plan.ablations.join(" / ")}</dd>
            </div>
            <div>
              <dt>Resources</dt>
              <dd>{plan.resources}</dd>
            </div>
          </dl>
        </section>

      ) : null}

      <div className="experiment-list">
        {(plan
          ? plan.timeline.map((step, index) => ({
              week: `Step ${index + 1}`,
              goal: step,
              deliverable: index === plan.timeline.length - 1 ? plan.success_criterion : plan.claim,
              cost: isBlocked ? "blocked" : index === 0 ? plan.resources : "tracked",
            }))
          : experiments
        ).map((item) => (
          <section className="experiment-row" key={item.week}>
            <div className="experiment-date">{item.week}</div>
            <div>
              <h2>{item.goal}</h2>
              <p>{item.deliverable}</p>
            </div>
            <span>{item.cost}</span>
          </section>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function PlanChecklist({ steps }: { steps: PlanStep[] }) {
  return (
    <section className="side-panel" aria-label="plan checklist">
      <div className="panel-heading">
        <h2>Plan Checklist</h2>
        <span>
          {steps.filter((step) => step.status === "done").length}/{steps.length}
        </span>
      </div>
      <div className="plan-list">
        {steps.map((step) => (
          <div className="plan-step" key={step.id}>
            <StatusIcon status={step.status} />
            <div>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function StatusIcon({ status }: { status: PlanStatus }) {
  if (status === "done") {
    return <CheckCircle2 className="status done" size={18} />;
  }
  if (status === "active") {
    return <Clock3 className="status active" size={18} />;
  }
  if (status === "blocked") {
    return <AlertTriangle className="status blocked" size={18} />;
  }
  return <Circle className="status queued" size={18} />;
}

function ToolTimeline({ events }: { events: TimelineEvent[] }) {
  return (
    <section className="side-panel" aria-label="tool timeline">
      <div className="panel-heading">
        <h2>Tool Timeline</h2>
        <FileText size={17} />
      </div>
      <div className="timeline-list">
        {events.map((event) => {
          const Icon = getToolEventIcon(event.tool);
          return (
            <article className={`timeline-event ${event.status}`} key={`${event.time}-${event.tool}-${event.summary}`}>
              <time>{event.time}</time>
              <div className="timeline-icon">
                <Icon size={15} />
              </div>
              <div>
                <strong>{event.tool}</strong>
                <p>{event.summary}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function getToolEventIcon(tool: string): LucideIcon {
  if (tool.includes("memory")) {
    return BrainCircuit;
  }
  if (tool.includes("literature") || tool.includes("retrieve") || tool.includes("query")) {
    return Search;
  }
  if (tool.includes("paper") || tool.includes("read")) {
    return BookOpen;
  }
  if (tool.includes("artifact") || tool.includes("save")) {
    return Save;
  }
  if (tool.includes("gap") || tool.includes("novelty")) {
    return GitBranch;
  }
  if (tool.includes("experiment")) {
    return FlaskConical;
  }
  if (tool.includes("plan") || tool.includes("agent")) {
    return BrainCircuit;
  }
  return FileText;
}

interface ArtifactPreviewProps {
  activeTab: ArtifactTab;
  apiStatus: ApiStatus;
  artifact: ArtifactContent;
  isSaving: boolean;
  lastSavedArtifact: ApiArtifact | null;
  onArtifactChange: (artifact: ArtifactContent) => void;
  onSave: () => void;
  onTabChange: (tab: ArtifactTab) => void;
}

function ArtifactPreview({
  activeTab,
  apiStatus,
  artifact,
  isSaving,
  lastSavedArtifact,
  onArtifactChange,
  onSave,
  onTabChange,
}: ArtifactPreviewProps) {
  const content = artifact[activeTab];

  function updateArtifactField(field: keyof ArtifactContent, value: string) {
    onArtifactChange({
      ...artifact,
      [field]: value,
    });
  }

  return (
    <aside className="artifact-preview" aria-label="artifact preview">
      <div className="artifact-header">
        <div>
          <p className="section-kicker">Editable Artifact</p>
          <input
            aria-label="artifact title"
            className="artifact-title-input"
            value={artifact.title}
            onChange={(event) => updateArtifactField("title", event.target.value)}
          />
        </div>
        <button
          className="secondary-command"
          disabled={apiStatus !== "online" || isSaving}
          type="button"
          onClick={onSave}
        >
          <Save size={17} />
          {isSaving ? "保存中" : "保存"}
        </button>
      </div>

      <div className="segmented-control" role="tablist" aria-label="artifact format">
        {(["markdown", "json", "diff"] as ArtifactTab[]).map((tab) => (
          <button
            className={activeTab === tab ? "active" : ""}
            key={tab}
            type="button"
            onClick={() => onTabChange(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="artifact-meta">
        <span>{apiStatus === "online" ? "可编辑并保存到 SQLite" : "离线预览，启动 API 后可保存"}</span>
        <span>{lastSavedArtifact ? `当前来源: ${lastSavedArtifact.id}` : "当前来源: 内置示例"}</span>
      </div>

      <textarea
        className="artifact-editor"
        value={content}
        onChange={(event) => updateArtifactField(activeTab, event.target.value)}
      />
    </aside>
  );
}

function selectArtifactForView(items: ApiArtifact[], view: ViewId): ApiArtifact | null {
  const patterns: Record<ViewId, string[]> = {
    dashboard: ["agent_run", "agent_plan"],
    "new-project": [],
    "paper-table": ["paper_table", "literature_search"],
    "direction-review": ["direction_review", "baseline_map"],
    "paper-memory": ["research_memory_answer", "direction_memory"],
    "paper-reader": ["paper_card"],
    "gap-board": ["gap_board", "idea_validation"],
    "experiment-planner": ["experiment_plan"],
  };
  const wanted = patterns[view] ?? [];
  return (
    items.find((artifact) => {
      const title = artifact.title.toLowerCase();
      return wanted.some((pattern) => title.includes(pattern));
    }) ?? items[0] ?? null
  );
}

function toPaperRow(paper: ApiPaper): PaperRow {
  return {
    id: paper.id,
    title: paper.title,
    authors: paper.authors,
    abstract: paper.abstract,
    year: paper.year,
    type: paper.type,
    venue: paper.venue,
    source: paper.source,
    url: paper.url,
    relation: paper.relation,
    priority: paper.priority === "High" || paper.priority === "Medium" || paper.priority === "Watch" ? paper.priority : "Medium",
    code: paper.code,
    relevanceScore: paper.relevance_score,
  };
}

function toTimelineEvent(event: ApiToolEvent): TimelineEvent {
  return {
    time: event.time_label,
    tool: event.tool,
    status: event.status,
    summary: event.summary,
  };
}

function toPlanStep(step: ApiAgentPlanStep): PlanStep {
  return {
    id: step.id,
    title: step.title,
    detail: step.detail,
    status: toPlanStatus(step.status),
  };
}

function toPlanStatus(status: ApiAgentPlanStep["status"]): PlanStatus {
  if (status === "done") {
    return "done";
  }
  if (status === "running") {
    return "active";
  }
  return "queued";
}
