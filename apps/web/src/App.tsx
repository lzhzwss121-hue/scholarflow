import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  Circle,
  Clock3,
  Download,
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
  type ApiPaper,
  type ApiProject,
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
  createProject,
  executeAgentRun,
  getArtifact,
  getHealth,
  getProjectTimeline,
  listProjectArtifacts,
  listProjectPapers,
  listProjects,
  saveArtifact,
} from "./apiClient";
import "./styles.css";

type ArtifactTab = "markdown" | "json" | "diff";
type ApiStatus = "checking" | "online" | "offline";

const navIcons: Record<ViewId, LucideIcon> = {
  dashboard: LayoutDashboard,
  "new-project": Plus,
  "paper-table": Table2,
  "paper-reader": BookOpen,
  "gap-board": GitBranch,
  "experiment-planner": FlaskConical,
};

const viewTitles: Record<ViewId, string> = {
  dashboard: "项目总览",
  "new-project": "新建科研项目",
  "paper-table": "论文表格",
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
  const [agentTask, setAgentTask] = useState(
    "请基于 VLM hallucination benchmark 方向，生成一个从文献表到可验证 gap 的最小科研任务计划。",
  );
  const [agentPlan, setAgentPlan] = useState<ApiAgentPlanResponse | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);

  const activeArtifact = artifacts[activeView];
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
  }

  async function handleCreateProject() {
    setApiMessage("正在创建本地 research project...");
    try {
      const project = await createProject({
        title: "VLM Hallucination Benchmark",
        description: "从可信多模态评测出发，定位证据错误和 visual grounding 失败。",
        keyword: "VLM hallucination benchmark",
        field: "Trustworthy AI / Multimodal Evaluation",
        language: "zh-CN",
        workflow: "survey-to-experiment",
      });
      const nextProjects = [project, ...projects.filter((item) => item.id !== project.id)];
      setApiStatus("online");
      setProjects(nextProjects);
      setActiveProject(project);
      setActiveView("dashboard");
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

    setApiMessage("正在保存当前 artifact 到 SQLite...");
    try {
      const saved = await saveArtifact({
        project_id: activeProject.id,
        title: activeArtifact.title,
        kind: artifactTab,
        content_markdown: activeArtifact.markdown,
        content_json: activeArtifact.json,
        diff: activeArtifact.diff,
      });
      const reloaded = await getArtifact(saved.id);
      setLastSavedArtifact(reloaded);
      setPersistedArtifactCount((count) => count + 1);
      setApiMessage(`Artifact 已保存并回读: ${reloaded.id}`);
      const refreshedTimeline = await getProjectTimeline(activeProject.id);
      setTimelineRows(refreshedTimeline.map(toTimelineEvent));
    } catch (error) {
      setApiMessage("保存 artifact 失败，请确认 API 与 SQLite 工作区可用。");
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
        provider: "deepseek",
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

  return (
    <div className="scholarflow-app">
      <ProjectNavigator
        activeProject={activeProject}
        activeView={activeView}
        apiStatus={apiStatus}
        artifactCount={persistedArtifactCount}
        onSelect={setActiveView}
        paperCount={paperRows.length}
        projectCount={projects.length}
      />

      <main className="agent-workspace">
        <header className="workspace-header">
          <div>
            <p className="phase-label">Phase 5 / Minimal Agent Core</p>
            <h1>{viewTitles[activeView]}</h1>
          </div>
          <div className="toolbar" aria-label="workspace actions">
            <button className="icon-button" title="运行静态工作流" type="button">
              <Play size={17} />
            </button>
            <button className="icon-button" title="保存 Artifact 到 API" type="button" onClick={handleSaveArtifact}>
              <Save size={17} />
            </button>
            <button className="icon-button" title="导出 Artifact" type="button">
              <Download size={17} />
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
              onAgentTaskChange={setAgentTask}
              onCreateProject={handleCreateProject}
              onCreateAgentPlan={handleCreateAgentPlan}
              onExecuteAgentRun={handleExecuteAgentRun}
              paperRows={paperRows}
              projectCount={projects.length}
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
        artifact={activeArtifact}
        lastSavedArtifact={lastSavedArtifact}
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
  paperCount: number;
  projectCount: number;
}

function ProjectNavigator({
  activeProject,
  activeView,
  apiStatus,
  artifactCount,
  onSelect,
  paperCount,
  projectCount,
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
        <h2>{activeProject?.title ?? "VLM Hallucination Benchmark"}</h2>
        <div className="tag-row">
          <span>Trustworthy AI</span>
          <span>VLM</span>
          <span>Evaluation</span>
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
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onCreateProject: () => void;
  onExecuteAgentRun: () => void;
  paperRows: PaperRow[];
  projectCount: number;
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
  onAgentTaskChange,
  onCreateAgentPlan,
  onCreateProject,
  onExecuteAgentRun,
  paperRows,
  projectCount,
  view,
}: ActiveViewProps) {
  switch (view) {
    case "new-project":
      return <NewProjectView apiMessage={apiMessage} apiStatus={apiStatus} onCreateProject={onCreateProject} />;
    case "paper-table":
      return <PaperTableView papers={paperRows} />;
    case "paper-reader":
      return <PaperReaderView />;
    case "gap-board":
      return <GapBoardView />;
    case "experiment-planner":
      return <ExperimentPlannerView />;
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
  paperCount: number;
  projectCount: number;
}) {
  return (
    <div className="view-stack">
      <section className="brief-panel">
        <div>
          <p className="section-kicker">Current Task</p>
          <h2>{activeProject?.title ?? "从 VLM hallucination benchmark 找到可验证研究 gap"}</h2>
        </div>
        <p>
          当前阶段已经接入最小 Agent Loop。系统会先保存 Research Plan，等待确认后执行 mock tools，
          并把每个工具调用写入 session timeline。
        </p>
      </section>

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

      <section className="workflow-strip" aria-label="research workflow">
        {["Project", "Plan", "Tools", "Artifacts", "Timeline", "Confirm"].map((item, index) => (
          <div className="workflow-node" key={item}>
            <span>{index + 1}</span>
            {item}
          </div>
        ))}
      </section>
    </div>
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

  return (
    <section className="agent-run-panel" aria-label="agent plan mode">
      <div className="agent-run-header">
        <div>
          <p className="section-kicker">Research Plan Mode</p>
          <h2>{agentPlan ? `Run ${agentPlan.run_id}` : "Agent Task"}</h2>
        </div>
        <span className={`run-status ${agentPlan?.status ?? "idle"}`}>{agentPlan?.status ?? "idle"}</span>
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
  onCreateProject,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  onCreateProject: () => void;
}) {
  return (
    <div className="view-stack">
      <section className="form-panel">
        <label>
          研究关键词
          <div className="input-shell">
            <Search size={17} />
            <input readOnly value="VLM hallucination benchmark" />
          </div>
        </label>
        <label>
          研究目标
          <textarea
            readOnly
            value="从可信多模态评测出发，定位现有 benchmark 无法暴露的证据错误和视觉 grounding 失败。"
          />
        </label>
        <div className="form-grid">
          <label>
            领域
            <input readOnly value="Trustworthy AI / Multimodal Evaluation" />
          </label>
          <label>
            输出语言
            <input readOnly value="中文为主，保留英文术语" />
          </label>
        </div>
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

function PaperTableView({ papers }: { papers: PaperRow[] }) {
  return (
    <section className="table-shell" aria-label="paper table">
      <table>
        <thead>
          <tr>
            <th>论文</th>
            <th>年份</th>
            <th>类型</th>
            <th>来源</th>
            <th>与方向关系</th>
            <th>优先级</th>
            <th>代码</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => (
            <tr key={paper.title}>
              <td>{paper.title}</td>
              <td>{paper.year}</td>
              <td>{paper.type}</td>
              <td>{paper.venue}</td>
              <td>{paper.relation}</td>
              <td>
                <span className={`priority ${paper.priority.toLowerCase()}`}>{paper.priority}</span>
              </td>
              <td>{paper.code}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function PaperReaderView() {
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

  return (
    <div className="reader-layout">
      <section className="paper-summary">
        <p className="section-kicker">Selected Paper</p>
        <h2>Faithful Visual Question Answering Requires Grounded Evidence</h2>
        <p>
          当前阅读重点是把 answer correctness 和 evidence faithfulness 拆开，
          判断模型是否真的使用了图像证据，而不是依赖语言先验或 benchmark shortcut。
        </p>
        <div className="quote-block">
          <AlertTriangle size={18} />
          <span>最脆弱假设：人工证据标签足以代表模型真实视觉依据。</span>
        </div>
      </section>

      <section className="protocol-list" aria-label="deep paper card sections">
        {sections.map((section, index) => (
          <div className="protocol-row" key={section}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <p>{section}</p>
          </div>
        ))}
      </section>
    </div>
  );
}

function GapBoardView() {
  return (
    <div className="gap-board">
      {gapItems.map((gap) => (
        <article className="gap-card" key={gap.title}>
          <div className="gap-card-header">
            <h2>{gap.title}</h2>
            <span className={`risk ${gap.risk}`}>{gap.risk}</span>
          </div>
          <dl>
            <div>
              <dt>Weakness</dt>
              <dd>{gap.weakness}</dd>
            </div>
            <div>
              <dt>Opportunity</dt>
              <dd>{gap.opportunity}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function ExperimentPlannerView() {
  return (
    <div className="experiment-list">
      {experiments.map((item) => (
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
        {events.map((event) => (
          <article className={`timeline-event ${event.status}`} key={`${event.time}-${event.tool}-${event.summary}`}>
            <time>{event.time}</time>
            <div>
              <strong>{event.tool}</strong>
              <p>{event.summary}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

interface ArtifactPreviewProps {
  activeTab: ArtifactTab;
  apiStatus: ApiStatus;
  artifact: ArtifactContent;
  lastSavedArtifact: ApiArtifact | null;
  onTabChange: (tab: ArtifactTab) => void;
}

function ArtifactPreview({ activeTab, apiStatus, artifact, lastSavedArtifact, onTabChange }: ArtifactPreviewProps) {
  const previewArtifact = lastSavedArtifact
    ? {
        title: lastSavedArtifact.title,
        markdown: lastSavedArtifact.content_markdown,
        json: lastSavedArtifact.content_json,
        diff: lastSavedArtifact.diff,
      }
    : artifact;
  const content = previewArtifact[activeTab];

  return (
    <aside className="artifact-preview" aria-label="artifact preview">
      <div className="artifact-header">
        <div>
          <p className="section-kicker">Artifact Preview</p>
          <h2>{previewArtifact.title}</h2>
        </div>
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
        <span>{apiStatus === "online" ? "SQLite writable" : "Preview only"}</span>
        <span>{lastSavedArtifact ? `Last saved: ${lastSavedArtifact.id}` : "Not saved this session"}</span>
      </div>

      <pre className="artifact-code">{content}</pre>
    </aside>
  );
}

function toPaperRow(paper: ApiPaper): PaperRow {
  return {
    title: paper.title,
    year: paper.year,
    type: paper.type,
    venue: paper.venue,
    relation: paper.relation,
    priority: paper.priority === "High" || paper.priority === "Medium" || paper.priority === "Watch" ? paper.priority : "Medium",
    code: paper.code,
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
