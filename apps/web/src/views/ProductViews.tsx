import { type ReactNode, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  BookOpen,
  BrainCircuit,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Circle,
  Clock3,
  Download,
  Filter,
  FileText,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Lightbulb,
  Network,
  Play,
  Plus,
  Rocket,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Table2,
  Target,
  Trophy,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  SCHOLARFLOW_VERSION,
  type ApiAgentPlanResponse,
  type ApiAgentPlanStep,
  type ApiAgentRunStatusResponse,
  type ApiArtifact,
  type ApiArtifactRef,
  type ApiArtifactSummary,
  type ApiDirectionPaperReading,
  type ApiDirectionReviewResponse,
  type ApiEvidencePack,
  type ApiFullTextProvenance,
  type ApiPaperCard,
  type ApiProject,
  type ApiRagAnswerResponse,
  type ApiResearchDecisionResponse,
  type ApiResearchMemoryQueryResponse,
  type ApiSignalEvidence,
} from "@scholarflow/schemas";
import {
  navItems,
  type ArtifactContent,
  type PaperRow,
  type PlanStep,
  type PlanStatus,
  type TimelineEvent,
  type ViewId,
} from "../mockData";
import { ApiOfflineNotice } from "../components/ApiOfflineNotice";
import { RagAnswerPanel } from "../components/RagAnswerPanel";
import { isRetrievalWarning } from "../apiClient";
import {
  normalizeEvidencePack,
  normalizeResearchSight,
  resolvePaperCardForPaper,
  toPlanStatus,
} from "../lib/artifactHydration";
import type { PaperCardMatchSource } from "../lib/artifactHydration";
import type {
  ApiStatus,
  ArtifactTab,
  ProjectDraft,
  WorkflowActions,
  WorkflowNotice,
  WorkflowStepStatus,
  WorkflowViewModel,
} from "../types/workflow";

const conferenceBadges = [
  "CVPR",
  "ICCV",
  "ECCV",
  "NeurIPS",
  "ICLR",
  "ICML",
  "AAAI",
  "IJCAI",
  "ACL",
  "EMNLP",
  "KDD",
  "SIGIR",
];

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

const coreViews = new Set<ViewId>([
  "paper-table",
  "direction-review",
  "paper-memory",
  "paper-reader",
  "gap-board",
  "experiment-planner",
]);

const PROJECT_DRAFT_STORAGE_KEY = "scholarflow.projectDraft";

export function WorkflowShell({
  activeView,
  actions,
  ariaLabel,
  children,
  onSelectView,
  viewModel,
}: {
  activeView: ViewId;
  actions: WorkflowActions;
  ariaLabel: string;
  children: ReactNode;
  onSelectView: (view: ViewId) => void;
  viewModel: WorkflowViewModel;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window === "undefined" ? true : window.innerWidth > 860,
  );
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const verifiedReaderCard =
    activeView === "paper-reader" &&
    viewModel.latestPaperCard?.evidence_level === "full_text" &&
    viewModel.latestPaperCard.full_text?.status === "extracted";
  const historicalNotices = verifiedReaderCard
    ? viewModel.warnings.filter((notice) => isSupersededFullTextNotice(notice.message))
    : [];
  const currentNotices = verifiedReaderCard
    ? viewModel.warnings.filter((notice) => !isSupersededFullTextNotice(notice.message))
    : viewModel.warnings;
  const latestRawNotice = currentNotices[0] ?? null;
  const latestNotice = latestRawNotice
    ? { ...latestRawNotice, message: summarizeWorkflowNotice(latestRawNotice.message) }
    : null;
  const activeStep = viewModel.workflowSteps.find((step) => step.id === activeView);
  const completedStepCount = viewModel.workflowSteps.filter((step) => step.status === "complete").length;
  const partialStepCount = viewModel.workflowSteps.filter((step) => step.status === "partial").length;
  const progressValue = completedStepCount + partialStepCount * 0.5;
  const returnedCount = viewModel.literatureCoverage.returned_count ?? viewModel.paperRows.length;
  const directionReadCount =
    viewModel.directionReview?.relevant_read_count ?? viewModel.directionReview?.round_read_count ?? 0;

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth <= 860) {
        setSidebarOpen(false);
      }
    }

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  function selectView(view: ViewId) {
    onSelectView(view);
    if (typeof window !== "undefined" && window.innerWidth <= 860) {
      setSidebarOpen(false);
    }
  }

  return (
    <div className={`workflow-shell ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"} ${inspectorOpen ? "inspector-open" : ""}`}>
      <aside className="workflow-rail" aria-label="workflow steps">
        <div className="workflow-brand-row">
          <button className="workflow-brand" type="button" onClick={() => selectView("dashboard")}>
            <span className="sf-logo small" aria-hidden="true">
              <span>S</span>
            </span>
            <span>
              <strong>ScholarFlow</strong>
              <small>Research workspace</small>
            </span>
          </button>
          <button
            aria-label="折叠工作流侧栏"
            className="workflow-shell-icon-button workflow-collapse-button"
            type="button"
            onClick={() => setSidebarOpen(false)}
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        <label className="project-select-block">
          <span className="project-select-label">
            <span>Active project</span>
            <small>{viewModel.projects.length} local</small>
          </span>
          <select
            aria-label="项目"
            value={viewModel.activeProject?.id ?? ""}
            onChange={(event) => actions.onSelectProject(event.target.value)}
          >
            <option value="">创建真实项目开始</option>
            {viewModel.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {isDemoProject(project) ? "Demo 项目（示例，不代表真实 workflow）: " : ""}
                {project.title}
              </option>
            ))}
          </select>
          <small className="project-select-meta">
            {viewModel.activeProject
              ? `${viewModel.activeProject.field || "General research"} · ${viewModel.activeProject.stage}`
              : "No demo auto-selection"}
          </small>
        </label>

        <div className="workflow-rail-heading">
          <span>Research pipeline</span>
          <strong>
            {completedStepCount}/{viewModel.workflowSteps.length}
          </strong>
        </div>
        <progress
          aria-label="workflow completion"
          className="workflow-progress"
          max={Math.max(viewModel.workflowSteps.length, 1)}
          value={progressValue}
        />

        <nav className="workflow-step-list">
          {viewModel.workflowSteps.map((step, index) => {
            const Icon = navIcons[step.id];
            const isActive = step.id === activeView || (activeView === "paper-reader" && step.id === "paper-reader");
            return (
              <button
                className={isActive ? "workflow-step active" : "workflow-step"}
                data-status={step.status}
                aria-current={isActive ? "page" : undefined}
                key={step.id}
                title={`${step.label}：${step.summary}`}
                type="button"
                onClick={() => selectView(step.id)}
              >
                <span className="workflow-step-icon" aria-hidden="true">
                  <Icon size={16} />
                  <small>{String(index + 1).padStart(2, "0")}</small>
                </span>
                <span>
                  <strong>{step.label}</strong>
                  <small title={step.summary}>{step.summary}</small>
                </span>
                <StatusPill status={step.status} />
              </button>
            );
          })}
        </nav>

        <footer className="workflow-rail-footer">
          <span>
            <i aria-hidden="true" />
            Local-first workspace
          </span>
          <small>v{SCHOLARFLOW_VERSION}</small>
        </footer>
      </aside>

      <main className="workflow-main" aria-label={ariaLabel}>
        <header className="workflow-header">
          <div className="workflow-header-copy">
            {!sidebarOpen ? (
              <button
                aria-label="展开工作流侧栏"
                className="workflow-shell-icon-button workflow-open-sidebar-button"
                type="button"
                onClick={() => setSidebarOpen(true)}
              >
                <ArrowRight size={16} />
              </button>
            ) : null}
            <p className="section-kicker">
              Workspace <span aria-hidden="true">/</span> {activeStep?.label ?? "Project overview"}
            </p>
            <h1 title={viewModel.activeProject?.title ?? "创建真实项目开始"}>
              {viewModel.activeProject?.title ?? "创建真实项目开始"}
            </h1>
            <span className="workflow-header-description">
              {viewModel.activeProject
                ? isDemoProject(viewModel.activeProject)
                  ? "Demo 项目仅用于界面预览，不代表真实 workflow 输出"
                  : viewModel.activeProject.workflow
                : "Demo 不会被自动选择；创建项目后开始真实科研工作流"}
            </span>
          </div>
          <div className="workflow-header-meta">
            <span className={`api-chip ${viewModel.apiStatus}`}>{viewModel.apiStatus}</span>
            <span data-testid="project-saved-paper-count" title="项目已保存论文：当前项目中已持久化并去重的论文总数。">
              项目已保存 {viewModel.paperRows.length}
            </span>
            <span data-testid="current-search-returned-count" title="当前检索返回：最近一轮 Literature Search 通过相关性门槛后返回的论文数。">
              当前检索返回 {returnedCount}
            </span>
            <span data-testid="current-direction-read-count" title="当前方向已读：最近一轮 Direction Review 已生成结构化阅读记录的强/中相关论文数。">
              当前方向已读 {directionReadCount}
            </span>
            <span title="保存在当前项目 SQLite 工作区中的 artifact 数。">{viewModel.artifactCount} 个产物</span>
            <button
              aria-expanded={inspectorOpen}
              className="secondary-command compact workflow-trace-button"
              type="button"
              onClick={() => setInspectorOpen((value) => !value)}
            >
              <FileText size={14} />
              研究轨迹
              <strong>{viewModel.warnings.length + viewModel.artifactCount}</strong>
            </button>
            <button className="secondary-command compact" type="button" onClick={() => selectView("new-project")}>
              <Plus size={15} />
              新建项目
            </button>
          </div>
        </header>

        {latestNotice ? (
          <div className={`workflow-latest-notice ${latestNotice.kind}`}>
            <AlertTriangle size={16} />
            <span>{latestNotice.message}</span>
          </div>
        ) : activeStep ? (
          <div className="workflow-latest-notice info">
            <CheckCircle2 size={16} />
            <span>
              当前步骤：{activeStep.label} · {activeStep.status}
            </span>
          </div>
        ) : null}

        <section className="workflow-content">{children}</section>
      </main>

      {inspectorOpen ? (
        <button
          aria-label="关闭研究轨迹"
          className="workflow-drawer-backdrop"
          type="button"
          onClick={() => setInspectorOpen(false)}
        />
      ) : null}

      {sidebarOpen ? (
        <button
          aria-label="关闭工作流侧栏"
          className="workflow-sidebar-backdrop"
          type="button"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <aside className="workflow-inspector" aria-label="workflow artifacts and warnings" hidden={!inspectorOpen}>
        <header className="workflow-inspector-header">
          <div>
            <p className="section-kicker">Research trace</p>
            <h2>Evidence context</h2>
          </div>
          <button
            aria-label="关闭研究轨迹"
            className="workflow-shell-icon-button"
            type="button"
            onClick={() => setInspectorOpen(false)}
          >
            <X size={16} />
          </button>
        </header>
        <WorkflowNoticeList notices={currentNotices} />
        {historicalNotices.length ? (
          <details className="workflow-history-notices">
            <summary>历史尝试 · {historicalNotices.length}</summary>
            <p>当前论文已有更高等级的全文证据，以下旧下载失败仅保留用于追溯。</p>
            <WorkflowNoticeList notices={historicalNotices} />
          </details>
        ) : null}
        <WorkflowArtifactPanel
          activeArtifact={viewModel.activeArtifact}
          artifacts={viewModel.artifactSummaries}
          lastSavedArtifact={viewModel.lastSavedArtifact}
          onLoadArtifact={actions.onLoadArtifact}
        />
        <WorkflowTimelinePanel events={viewModel.timelineRows} />
      </aside>
    </div>
  );
}

function StatusPill({ status }: { status: WorkflowStepStatus }) {
  return (
    <em className={`workflow-status ${status}`}>
      <span aria-hidden="true" />
      {status}
    </em>
  );
}

function WorkflowNoticeList({ notices }: { notices: WorkflowNotice[] }) {
  return (
    <section className="workflow-side-section">
      <div className="workflow-side-heading">
        <strong>Warnings</strong>
        <span>{notices.length}</span>
      </div>
      {notices.length ? (
        <div className="workflow-notice-list">
          {notices.map((notice) => (
            <article
              className={`workflow-notice ${notice.kind}`}
              data-testid={notice.message.startsWith("Artifact JSON") ? "artifact-hydration-warning" : undefined}
              key={notice.id}
            >
              <AlertTriangle size={15} />
              <p>{notice.message}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="workflow-empty-copy">暂无 warning / error。</p>
      )}
    </section>
  );
}

function WorkflowArtifactPanel({
  activeArtifact,
  artifacts,
  lastSavedArtifact,
  onLoadArtifact,
}: {
  activeArtifact: ArtifactContent;
  artifacts: ApiArtifactSummary[];
  lastSavedArtifact: ApiArtifact | null;
  onLoadArtifact: (artifactId: string) => void;
}) {
  const preview = activeArtifact.markdown || activeArtifact.json || "暂无 artifact 内容。";

  return (
    <section className="workflow-side-section">
      <div className="workflow-side-heading">
        <strong>Local Assets</strong>
        <span>{artifacts.length}</span>
      </div>
      <div className="workflow-artifact-list">
        {artifacts.slice(0, 6).map((artifact) => (
          <button key={artifact.id} type="button" onClick={() => onLoadArtifact(artifact.id)}>
            <FileText size={15} />
            <span>
              <strong>{artifact.title}</strong>
              <small>
                {artifact.kind} · {formatBytes(artifact.markdown_bytes + artifact.json_bytes)}
              </small>
            </span>
          </button>
        ))}
      </div>
      {!artifacts.length ? <p className="workflow-empty-copy">运行工作流后，这里会列出真实 artifact。</p> : null}
      <div className="workflow-artifact-preview">
        <small>{lastSavedArtifact ? `当前来源：${lastSavedArtifact.id}` : "当前没有已回读 artifact"}</small>
        <strong>{activeArtifact.title}</strong>
        <p>{preview.slice(0, 360)}</p>
      </div>
    </section>
  );
}

function WorkflowTimelinePanel({ events }: { events: TimelineEvent[] }) {
  return (
    <section className="workflow-side-section" data-testid="workflow-timeline">
      <div className="workflow-side-heading">
        <strong>Timeline</strong>
        <span>{events.length}</span>
      </div>
      {events.length ? (
        <div className="workflow-mini-timeline">
          {events.slice(0, 7).map((event) => {
            const Icon = getToolEventIcon(event.tool);
            return (
              <article key={`${event.time}-${event.tool}-${event.summary}`}>
                <Icon size={14} />
                <div>
                  <strong>{event.tool}</strong>
                  <p>{event.summary}</p>
                  <small>{event.time}</small>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="workflow-empty-copy">暂无后端 timeline 事件。</p>
      )}
    </section>
  );
}

export function ProductTopNav({
  activeView,
  onSelectView,
}: {
  activeView: ViewId;
  onSelectView: (view: ViewId) => void;
}) {
  const navLinks = ([
    { label: "首页", view: "dashboard" },
    { label: "新建项目", view: "new-project" },
    { label: "论文检索", view: "paper-table" },
    { label: "方向精读", view: "direction-review" },
    { label: "Paper Memory", view: "paper-memory" },
    { label: "Gap Board", view: "gap-board" },
    { label: "实验计划", view: "experiment-planner" },
  ] satisfies Array<{ label: string; view: ViewId }>);
  const activeTopView = activeView === "paper-reader" ? "paper-memory" : activeView;
  const readerChrome = activeView === "paper-reader";

  return (
    <header className={readerChrome ? "product-topbar reader" : "product-topbar"}>
      <button className="topbar-brand" type="button" onClick={() => onSelectView("dashboard")}>
        <span className="sf-logo">SF</span>
        <span>
          <strong>ScholarFlow</strong>
          <small>AI Research Workflow Agent</small>
        </span>
      </button>

      <nav className="topbar-nav" aria-label="primary navigation">
        {navLinks.map((item) => (
          <button
            className={activeTopView === item.view ? "active" : ""}
            key={item.label}
            type="button"
            onClick={() => onSelectView(item.view)}
          >
            {item.label}
          </button>
        ))}
        <button type="button">Docs</button>
      </nav>

      {readerChrome ? (
        <div className="topbar-reader-tools">
          <label className="topbar-search">
            <Search size={16} />
            <input placeholder="搜索论文、方向、笔记..." />
          </label>
          <button className="round-tool" type="button" aria-label="notifications">
            <Bell size={18} />
          </button>
          <button className="user-avatar" type="button" aria-label="profile">
            A
          </button>
        </div>
      ) : (
        <div className="topbar-actions">
          <button className="login-button" type="button">
            登录
          </button>
          <button className="gradient-button" type="button" onClick={() => onSelectView("new-project")}>
            <Plus size={16} />
            新建项目
          </button>
        </div>
      )}
    </header>
  );
}

function ConferenceLogoBelt({ withTitle = true }: { withTitle?: boolean }) {
  const badges = [...conferenceBadges, ...conferenceBadges];
  return (
    <section className="conference-logo-belt" aria-label="top AI conferences">
      {withTitle ? (
        <div className="conference-belt-title">
          <Trophy size={21} />
          <strong>面向顶会与主流会议</strong>
        </div>
      ) : null}
      <div className="conference-logo-mask">
        <div className="conference-logo-track">
          {badges.map((label, index) => (
            <span className={`conference-logo-chip tone-${index % 6}`} key={`${label}-${index}`}>
              <ConferenceGlyph label={label} />
              {label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function ConferenceGlyph({ label }: { label: string }) {
  const glyph = label.slice(0, 1);
  return <i aria-hidden="true">{glyph}</i>;
}

export function ProjectSidebar({
  activeProject,
  activeView,
  artifacts: artifactSummaries = [],
  compact = false,
  onLoadArtifact,
  onSelectView,
  paperCount,
  projectCount,
  artifactCount,
}: {
  activeProject: ApiProject | null;
  activeView: ViewId;
  artifacts?: ApiArtifactSummary[];
  compact?: boolean;
  onLoadArtifact?: (artifactId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
  artifactCount: number;
}) {
  const showBoostCard = activeView === "new-project";
  const showLocalAssets = !compact && activeView !== "new-project";
  const visibleArtifacts = artifactSummaries.slice(0, 5);
  const sidebarItems: Array<{ id: ViewId; label: string; icon: LucideIcon }> = [
    { id: "dashboard", label: "项目总览", icon: LayoutDashboard },
    { id: "new-project", label: "新建项目", icon: Plus },
    { id: "paper-table", label: "论文表格", icon: Search },
    { id: "direction-review", label: "方向精读", icon: FileText },
    { id: "paper-memory", label: "Paper Memory", icon: Network },
    { id: "paper-reader", label: compact ? "Deep Paper Card" : "Deep Paper Card", icon: BookOpen },
    { id: "gap-board", label: "Gap Board", icon: Target },
    { id: "experiment-planner", label: "实验计划", icon: FlaskConical },
  ];

  return (
    <aside className={compact ? "mock-sidebar reader-sidebar" : "mock-sidebar"}>
      <div className="sidebar-project-head">
        <span className="sf-logo small">SF</span>
        <div>
          <strong>{activeProject?.title ?? "ScholarFlow"}</strong>
          <small>{activeProject?.workflow ?? "Workspace"}</small>
        </div>
        <ChevronDown size={17} />
      </div>

      {compact ? (
        <div className="reader-nav-title">阅读导航</div>
      ) : null}

      <nav className="mock-sidebar-nav">
        {sidebarItems
          .filter((item) => (compact ? item.id !== "new-project" : true))
          .map((item) => {
            const Icon = item.icon;
            const isActive = item.id === activeView || (compact && item.id === "paper-reader");
            return (
              <button
                className={isActive ? "active" : ""}
                key={item.id}
                type="button"
                onClick={() => onSelectView(item.id)}
              >
                <Icon size={16} />
                <span>{item.label}</span>
                {compact && item.id === "direction-review" ? <ChevronDown size={15} /> : null}
              </button>
            );
          })}
      </nav>

      {compact ? (
        <div className="reader-progress-card">
          <strong>阅读进度</strong>
          <div className="progress-line">
            <span style={{ width: "100%" }} />
          </div>
          <div className="progress-meta">
            <Check size={15} />
            <span>本轮精读完成</span>
            <em>10 / 10</em>
          </div>
        </div>
      ) : showBoostCard ? (
        <div className="sidebar-boost-card">
          <div className="boost-icon">
            <Sparkles size={15} />
          </div>
          <strong>AI 驱动的科研加速器</strong>
          <p>从想法到可验证成果，ScholarFlow 帮助你更快、更深、更稳地完成科研任务。</p>
          <button type="button">
            了解更多
            <ArrowRight size={14} />
          </button>
        </div>
      ) : null}

      {showLocalAssets ? (
        <div className="local-assets-card">
          <strong>Local Assets</strong>
          <span>{projectCount || 1} project</span>
          <span>{paperCount} papers</span>
          <span>{artifactCount} persisted artifacts</span>
          <span>SQLite workspace</span>
          {visibleArtifacts.length ? (
            <div className="local-assets-list">
              {visibleArtifacts.map((artifact) => (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => onLoadArtifact?.(artifact.id)}
                >
                  <FileText size={14} />
                  <span>
                    <strong>{artifact.title}</strong>
                    <small>
                      {artifact.kind} · {formatBytes(artifact.markdown_bytes + artifact.json_bytes)}
                      {artifact.json_schema_version ? ` · ${artifact.json_schema_version}` : ""}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <small className="local-assets-empty">暂无已保存 artifact</small>
          )}
        </div>
      ) : null}
    </aside>
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
        {apiStatus === "online" ? "API Online" : apiStatus === "checking" ? "API Checking" : "API Offline"}
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
  agentRunStatus: ApiAgentRunStatusResponse | null;
  agentTask: string;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  decisionBusy: boolean;
  decisionGoal: string;
  directionBusy: boolean;
  directionInput: string;
  directionPaperRouteId: string;
  directionReview: ApiDirectionReviewResponse | null;
  directionRound: number;
  literatureCoverage: Record<string, number>;
  literatureBusy: boolean;
  literatureErrors: string[];
  literatureQuery: string;
  latestPaperCard: ApiPaperCard | null;
  memoryBusy: boolean;
  memoryQuestion: string;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  memoryTopK: number;
  ragAnswer: ApiRagAnswerResponse | null;
  ragBusy: boolean;
  projectDraft: ProjectDraft;
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onCancelAgentRun: () => void;
  onCreateDirectionReview: () => void;
  onCreateProject: () => void;
  onCreateResearchDecision: () => void;
  onDecisionGoalChange: (goal: string) => void;
  onDirectionInputChange: (direction: string) => void;
  onDirectionRoundChange: (round: number) => void;
  onExecuteAgentRun: () => void;
  onExitDirectionPaper: () => void;
  onGeneratePaperCard: () => void;
  onLiteratureQueryChange: (query: string) => void;
  onLoadArtifact: (artifactId: string) => void;
  onMemoryQuestionChange: (question: string) => void;
  onMemoryTopKChange: (topK: number) => void;
  onPaperCardInputChange: (value: string) => void;
  onPaperPdfUpload: (paperId: string, file: File) => void;
  onProjectDraftChange: (draft: ProjectDraft) => void;
  onQueryResearchMemory: () => void;
  onQueryRag: () => void;
  onSearchLiterature: () => void;
  onSelectedDirectionPaperChange: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperRows: PaperRow[];
  paperCardBusy: boolean;
  paperCardInput: string;
  projectCount: number;
  researchDecision: ApiResearchDecisionResponse | null;
  selectedPaperId: string;
  view: ViewId;
}

export function ActiveView({
  activeProject,
  agentBusy,
  agentPlan,
  agentRunStatus,
  agentTask,
  apiMessage,
  apiStatus,
  artifactCount,
  artifactSummaries,
  decisionBusy,
  decisionGoal,
  directionBusy,
  directionInput,
  directionPaperRouteId,
  directionReview,
  directionRound,
  literatureCoverage,
  literatureBusy,
  literatureErrors,
  literatureQuery,
  latestPaperCard,
  memoryBusy,
  memoryQuestion,
  memoryResult,
  memoryTopK,
  ragAnswer,
  ragBusy,
  projectDraft,
  onAgentTaskChange,
  onCancelAgentRun,
  onCreateAgentPlan,
  onCreateDirectionReview,
  onCreateProject,
  onCreateResearchDecision,
  onDecisionGoalChange,
  onDirectionInputChange,
  onDirectionRoundChange,
  onExecuteAgentRun,
  onExitDirectionPaper,
  onGeneratePaperCard,
  onLiteratureQueryChange,
  onLoadArtifact,
  onMemoryQuestionChange,
  onMemoryTopKChange,
  onPaperCardInputChange,
  onPaperPdfUpload,
  onProjectDraftChange,
  onQueryResearchMemory,
  onQueryRag,
  onSearchLiterature,
  onSelectedDirectionPaperChange,
  onSelectedPaperChange,
  onSelectView,
  paperRows,
  paperCardBusy,
  paperCardInput,
  projectCount,
  researchDecision,
  selectedPaperId,
  view,
}: ActiveViewProps) {
  const offlineNotice = apiStatus === "offline" && coreViews.has(view) ? <ApiOfflineNotice /> : null;

  switch (view) {
    case "new-project":
      return (
        <ProductNewProjectView
          activeProject={activeProject}
          apiMessage={apiMessage}
          apiStatus={apiStatus}
          artifactCount={artifactCount}
          artifactSummaries={artifactSummaries}
          draft={projectDraft}
          onCreateProject={onCreateProject}
          onDraftChange={onProjectDraftChange}
          onLoadArtifact={onLoadArtifact}
          onSelectView={onSelectView}
          paperCount={paperRows.length}
          projectCount={projectCount}
        />
      );
    case "paper-table":
      return (
        <>
          {offlineNotice}
          <ProductPaperTableView
            activeProject={activeProject}
            apiMessage={apiMessage}
            artifactCount={artifactCount}
            artifactSummaries={artifactSummaries}
            apiStatus={apiStatus}
            relevanceCoverage={literatureCoverage}
            errors={literatureErrors}
            isSearching={literatureBusy}
            onQueryChange={onLiteratureQueryChange}
            onLoadArtifact={onLoadArtifact}
            onSearch={onSearchLiterature}
            onSelectView={onSelectView}
            papers={paperRows}
            projectCount={projectCount}
            query={literatureQuery}
          />
        </>
      );
    case "paper-reader":
      return (
        <>
          {offlineNotice}
          <ProductPaperReaderView
            activeProject={activeProject}
            apiMessage={apiMessage}
            artifactCount={artifactCount}
            apiStatus={apiStatus}
            card={latestPaperCard}
            directionPaperId={directionPaperRouteId}
            directionReview={directionReview}
            artifactSummaries={artifactSummaries}
            isGenerating={paperCardBusy}
            onGenerate={onGeneratePaperCard}
            onInputChange={onPaperCardInputChange}
            onPdfUpload={onPaperPdfUpload}
            onLoadArtifact={onLoadArtifact}
            onExitDirectionPaper={onExitDirectionPaper}
            onOpenDirectionPaper={onSelectedDirectionPaperChange}
            onSelectedPaperChange={onSelectedPaperChange}
            onSelectView={onSelectView}
            papers={paperRows}
            projectCount={projectCount}
            selectedPaperId={selectedPaperId}
            supplementalInput={paperCardInput}
          />
        </>
      );
    case "direction-review":
      return (
        <>
          {offlineNotice}
          <DirectionReviewView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            direction={directionInput}
            isGenerating={directionBusy}
            onDirectionChange={onDirectionInputChange}
            onGenerate={onCreateDirectionReview}
            onLoadArtifact={onLoadArtifact}
            onOpenPaperCard={onSelectedDirectionPaperChange}
            onRoundChange={onDirectionRoundChange}
            review={directionReview}
            round={directionRound}
          />
        </>
      );
    case "paper-memory":
      return (
        <>
          {offlineNotice}
          <ResearchMemoryView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            direction={directionInput}
            isQuerying={memoryBusy}
            isRagQuerying={ragBusy}
            onQuestionChange={onMemoryQuestionChange}
            onQuery={onQueryResearchMemory}
            onQueryRag={onQueryRag}
            onSelectView={onSelectView}
            onTopKChange={onMemoryTopKChange}
            question={memoryQuestion}
            result={memoryResult}
            ragResult={ragAnswer}
            topK={memoryTopK}
          />
        </>
      );
    case "gap-board":
      return (
        <>
          {offlineNotice}
          <GapBoardView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            decision={researchDecision}
            goal={decisionGoal}
            isGenerating={decisionBusy}
            onGenerate={onCreateResearchDecision}
            onGoalChange={onDecisionGoalChange}
          />
        </>
      );
    case "experiment-planner":
      return (
        <>
          {offlineNotice}
          <ExperimentPlannerView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            decision={researchDecision}
            goal={decisionGoal}
            isGenerating={decisionBusy}
            onGenerate={onCreateResearchDecision}
            onGoalChange={onDecisionGoalChange}
          />
        </>
      );
    case "dashboard":
    default:
      return (
        <ProductHomeView
          activeProject={activeProject}
          agentBusy={agentBusy}
          agentPlan={agentPlan}
          agentRunStatus={agentRunStatus}
          agentTask={agentTask}
          apiStatus={apiStatus}
          artifactCount={artifactCount}
          onAgentTaskChange={onAgentTaskChange}
          onCancelAgentRun={onCancelAgentRun}
          onCreateAgentPlan={onCreateAgentPlan}
          onExecuteAgentRun={onExecuteAgentRun}
          onSelectView={onSelectView}
          paperCount={paperRows.length}
          projectCount={projectCount}
        />
      );
  }
}

export function ProductHomeView({
  activeProject,
  agentBusy,
  agentPlan,
  agentRunStatus,
  agentTask,
  apiStatus,
  artifactCount,
  onAgentTaskChange,
  onCancelAgentRun,
  onCreateAgentPlan,
  onExecuteAgentRun,
  onSelectView,
  paperCount,
  projectCount,
}: {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentRunStatus: ApiAgentRunStatusResponse | null;
  agentTask: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  onAgentTaskChange: (task: string) => void;
  onCancelAgentRun: () => void;
  onCreateAgentPlan: () => void;
  onExecuteAgentRun: () => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
}) {
  return (
    <div className="dashboard-workbench">
      <section className="workbench-summary-panel">
        <div className="workbench-summary-copy">
          <p className="section-kicker">Project snapshot</p>
          <h2>{activeProject?.title ?? "先创建一个科研项目"}</h2>
          <p>
            {activeProject
              ? activeProject.description || "当前项目已经连接到本地 SQLite 工作区。"
              : "ScholarFlow 只展示真实项目状态。创建项目后，Paper Table、Direction Review、Paper Memory、Gap Board 和 Experiment Plan 才会逐步进入可用状态。"}
          </p>
          <div className="workbench-context-row">
            <span>{activeProject?.field || "Evidence-first workflow"}</span>
            <span>{activeProject?.workflow || "Survey → experiment"}</span>
            <span>{activeProject?.stage || "Awaiting project"}</span>
          </div>
        </div>
        <div className="workbench-summary-actions">
          <div className={`workbench-live-state ${apiStatus}`}>
            <span aria-hidden="true" />
            <div>
              <small>Workspace state</small>
              <strong>{apiStatus === "online" ? "Ready for research" : "Backend required"}</strong>
            </div>
          </div>
          <div className="workbench-action-row">
            <button className="secondary-command" type="button" onClick={() => onSelectView("new-project")}>
              <Plus size={17} />
              新建项目
            </button>
            <button
              className="secondary-command workbench-primary-command"
              disabled={!activeProject || apiStatus !== "online"}
              type="button"
              onClick={() => onSelectView("paper-table")}
            >
              <Search size={17} />
              进入 Paper Table
            </button>
          </div>
        </div>
      </section>

      <section className="workbench-metric-grid" aria-label="current project metrics">
        <Metric label="API" value={apiStatus} detail={apiStatus === "online" ? "后端可用" : "等待后端连接"} />
        <Metric label="Projects" value={String(projectCount)} detail="本地 SQLite 项目数" />
        <Metric label="Papers" value={String(paperCount)} detail="当前项目真实论文" />
        <Metric label="Artifacts" value={String(artifactCount)} detail="后端持久化输出" />
      </section>

      <WorkflowGuide
        apiStatus={apiStatus}
        artifactCount={artifactCount}
        hasProject={Boolean(activeProject)}
        onSelectView={onSelectView}
        paperCount={paperCount}
      />

      <AgentRunPanel
        activeProject={activeProject}
        agentBusy={agentBusy}
        agentPlan={agentPlan}
        agentRunStatus={agentRunStatus}
        agentTask={agentTask}
        apiStatus={apiStatus}
        onAgentTaskChange={onAgentTaskChange}
        onCancelAgentRun={onCancelAgentRun}
        onCreateAgentPlan={onCreateAgentPlan}
        onExecuteAgentRun={onExecuteAgentRun}
      />
    </div>
  );
}

export function ProductNewProjectView({
  activeProject,
  apiMessage,
  apiStatus,
  artifactCount,
  artifactSummaries,
  draft,
  onCreateProject,
  onDraftChange,
  onLoadArtifact,
  onSelectView,
  paperCount,
  projectCount,
}: {
  activeProject: ApiProject | null;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  draft: ProjectDraft;
  onCreateProject: () => void;
  onDraftChange: (draft: ProjectDraft) => void;
  onLoadArtifact: (artifactId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
}) {
  const [draftStatus, setDraftStatus] = useState("");
  const suggestions = [
    {
      title: "多模态大模型在视觉问答中的证据真实性评估",
      detail: "关注 hallucination、citation faithfulness 与 benchmark。",
      icon: Network,
    },
    {
      title: "医学影像分割中的 prompt learning",
      detail: "探索提示学习在分割任务中的跨域泛化能力。",
      icon: BookOpen,
    },
    {
      title: "RAG 系统中 citation faithfulness 的自动评估方法",
      detail: "构建无需人工标注的可信度评估框架。",
      icon: Search,
    },
    {
      title: "扩散模型用于盲图像修复时的可控性问题",
      detail: "研究条件控制与结构保持的平衡策略。",
      icon: FileText,
    },
  ];
  const createSteps = [
    ["创建 SQLite Project", "建立本地项目、语言、研究领域和 workflow。"],
    ["初始化 Agent Task", "生成从文献检索到可验证 gap 的最小任务计划。"],
    ["进入 Paper Table", "用当前关键词直接发起 arXiv / OpenAlex 检索。"],
    ["保存 Artifact", "后续总结、Paper Card、Gap Board 都可回溯。"],
  ];

  function updateDraft(field: keyof ProjectDraft, value: string) {
    onDraftChange({
      ...draft,
      [field]: value,
    });
  }

  function applySuggestion(title: string) {
    onDraftChange({
      ...draft,
      title,
      keyword: title,
      description: `围绕「${title}」检索近三年相关论文，识别证据约束、benchmark 偏差与一周可验证实验。`,
    });
  }

  function saveDraftToLocalStorage() {
    if (!draft.title.trim() && !draft.keyword.trim() && !draft.description.trim()) {
      setDraftStatus("请先填写标题、关键词或目标，再保存草稿。");
      return;
    }
    try {
      window.localStorage.setItem(PROJECT_DRAFT_STORAGE_KEY, JSON.stringify({ ...draft, saved_at: new Date().toISOString() }));
      setDraftStatus("草稿已保存到本机浏览器 localStorage，不会写入后端或 GitHub。");
    } catch {
      setDraftStatus("草稿保存失败：浏览器阻止了 localStorage 写入。");
    }
  }

  return (
    <div className="project-canvas">
      <ProjectSidebar
        activeProject={activeProject}
        activeView="new-project"
        artifacts={artifactSummaries}
        artifactCount={artifactCount}
        onLoadArtifact={onLoadArtifact}
        onSelectView={onSelectView}
        paperCount={paperCount}
        projectCount={projectCount}
      />

      <section className="new-project-panel">
        <div className="panel-title-row">
          <Sparkles size={34} />
          <div>
            <h1>新建科研项目</h1>
            <p>输入项目信息，系统将为你初始化 “survey-to-experiment” 工作流。</p>
          </div>
        </div>

        <div className="field-stack">
          <label>
            <span>项目标题 <sup>*</sup></span>
            <div className="text-input-row">
              <input
                maxLength={100}
                placeholder="例如：多模态大模型在视觉问答证据真实性研究"
                value={draft.title}
                onChange={(event) => updateDraft("title", event.target.value)}
              />
              <span>{draft.title.length}/100</span>
            </div>
          </label>
          <label>
            <span>研究方向 / Keyword <sup>*</sup></span>
            <div className="text-input-row">
              <input
                maxLength={200}
                placeholder="输入关键词，多个关键词请用英文逗号分隔"
                value={draft.keyword}
                onChange={(event) => updateDraft("keyword", event.target.value)}
              />
              <span>{draft.keyword.length}/200</span>
            </div>
          </label>
          <label>
            <span>研究领域 <sup>*</sup></span>
            <div className="select-like readonly-field" aria-readonly="true">
              <span>{draft.field || "Artificial Intelligence / Multimodal Learning"}</span>
              <small>只读，可在标题和关键词中细化方向</small>
            </div>
          </label>
          <label>
            <span>工作流模板 <sup>*</sup></span>
            <div className="select-like readonly-field" aria-readonly="true">
              <span>Survey → Deep Reading → Memory → Gap → Experiment</span>
              <small>固定模板</small>
            </div>
          </label>
        </div>

        <div className="form-action-row">
          <button className="gradient-button form-primary" disabled={apiStatus === "checking"} type="button" onClick={onCreateProject}>
            创建项目
          </button>
          <button className="outline-button form-secondary" type="button" onClick={saveDraftToLocalStorage}>
            <Save size={17} />
            保存草稿
          </button>
        </div>
        {draftStatus ? <p className="draft-status-note">{draftStatus}</p> : null}

        <div className={`project-status-note ${apiStatus}`}>
          <Lightbulb size={18} />
          <span>{apiMessage}</span>
        </div>
      </section>

      <aside className="new-project-aside">
        <section className="suggestion-panel">
          <div className="aside-heading">
            <h2>推荐输入示例</h2>
            <span>Prompt Suggestions</span>
          </div>
          <div className="suggestion-list">
            {suggestions.map((item) => {
              const Icon = item.icon;
              return (
                <button className="suggestion-card" key={item.title} type="button" onClick={() => applySuggestion(item.title)}>
                  <span>
                    <Icon size={21} />
                  </span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="after-create-panel">
          <h2>创建后自动生成</h2>
          <ol>
            {createSteps.map(([title, detail], index) => (
              <li key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </aside>

      <ConferenceLogoBelt />
    </div>
  );
}

export function ProductPaperTableView({
  activeProject,
  apiMessage,
  artifactCount,
  artifactSummaries,
  apiStatus,
  errors,
  isSearching,
  relevanceCoverage: structuredRelevanceCoverage,
  onLoadArtifact,
  onQueryChange,
  onSearch,
  onSelectView,
  papers,
  projectCount,
  query,
}: {
  activeProject: ApiProject | null;
  apiMessage: string;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  apiStatus: ApiStatus;
  errors: string[];
  isSearching: boolean;
  relevanceCoverage: Record<string, number>;
  onLoadArtifact: (artifactId: string) => void;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  onSelectView: (view: ViewId) => void;
  papers: PaperRow[];
  projectCount: number;
  query: string;
}) {
  const [highOnly, setHighOnly] = useState(false);
  const [expandedReasons, setExpandedReasons] = useState<Set<string>>(() => new Set());
  const displayPapers = highOnly ? papers.filter((paper) => paper.priority === "High") : papers;
  const relevanceCoverage = derivePaperTableCoverage(papers, structuredRelevanceCoverage);
  const strongCount = relevanceCoverage.strong_match_count;
  const mediumCount = relevanceCoverage.medium_match_count;
  const weakCount = relevanceCoverage.weak_match_count;
  const offTopicCount = relevanceCoverage.off_topic_count;
  const retrievalWarnings = errors.filter(isRetrievalWarning);
  const backendErrors = errors.filter((error) => !isRetrievalWarning(error));
  const isPartialPaperTable = offTopicCount > 0 || weakCount > 0 || retrievalWarnings.length > 0;
  const isDemo = isDemoProject(activeProject);
  const tableRows = displayPapers.map((paper) => ({
    id: paper.id,
    title: paper.title,
    authors: paper.authors,
    year: paper.year,
    type: paper.type,
    source: paper.source,
    priority: paper.priority,
    relation: paper.relation,
    url: paper.url,
    relevanceQuality: paper.relevanceQuality,
    matchedTerms: paper.matchedTerms,
  }));
  const csvDisabledReason = tableRows.length === 0 ? "没有可导出的真实论文。请先运行 Literature Search。" : "";
  const searchDisabledReason = isDemo
    ? "Demo 项目仅用于界面预览。请新建真实项目后再检索。"
    : query.trim().length === 0
      ? "请输入检索关键词。"
      : apiStatus !== "online"
        ? "API 未连接，无法检索。"
        : "";
  const directionDisabledReason = isDemo
    ? "Demo 项目不能生成真实 Direction Review。"
    : apiStatus !== "online"
      ? "API 未连接，无法生成 Direction Review。"
      : "";

  function exportCsv() {
    if (!tableRows.length) {
      return;
    }
    const headers = ["Title", "Authors", "Year", "Type", "Source", "Priority", "Relevance Reason", "URL"];
    const csvRows = [
      headers,
      ...tableRows.map((paper) => [
        paper.title,
        paper.authors,
        paper.year,
        paper.type,
        paper.source,
        paper.priority,
        paper.relation,
        paper.url,
      ]),
    ];
    const csv = csvRows.map((row) => row.map(escapeCsvCell).join(",")).join("\n");
    const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const projectSlug = slugify(activeProject?.title ?? "scholarflow");
    anchor.href = url;
    anchor.download = `${projectSlug}-papers.csv`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  }

  return (
    <div className="table-canvas">
      <ProjectSidebar
        activeProject={activeProject}
        activeView="paper-table"
        artifacts={artifactSummaries}
        artifactCount={artifactCount}
        onLoadArtifact={onLoadArtifact}
        onSelectView={onSelectView}
        paperCount={papers.length}
        projectCount={projectCount}
      />

      <section className="paper-table-panel">
        <div className="table-header-row">
          <div>
            <h1>论文表格 · Literature Search</h1>
            <p>优先检索近三年高相关论文，并标记 Method / Benchmark / Survey / Analysis。</p>
          </div>
          <div className="table-header-actions">
            <button className="outline-button" disabled={!tableRows.length} title={csvDisabledReason} type="button" onClick={exportCsv}>
              <Download size={17} />
              导出 CSV
            </button>
            <button
              className="gradient-button"
              disabled={apiStatus !== "online" || isDemo}
              title={directionDisabledReason}
              type="button"
              onClick={() => onSelectView("direction-review")}
            >
              <Sparkles size={17} />
              进入 Direction Review
            </button>
          </div>
        </div>

        <div className="table-metrics">
          <MetricCard
            icon={FileText}
            label="已保存论文"
            value={String(papers.length)}
            hint="当前项目中已保存、去重后的论文总数。"
          />
          <MetricCard
            icon={Search}
            label="本轮候选"
            value={String(relevanceCoverage.candidate_count)}
            hint="本轮从检索源收集并去重后，进入相关性筛选的候选论文数。"
          />
          <MetricCard
            icon={ShieldCheck}
            label="通过门槛"
            value={String(relevanceCoverage.eligible_count)}
            hint="被判定为强相关或中相关、具备进入结果集资格的论文数。"
          />
          <MetricCard
            icon={FileText}
            label="本轮展示"
            value={String(relevanceCoverage.returned_count)}
            hint="受 max_results 上限约束后，本轮实际返回并写入项目的论文数。"
          />
          <MetricCard
            icon={AlertTriangle}
            label="因上限未展示"
            value={String(relevanceCoverage.truncated_count)}
            hint="已通过相关性门槛，但因本轮数量上限而未写入项目的论文数。"
            amber={relevanceCoverage.truncated_count > 0}
          />
          <MetricCard icon={Target} label="强 / 中相关" value={`${strongCount} / ${mediumCount}`} hint="所有通过门槛论文的相关性分级；两者之和等于“通过门槛”。" />
          <MetricCard icon={AlertTriangle} label="弱相关已过滤" value={String(weakCount)} hint="因只命中泛词或证据不足而未进入默认结果的候选数。" amber={weakCount > 0} />
          <MetricCard icon={ShieldCheck} label="离题已过滤" value={String(offTopicCount)} hint="因领域或核心主题不匹配而被排除的候选数。" amber={offTopicCount > 0} />
        </div>

        <div className="paper-search-strip">
          <label className="paper-query-box">
            <Search size={20} />
            <input
              aria-label="论文检索关键词"
              value={query}
              placeholder={activeProject?.keyword || "multimodal large language model visual question answering evidence faithfulness"}
              onChange={(event) => onQueryChange(event.target.value)}
            />
            {query ? (
              <button type="button" onClick={() => onQueryChange("")} aria-label="清空检索关键词">
                <X size={19} />
              </button>
            ) : null}
          </label>
          <button
            className="outline-button search-again"
            disabled={apiStatus !== "online" || isSearching || query.trim().length === 0 || isDemo}
            title={searchDisabledReason}
            type="button"
            onClick={onSearch}
          >
            <Sparkles size={17} />
            {isSearching ? "检索中" : "重新检索"}
          </button>
          <button className={highOnly ? "outline-button active-filter" : "outline-button"} type="button" onClick={() => setHighOnly((value) => !value)}>
            <Filter size={17} />
            筛选 High
          </button>
        </div>

        {isSearching ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}

        <ResearchWarningPanel
          className="table-warning-summary"
          title="检索状态"
          warnings={errors}
          fallback={
            isDemo
              ? "当前为 Demo 预览；示例论文不会出现在真实项目的检索结果中。"
              : isPartialPaperTable
                ? `本轮结果为部分完成：已过滤 ${weakCount} 篇弱相关与 ${offTopicCount} 篇离题候选。`
                : "本轮检索没有报告外部依赖或相关性过滤警告。"
          }
        />

        <div className="product-table-wrap">
          <table className="product-paper-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Year</th>
                <th>Type</th>
                <th>Source</th>
                <th>Priority</th>
                <th>Relevance Reason</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((paper, index) => (
                <tr key={paper.id || `${paper.title}-${index}`}>
                  <td className="paper-title-cell" title={paper.title}>
                    {paper.url ? (
                      <a className="paper-title-link" href={paper.url} rel="noreferrer" target="_blank">
                        <strong>{paper.title}</strong>
                      </a>
                    ) : (
                      <strong>{paper.title}</strong>
                    )}
                    <small>{paper.authors}</small>
                  </td>
                  <td>{paper.year}</td>
                  <td>
                    <span className={`paper-type type-${paper.type.toLowerCase()}`}>{paper.type || "Method"}</span>
                  </td>
                  <td className="paper-source-cell">
                    <span>{paper.source}</span>
                    {paper.url ? (
                      <a
                        aria-label={`打开论文来源：${paper.title}`}
                        href={paper.url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        原文
                        <ArrowRight size={12} aria-hidden="true" />
                      </a>
                    ) : (
                      <small>链接缺失</small>
                    )}
                  </td>
                  <td>
                    <span className={`priority ${paper.priority.toLowerCase()}`}>{paper.priority}</span>
                    <small>{paper.relevanceQuality ?? "medium"}</small>
                  </td>
                  <td className="paper-relation-cell">
                    <p className={expandedReasons.has(paper.id) ? "expanded" : ""} id={`paper-relevance-${paper.id}`}>
                      {paper.relation}
                    </p>
                    {paper.matchedTerms?.length ? <small>匹配词：{paper.matchedTerms.slice(0, 5).join(", ")}</small> : null}
                    {paper.relation.trim().length > 80 ? (
                      <button
                        aria-controls={`paper-relevance-${paper.id}`}
                        aria-expanded={expandedReasons.has(paper.id)}
                        className="paper-relation-toggle"
                        type="button"
                        onClick={() => {
                          setExpandedReasons((current) => {
                            const next = new Set(current);
                            if (next.has(paper.id)) {
                              next.delete(paper.id);
                            } else {
                              next.add(paper.id);
                            }
                            return next;
                          });
                        }}
                      >
                        {expandedReasons.has(paper.id) ? "收起理由" : "展开理由"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {tableRows.length === 0 ? (
            <div className="product-table-empty">
              <h2>
                {apiStatus === "offline"
                  ? "API 未连接"
                  : retrievalWarnings.length
                    ? "外部检索源 degraded retrieval"
                    : "本次没有可展示论文"}
              </h2>
              <p>
                {apiStatus === "offline"
                  ? "请先启动 ScholarFlow 后端服务。当前不是“没有论文”，而是前端无法读取真实 paper table。"
                  : retrievalWarnings.length
                    ? "arXiv/OpenAlex 限流、超时或降级时，系统会显示 partial/warning，不会用 demo 论文冒充真实结果。可以稍后重试或换更具体关键词。"
                    : highOnly
                    ? "当前没有 High Priority 论文。可以关闭筛选，或重新检索更具体的方向。"
                    : "请先运行 Literature Search，系统不会用内置示例论文填充表格。"}
              </p>
            </div>
          ) : null}
        </div>

        <div className="table-warning" aria-live="polite">
          <Lightbulb size={17} />
          <span>
            {isDemo
              ? "Demo 项目只用于预览；不会把 seed/demo 论文显示为真实检索结果。"
              : isPartialPaperTable
                ? "当前 Paper Table 为部分完成，请结合上方检索状态与过滤数判断覆盖范围。"
                : "表格仅显示当前项目已保存的真实论文记录。"}
          </span>
        </div>
      </section>

      <ConferenceLogoBelt withTitle={false} />
    </div>
  );
}

function derivePaperTableCoverage(papers: PaperRow[], coverage: Record<string, number>): Record<string, number> {
  const strongFromRows = papers.filter((paper) => paper.relevanceQuality === "strong").length;
  const mediumFromRows = papers.filter((paper) => paper.relevanceQuality === "medium" || !paper.relevanceQuality).length;
  const weakCount = coverage.weak_match_count ?? 0;
  const offTopicCount = coverage.off_topic_count ?? 0;
  const strongCount = coverage.strong_match_count ?? strongFromRows;
  const mediumCount = coverage.medium_match_count ?? mediumFromRows;
  const eligibleCount = coverage.eligible_count ?? strongCount + mediumCount;
  const returnedCount = coverage.returned_count ?? papers.length;
  return {
    candidate_count: coverage.candidate_count ?? papers.length,
    eligible_count: eligibleCount,
    returned_count: returnedCount,
    truncated_count: coverage.truncated_count ?? Math.max(0, eligibleCount - returnedCount),
    strong_match_count: strongCount,
    medium_match_count: mediumCount,
    weak_match_count: weakCount,
    off_topic_count: offTopicCount,
    filtered_count: coverage.filtered_count ?? weakCount + offTopicCount,
  };
}

function formatEvidenceLevel(level: string): string {
  if (level === "full_text") {
    return "全文已验证";
  }
  if (level === "abstract_only") {
    return "摘要级证据";
  }
  if (level === "metadata_only") {
    return "元数据级证据";
  }
  return level || "未知证据等级";
}

function formatSignalEvidenceLocation(evidence?: ApiSignalEvidence): string {
  if (!evidence) {
    return "未找到可定位的原文证据";
  }
  const location = [
    evidence.source || "unknown source",
    evidence.section || "unknown section",
    typeof evidence.page === "number" ? `p.${evidence.page}` : "",
  ].filter(Boolean);
  return `${location.join(" · ")} · 抽取置信度 ${evidence.confidence || "low"}`;
}

function MetricCard({
  amber = false,
  hint,
  icon: Icon,
  label,
  value,
}: {
  amber?: boolean;
  hint?: string;
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <article aria-label={`${label}：${value}`} className={amber ? "metric-card amber" : "metric-card"} title={hint}>
      <span>
        <Icon size={25} />
      </span>
      <div>
        <strong>{value}</strong>
        <p>{label}</p>
      </div>
    </article>
  );
}

export function ProductPaperReaderView({
  activeProject,
  apiMessage,
  artifactCount,
  artifactSummaries,
  apiStatus,
  card,
  directionPaperId,
  directionReview,
  isGenerating,
  onGenerate,
  onInputChange,
  onPdfUpload,
  onLoadArtifact,
  onExitDirectionPaper,
  onOpenDirectionPaper,
  onSelectedPaperChange,
  onSelectView,
  papers,
  projectCount,
  selectedPaperId,
  supplementalInput,
}: {
  activeProject: ApiProject | null;
  apiMessage: string;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  apiStatus: ApiStatus;
  card: ApiPaperCard | null;
  directionPaperId: string;
  directionReview: ApiDirectionReviewResponse | null;
  isGenerating: boolean;
  onGenerate: () => void;
  onInputChange: (value: string) => void;
  onPdfUpload: (paperId: string, file: File) => void;
  onLoadArtifact: (artifactId: string) => void;
  onExitDirectionPaper: () => void;
  onOpenDirectionPaper: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  papers: PaperRow[];
  projectCount: number;
  selectedPaperId: string;
  supplementalInput: string;
}) {
  const [activeQuestion, setActiveQuestion] = useState(1);

  useEffect(() => {
    setActiveQuestion(1);
  }, [card, selectedPaperId]);

  const directionReadings = directionReview?.papers ?? [];
  const directionReading = directionReadings.find((reading) => reading.paper.id === directionPaperId) ?? null;
  const effectiveDirectionReading = mergeDirectionReadingWithPaperCard(directionReading, card);

  if (directionPaperId) {
    return (
      <DirectionPaperPage
        canUpload={apiStatus === "online"}
        hasHydratedReview={Boolean(directionReview)}
        isGenerating={isGenerating}
        onBack={onExitDirectionPaper}
        onOpenEvidenceInput={() => onSelectView("paper-reader")}
        onOpenPaper={onOpenDirectionPaper}
        onPdfUpload={onPdfUpload}
        reading={effectiveDirectionReading}
        readings={directionReadings}
        requestedPaperId={directionPaperId}
      />
    );
  }

  const selectedPaper = papers.find((paper) => paper.id === selectedPaperId) ?? papers[0];
  const cardMatch = resolvePaperCardForPaper(card, directionReview, selectedPaper);
  const displayCard = cardMatch?.card ?? null;
  const cardSections = displayCard?.sections ?? [];
  const signals = displayCard?.signals;
  const evidenceLevel = displayCard?.evidence_level ?? "metadata_only";
  const readerTitle = formatReaderTitle(evidenceLevel, Boolean(displayCard));
  const evidenceBoundary = buildEvidenceBoundary(evidenceLevel);
  const missingEvidence = buildMissingEvidenceChecklist(displayCard);
  const activeQuestionIndex = cardSections.length
    ? Math.min(Math.max(activeQuestion - 1, 0), cardSections.length - 1)
    : -1;
  const activeSection = activeQuestionIndex >= 0 ? cardSections[activeQuestionIndex] : null;
  const activeSectionContent = activeSection ? parsePaperCardSectionContent(activeSection.content) : null;
  const activeSectionParagraphs = activeSectionContent
    ? splitPaperCardSectionParagraphs(activeSectionContent.primary)
    : [];
  const openSupplementalEvidenceInput = () => {
    if (typeof document === "undefined") {
      return;
    }
    const panel = document.querySelector<HTMLDetailsElement>(".reader-supplemental-input");
    if (!panel) {
      return;
    }
    panel.open = true;
    window.requestAnimationFrame(() => {
      panel.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    });
  };
  const expectedSections = [
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
  const conciseSignal = (label: string, value: string | undefined) => {
    const normalized = value?.trim() ?? "";
    if (!normalized || normalized.startsWith("当前证据不足")) {
      return "";
    }
    const preview = normalized.length > 72 ? `${normalized.slice(0, 69)}…` : normalized;
    return `${label} · ${preview}`;
  };
  const signalTags = [
    signals?.contribution_type ? `类型 · ${signals.contribution_type}` : "",
    selectedPaper?.year ? `年份 · ${selectedPaper.year}` : "",
    selectedPaper?.venue ? `来源 · ${selectedPaper.venue}` : "",
    conciseSignal("Dataset", signals?.dataset),
    conciseSignal("Metric", signals?.metric),
    conciseSignal("Baseline", signals?.baseline),
  ].filter(Boolean);
  const selectedSummary = selectedPaper?.abstract || selectedPaper?.relation || "";
  const selectedSummaryPreview = selectedSummary.length > 560 ? `${selectedSummary.slice(0, 557)}…` : selectedSummary;

  return (
    <div className="reader-canvas">
      <ProjectSidebar
        activeProject={activeProject}
        activeView="paper-reader"
        artifacts={artifactSummaries}
        artifactCount={artifactCount}
        compact
        onLoadArtifact={onLoadArtifact}
        onSelectView={onSelectView}
        paperCount={papers.length}
        projectCount={projectCount}
      />

      <section className="reader-main-panel">
        <div className="reader-content">
          <button className="back-link" type="button" onClick={() => onSelectView("paper-table")}>
            <ChevronLeft size={16} />
            返回列表
          </button>
          <div className="reader-title-row">
            <div>
              <h1>{readerTitle}</h1>
              <p>
                {selectedPaper?.title ?? "尚未选择论文"}
                {selectedPaper?.venue || selectedPaper?.year ? <span>{selectedPaper.venue || selectedPaper.year}</span> : null}
              </p>
              <small>只展示当前项目真实论文和已生成的 Paper Card；摘要级/元数据级卡片不会被标成完整正文阅读。</small>
            </div>
            <div className="reader-actions">
              <button
                className="gradient-button"
                disabled={apiStatus !== "online" || isGenerating}
                type="button"
                onClick={onGenerate}
              >
                <Rocket size={17} />
                {isGenerating ? "生成中" : "生成 12 条分析"}
              </button>
            </div>
          </div>

          {isGenerating ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}

          <div className="reader-tags">
            {signalTags.length ? (
              signalTags.map((tag) => <span key={tag}>{tag}</span>)
            ) : selectedPaper ? (
              <>
                <span>{selectedPaper.type || "type unknown"}</span>
                <span>{selectedPaper.source || "source unknown"}</span>
                <span>{selectedPaper.year || "year unknown"}</span>
              </>
            ) : (
              <span>等待论文或手动输入</span>
            )}
          </div>

          <article className="summary-card">
            <Sparkles size={23} />
            <div>
              <strong>{displayCard ? `${formatEvidenceLevel(evidenceLevel)}卡片` : "待生成 Paper Card"}</strong>
              <p>{selectedSummaryPreview || "请先在 Paper Table 选择论文，或粘贴摘要/正文片段后生成 Paper Card。"}</p>
              {selectedSummary.length > selectedSummaryPreview.length ? (
                <details className="summary-card-details">
                  <summary>查看完整摘要</summary>
                  <p>{selectedSummary}</p>
                </details>
              ) : null}
              {displayCard?.evidence_level ? (
                <small>
                  Evidence level: {formatEvidenceLevel(displayCard.evidence_level)} · 来源：
                  {formatPaperCardSource(cardMatch?.source ?? displayCard.card_source ?? "manual_unbound")} · 匹配：
                  {cardMatch?.matchedBy ?? "manual_unbound"}
                </small>
              ) : null}
            </div>
          </article>

          <section className="reader-evidence-summary" aria-label="paper card evidence summary">
            <div className={`reader-evidence-level ${evidenceLevel}`}>
              <ShieldCheck size={16} />
              <strong>{formatEvidenceLevel(evidenceLevel)}</strong>
              <span>来源：{formatPaperCardSource(cardMatch?.source ?? displayCard?.card_source ?? "manual_unbound")}</span>
              {displayCard?.full_text?.status === "extracted" ? (
                <span>
                  {displayCard.full_text.page_count} 页 / {displayCard.full_text.character_count.toLocaleString("zh-CN")} 字符
                </span>
              ) : null}
              {displayCard?.updated_at || displayCard?.created_at ? (
                <span>更新：{formatArtifactDate(displayCard.updated_at || displayCard.created_at)}</span>
              ) : null}
            </div>
            {evidenceBoundary ? <LimitedEvidenceSummary boundary={evidenceBoundary} /> : null}
            <FullTextProvenanceStatus
              onOpenEvidenceInput={openSupplementalEvidenceInput}
              provenance={displayCard?.full_text}
              updatedAt={displayCard?.updated_at || displayCard?.created_at}
            />

            {displayCard && missingEvidence.length ? (
              <details className="reader-evidence-scope" aria-label="paper card evidence scope">
                <summary>
                  <span>
                    <ShieldCheck size={17} />
                    <strong>待补证据与核验清单</strong>
                  </span>
                  <span>{formatEvidenceLevel(evidenceLevel)}</span>
                </summary>
                <div className="reader-evidence-scope-content">
                  {missingEvidence.length ? (
                    <div>
                      <strong>待补证据</strong>
                      <ul>
                        {missingEvidence.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </details>
            ) : null}
          </section>

          <details className="reader-supplemental-input">
            <summary>
              <span>
                <FileText size={17} />
                <strong>补充正文证据</strong>
              </span>
              <span>{supplementalInput.trim() ? `${supplementalInput.trim().length} 字` : "可选"}</span>
            </summary>
            <div className="reader-supplemental-input-content">
              <PdfUploadControl
                busy={isGenerating}
                disabled={apiStatus !== "online" || !selectedPaper}
                onUpload={onPdfUpload}
                paperId={selectedPaper?.id ?? ""}
              />
              <div className="reader-input-divider"><span>或粘贴关键正文片段</span></div>
              <label htmlFor="paper-card-supplemental-input">
                粘贴 abstract、method、experiment、表格说明或正文片段
              </label>
              <textarea
                id="paper-card-supplemental-input"
                placeholder="建议优先粘贴方法、实验设置、baseline、ablation 与 failure case；随后点击上方按钮重新生成。"
                value={supplementalInput}
                onChange={(event) => onInputChange(event.target.value)}
              />
              <p>补充内容会作为本次 Paper Card 的证据输入，不会覆盖项目中的原始论文记录。</p>
            </div>
          </details>

          <section className="question-board" aria-label="paper card reading">
            <div className="question-board-head">
              <div>
                <p className="section-kicker">Deep Paper Card</p>
                <h2>12 段科研精读</h2>
              </div>
              <span>{cardSections.length}/12 已生成</span>
            </div>
            {cardSections.length ? (
              <div className="paper-reader-workspace">
                <nav className="paper-reader-toc" aria-label="12 段精读目录">
                  <ol>
                    {cardSections.map((section, index) => {
                      const isActive = activeQuestionIndex === index;
                      return (
                        <li key={`${section.id}-${index}`}>
                          <button
                            aria-controls={isActive ? `paper-reader-section-${index + 1}` : undefined}
                            aria-current={isActive ? true : undefined}
                            className="paper-reader-toc-item"
                            type="button"
                            onClick={() => setActiveQuestion(index + 1)}
                          >
                            <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                            <strong>{formatPaperCardSectionTitle(section.title)}</strong>
                            <Check size={14} aria-hidden="true" />
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                </nav>

                {activeSection && activeSectionContent ? (
                  <article
                    className="paper-reader-section"
                    id={`paper-reader-section-${activeQuestionIndex + 1}`}
                    tabIndex={-1}
                  >
                    <header>
                      <span>
                        Section {String(activeQuestionIndex + 1).padStart(2, "0")} / {cardSections.length}
                      </span>
                      <h3 data-testid="paper-reader-active-section-heading">{formatPaperCardSectionTitle(activeSection.title)}</h3>
                    </header>

                    <div className="paper-reader-section-body">
                      {activeSectionParagraphs.map((paragraph, index) => (
                        <p key={`${activeSection.id}-paragraph-${index}`}>{paragraph}</p>
                      ))}
                    </div>

                    {activeSectionContent.outline ||
                    activeSectionContent.evidenceGap ||
                    activeSectionContent.verification ? (
                      <details className="paper-reader-section-notes">
                        <summary>本段核验备注</summary>
                        <dl>
                          {activeSectionContent.outline ? (
                            <div>
                              <dt>阅读定位</dt>
                              <dd>{activeSectionContent.outline}</dd>
                            </div>
                          ) : null}
                          {activeSectionContent.evidenceGap ? (
                            <div>
                              <dt>证据缺口</dt>
                              <dd>{activeSectionContent.evidenceGap}</dd>
                            </div>
                          ) : null}
                          {activeSectionContent.verification ? (
                            <div>
                              <dt>核验问题</dt>
                              <dd>{activeSectionContent.verification}</dd>
                            </div>
                          ) : null}
                        </dl>
                      </details>
                    ) : null}

                    <footer className="paper-reader-section-nav" aria-label="精读章节切换">
                      <button
                        disabled={activeQuestionIndex <= 0}
                        type="button"
                        onClick={() => setActiveQuestion(activeQuestionIndex)}
                      >
                        <ChevronLeft size={15} />
                        上一节
                      </button>
                      <span aria-live="polite">
                        {activeQuestionIndex + 1} / {cardSections.length}
                      </span>
                      <button
                        disabled={activeQuestionIndex >= cardSections.length - 1}
                        type="button"
                        onClick={() => setActiveQuestion(activeQuestionIndex + 2)}
                      >
                        下一节
                        <ArrowRight size={15} />
                      </button>
                    </footer>
                  </article>
                ) : null}
              </div>
            ) : (
              <div className="reader-empty-state">
                <BookOpen size={22} />
                <div>
                  <h2>尚未生成 12 条精读</h2>
                  <p>点击“生成 12 条分析”后，系统会基于选中论文或补充文本生成真实 Paper Card。</p>
                </div>
              </div>
            )}
            {!cardSections.length ? (
              <div className="protocol-list compact" aria-label="paper card protocol">
                {expectedSections.map((section, index) => (
                  <div className="protocol-row" key={section}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p>{section}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </div>

        <aside className="reader-aside">
          <section className="key-info-card">
            <h2>关键信息</h2>
            <div className="key-info-grid">
              <div>
                <strong>{selectedPaper?.year || "N/A"}</strong>
                <span>Year</span>
              </div>
              <div>
                <strong>{selectedPaper?.type || "N/A"}</strong>
                <span>Type</span>
              </div>
              <div>
                <strong>{selectedPaper?.priority || "N/A"}</strong>
                <span>Priority</span>
              </div>
              <div>
                <strong>{displayCard?.evidence_level ? formatEvidenceLevel(displayCard.evidence_level) : "N/A"}</strong>
                <span>Evidence</span>
              </div>
            </div>
          </section>

          <section className="evidence-chain-card">
            <div className="aside-heading compact">
              <h2>生成状态</h2>
              <span>{displayCard ? "已生成" : "待生成"}</span>
            </div>
            <div className="chain-step">
              <span>1</span>
              <div>
                <strong>最脆弱假设</strong>
                <p>{displayCard?.weakest_assumption || "尚未生成，系统不会编造论文局限。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>2</span>
              <div>
                <strong>一周最小复现</strong>
                <p>{displayCard?.minimal_reproduction || "需要生成 Paper Card 后才能给出具体实验切口。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>3</span>
              <div>
                <strong>证据来源</strong>
                <p>
                  {displayCard?.evidence_level
                    ? `${formatPaperCardSource(cardMatch?.source ?? displayCard.card_source ?? "manual_unbound")} · ${formatEvidenceLevel(displayCard.evidence_level)}`
                    : selectedPaper
                      ? "来自当前项目 Paper Table。"
                      : supplementalInput.trim()
                        ? "来自用户粘贴内容。"
                        : "暂无输入。"}
                </p>
              </div>
            </div>
          </section>

          <section className="paper-signals-card">
            <div className="aside-heading compact">
              <h2>PaperSignals（自动抽取）</h2>
              <span>{signals ? "available" : "empty"}</span>
            </div>
            {signals ? (
              <div className="signal-chip-grid">
                {[
                  ["Task", signals.task],
                  ["Method", signals.method],
                  ["Dataset", signals.dataset],
                  ["Metric", signals.metric],
                  ["Baseline", signals.baseline],
                  ["Claim", signals.claim],
                  ["Limitation", signals.limitation],
                ].map(([label, value], index) => (
                  <span className={`signal-chip tone-${index}`} key={label}>
                    <strong>{label}</strong>
                    {value || "暂无"}
                  </span>
                ))}
              </div>
            ) : (
              <div className="reader-empty-state compact">
                <FileText size={19} />
                <div>
                  <h3>暂无 PaperSignals</h3>
                  <p>生成 Paper Card 后才会显示 task、method、dataset、metric 和 claim。</p>
                </div>
              </div>
            )}
          </section>
        </aside>
      </section>
    </div>
  );
}

function DirectionPaperPage({
  canUpload,
  hasHydratedReview,
  isGenerating,
  onBack,
  onOpenEvidenceInput,
  onOpenPaper,
  onPdfUpload,
  reading,
  readings,
  requestedPaperId,
}: {
  canUpload: boolean;
  hasHydratedReview: boolean;
  isGenerating: boolean;
  onBack: () => void;
  onOpenEvidenceInput: () => void;
  onOpenPaper: (paperId: string) => void;
  onPdfUpload: (paperId: string, file: File) => void;
  reading: ApiDirectionPaperReading | null;
  readings: ApiDirectionPaperReading[];
  requestedPaperId: string;
}) {
  const readingIndex = reading ? readings.findIndex((item) => item.paper.id === reading.paper.id) : -1;
  const previousReading = readingIndex > 0 ? readings[readingIndex - 1] : null;
  const nextReading = readingIndex >= 0 && readingIndex < readings.length - 1 ? readings[readingIndex + 1] : null;

  return (
    <div className="direction-paper-page">
      <header className="direction-paper-toolbar">
        <button className="back-link" type="button" onClick={onBack}>
          <ChevronLeft size={16} />
          返回 Direction Review
        </button>
        <div className="direction-paper-position" aria-live="polite">
          {reading ? `${readingIndex + 1} / ${readings.length}` : "Paper Card"}
        </div>
        <div className="direction-paper-paging">
          <button
            aria-label="上一篇论文"
            disabled={!previousReading}
            type="button"
            onClick={() => previousReading && onOpenPaper(previousReading.paper.id)}
          >
            <ChevronLeft size={15} />
            上一篇
          </button>
          <button
            aria-label="下一篇论文"
            disabled={!nextReading}
            type="button"
            onClick={() => nextReading && onOpenPaper(nextReading.paper.id)}
          >
            下一篇
            <ArrowRight size={15} />
          </button>
        </div>
      </header>

      {reading ? (
        <DirectionPaperDetail
          canUpload={canUpload}
          isGenerating={isGenerating}
          onOpenEvidenceInput={onOpenEvidenceInput}
          onPdfUpload={onPdfUpload}
          reading={reading}
        />
      ) : (
        <section className="direction-paper-route-state" role="status">
          <BookOpen size={22} />
          <div>
            <h1>{hasHydratedReview ? "未找到这篇 Paper Card" : "正在恢复 Paper Card"}</h1>
            <p>
              {hasHydratedReview
                ? `当前 Direction Review 中没有 paper id=${requestedPaperId}。系统不会回退到第一篇论文。`
                : "正在从当前项目的 Direction Review artifact 恢复论文详情，请稍候。"}
            </p>
            {hasHydratedReview ? (
              <button className="secondary-command" type="button" onClick={onBack}>
                返回论文列表
              </button>
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}

function formatReaderTitle(evidenceLevel: string, hasCard: boolean): string {
  if (!hasCard) {
    return "论文阅读 · Paper Card";
  }
  if (evidenceLevel === "full_text") {
    return "全文级深读 · Paper Card";
  }
  if (evidenceLevel === "abstract_only") {
    return "摘要级阅读 · Paper Card";
  }
  return "阅读提纲 · Paper Card";
}

function formatPaperCardSource(source: PaperCardMatchSource): string {
  if (source === "direction_review_artifact") {
    return "Direction Review artifact";
  }
  if (source === "paper_table") {
    return "Paper Table";
  }
  return "Manual input / unbound";
}

function formatFullTextSource(source: string): string {
  if (source === "arxiv_pdf") {
    return "arXiv PDF";
  }
  if (source === "openalex_open_access_pdf") {
    return "OpenAlex 开放全文";
  }
  if (source === "open_access_pdf") {
    return "开放获取 PDF";
  }
  if (source === "user_provided") {
    return "用户粘贴正文";
  }
  if (source === "user_uploaded_pdf") {
    return "用户上传 PDF";
  }
  return source || "未记录来源";
}

function mergeDirectionReadingWithPaperCard(
  reading: ApiDirectionPaperReading | null,
  card: ApiPaperCard | null,
): ApiDirectionPaperReading | null {
  if (!reading || !card || !doesPaperCardMatchDirectionReading(card, reading)) {
    return reading;
  }
  if (evidenceRank(card.evidence_level, card.full_text) < evidenceRank(reading.evidence_level, reading.full_text)) {
    return reading;
  }
  return {
    ...reading,
    artifact_id: card.artifact_id ?? reading.artifact_id,
    artifact_title: card.source_artifact_title ?? reading.artifact_title,
    evidence_level: card.evidence_level ?? reading.evidence_level,
    full_text: card.full_text ?? reading.full_text,
    updated_at: card.updated_at || card.created_at || reading.updated_at,
    signals: card.signals ?? reading.signals,
    sections: card.sections.length ? card.sections : reading.sections,
    weakest_assumption: card.weakest_assumption || reading.weakest_assumption,
    minimal_reproduction: card.minimal_reproduction || reading.minimal_reproduction,
  };
}

function doesPaperCardMatchDirectionReading(card: ApiPaperCard, reading: ApiDirectionPaperReading): boolean {
  const readingId = reading.paper_id || reading.paper.id;
  if (card.paper_id && readingId) {
    return card.paper_id === readingId;
  }
  if (card.card_source !== "direction_review_artifact") {
    return false;
  }
  const cardTitle = normalizePaperTitle(card.paper_title);
  const readingTitle = normalizePaperTitle(reading.paper_title || reading.paper.title);
  return Boolean(cardTitle && readingTitle && cardTitle === readingTitle);
}

function evidenceRank(level: string | undefined, provenance?: ApiFullTextProvenance): number {
  if (level === "full_text" && provenance?.status === "extracted") {
    return 3;
  }
  if (level === "full_text") {
    return 2;
  }
  if (level === "abstract_only") {
    return 1;
  }
  return 0;
}

function normalizePaperTitle(value: string | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ")
    .trim();
}

function fullTextFailureReason(provenance: ApiFullTextProvenance): string {
  if (provenance.error.trim()) {
    return provenance.error.trim();
  }
  if (provenance.status === "download_failed") {
    return "PDF 下载失败，来源可能需要登录或拒绝自动访问。";
  }
  if (provenance.status === "parse_failed") {
    return "已获取 PDF，但没有解析出可用于科研分析的正文。";
  }
  if (provenance.status === "disabled") {
    return "当前服务未启用全文获取。";
  }
  return "没有发现可公开访问的 PDF 地址。";
}

function FullTextProvenanceStatus({
  onOpenEvidenceInput,
  provenance,
  updatedAt,
}: {
  onOpenEvidenceInput?: () => void;
  provenance: ApiFullTextProvenance | undefined;
  updatedAt?: string;
}) {
  if (!provenance) {
    return null;
  }

  const extracted = provenance.status === "extracted";
  return (
    <section
      className={extracted ? "full-text-provenance-status extracted" : "full-text-provenance-status limited"}
      aria-label="full text acquisition status"
      data-testid="paper-card-provenance"
    >
      {extracted ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      <div>
        <strong>
          {extracted
            ? `已解析 ${provenance.page_count.toLocaleString("zh-CN")} 页 / ${provenance.character_count.toLocaleString("zh-CN")} 字符`
            : fullTextFailureReason(provenance)}
        </strong>
        <p>
          来源：{formatFullTextSource(provenance.source)}
          {provenance.pdf_url ? (
            <>
              {" · "}
              <a href={provenance.pdf_url} rel="noreferrer" target="_blank">
                查看 PDF 来源
              </a>
            </>
          ) : null}
        </p>
        {updatedAt ? <small className="full-text-updated-at">更新时间：{formatArtifactDate(updatedAt)}</small> : null}
        {!extracted && provenance.recovery_hint ? <small>建议：{provenance.recovery_hint}</small> : null}
      </div>
      {!extracted && onOpenEvidenceInput ? (
        <button type="button" onClick={onOpenEvidenceInput}>
          补充正文证据
          <ArrowRight size={14} />
        </button>
      ) : null}
    </section>
  );
}

function PdfUploadControl({
  busy,
  disabled,
  onUpload,
  paperId,
}: {
  busy: boolean;
  disabled: boolean;
  onUpload: (paperId: string, file: File) => void;
  paperId: string;
}) {
  const inputId = `paper-pdf-upload-${paperId.replace(/[^a-zA-Z0-9_-]/g, "-") || "unbound"}`;
  const unavailable = disabled || busy || !paperId;
  return (
    <div className="pdf-upload-control" aria-label="upload paper PDF">
      <div>
        <Download size={18} aria-hidden="true" />
        <span>
          <strong>直接上传论文 PDF</strong>
          <small>解析文本层并重新生成全文级 Paper Card；文件仅发送到本地 ScholarFlow API。</small>
        </span>
      </div>
      <label className={unavailable ? "disabled" : ""} htmlFor={inputId} aria-disabled={unavailable}>
        {busy ? "正在解析…" : "选择 PDF"}
      </label>
      <input
        accept="application/pdf,.pdf"
        disabled={unavailable}
        id={inputId}
        type="file"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) {
            onUpload(paperId, file);
          }
        }}
      />
    </div>
  );
}

type EvidenceBoundary = {
  title: string;
  message: string;
  confirmed: string;
  cannotConfirm: string;
  nextAction: string;
};

function buildEvidenceBoundary(evidenceLevel: string | undefined): EvidenceBoundary | null {
  if (evidenceLevel === "metadata_only") {
    return {
      title: "元数据级证据，不是全文结论",
      message: "当前只基于标题、年份、来源等元数据生成阅读提纲。方法、实验、claim 和反例都需要补充 abstract 或 PDF 后才能确认。",
      confirmed: "论文标题、年份、来源与检索方向的表面关联。",
      cannotConfirm: "研究方法、实验设置、claim、局限和复现条件。",
      nextAction: "先补充摘要；需要做科研判断时上传可复制文本的 PDF。",
    };
  }
  if (evidenceLevel === "abstract_only") {
    return {
      title: "摘要级证据，不是全文结论",
      message: "当前只基于摘要和候选元数据生成结构化阅读。它适合决定是否精读，但不能替代完整 PDF 的方法和实验核验。",
      confirmed: "摘要明确陈述的研究对象、核心任务和作者公开 claim。",
      cannotConfirm: "方法细节、完整 baseline、消融、失败样本与统计可靠性。",
      nextAction: "上传本地 PDF，系统会重新绑定当前论文并升级为全文已验证。",
    };
  }
  return null;
}

function LimitedEvidenceSummary({ boundary }: { boundary: EvidenceBoundary }) {
  return (
    <section className="limited-evidence-summary" aria-label="limited evidence summary">
      <div>
        <strong>能确认什么</strong>
        <p>{boundary.confirmed}</p>
      </div>
      <div>
        <strong>不能确认什么</strong>
        <p>{boundary.cannotConfirm}</p>
      </div>
      <div>
        <strong>如何获得全文</strong>
        <p>{boundary.nextAction}</p>
      </div>
    </section>
  );
}

function buildMemoryEvidenceBoundary(
  hits: NonNullable<ApiResearchMemoryQueryResponse["hits"]>,
): { title: string; message: string } | null {
  if (!hits.length) {
    return null;
  }
  const levels = hits.map((hit) => normalizeEvidencePack(normalizeResearchSight(hit.research_sight).evidence_pack).evidence_level);
  const limitedCount = levels.filter((level) => level === "abstract_only" || level === "metadata_only" || level === "unknown").length;
  const fullTextCount = levels.filter((level) => level === "full_text").length;
  if (limitedCount > 0 && fullTextCount === 0) {
    return {
      title: "摘要级证据，不是全文结论",
      message: `当前 ${hits.length} 条 memory hit 主要来自摘要级或元数据级 Paper Card。回答可用于定位线索，但不能当作已经核验全文后的确定判断。`,
    };
  }
  return null;
}

function buildMemoryRewriteSuggestion(direction: string, question: string): string {
  const topic = direction.trim() || question.trim() || "当前研究方向";
  return `${topic}：具体研究对象、失败模式、数据集、指标与 baseline 分别是什么？`;
}

function buildDecisionEvidenceBoundary(
  decision: ApiResearchDecisionResponse | null,
): { title: string; message: string } | null {
  const quality = decision?.evidence_quality;
  if (!quality) {
    return null;
  }
  const abstractCount = Number(quality.abstract_only_card_count ?? 0);
  const metadataCount = Number(quality.metadata_only_card_count ?? 0);
  const fullTextCount = Number(quality.full_text_card_count ?? 0);
  const limitedCount = abstractCount + metadataCount;
  if (limitedCount > 0 && fullTextCount === 0) {
    return {
      title: "摘要级证据，不是全文结论",
      message: `当前研究决策主要依赖 ${abstractCount} 张摘要级 card 和 ${metadataCount} 张元数据级 card。Gap、Idea Validation 和实验计划只能作为保守候选，不能视为已完成全文级论证。`,
    };
  }
  return null;
}

function buildMissingEvidenceChecklist(card: ApiPaperCard | null): string[] {
  if (!card) {
    return [];
  }
  const checklist: string[] = [];
  if (card.evidence_level === "metadata_only") {
    checklist.push("缺 abstract/PDF/正文");
  }
  if (card.evidence_level === "abstract_only") {
    checklist.push("缺 PDF/完整正文、method/experiment 表格和 failure case");
  }
  const missingSignals = card.signals?.missing_signals ?? [];
  missingSignals.forEach((signal) => checklist.push(`缺 ${signal}`));
  if (card.minimal_reproduction.toLowerCase().includes("status: blocked")) {
    checklist.push("最小复现实验未解锁：需要补齐 claim + dataset + metric + baseline");
  }
  return [...new Set(checklist)];
}

type ParsedPaperCardSectionContent = {
  evidenceGap: string;
  outline: string;
  primary: string;
  verification: string;
};

function parsePaperCardSectionContent(content: string): ParsedPaperCardSectionContent {
  let normalized = content.replace(/\r\n?/g, "\n").trim();
  const boundaryMatch = normalized.match(
    /^证据边界[（(](?:metadata_only|abstract_only)[）)][:：][\s\S]*?(?=\n阅读提纲[:：])/,
  );

  if (boundaryMatch) {
    normalized = normalized.slice(boundaryMatch[0].length).replace(/^\n+/, "");
  }

  const outlinePrefix = "阅读提纲：";
  const visibleMarker = "\n当前可见线索：";
  const gapMarker = "\n证据缺口：";
  const verificationMarker = "\n需要验证的问题：";
  const visibleIndex = normalized.indexOf(visibleMarker);
  const verificationIndex = normalized.lastIndexOf(verificationMarker);
  const gapIndex = verificationIndex >= 0
    ? normalized.lastIndexOf(gapMarker, verificationIndex - 1)
    : normalized.lastIndexOf(gapMarker);

  if (
    normalized.startsWith(outlinePrefix) &&
    visibleIndex >= 0 &&
    gapIndex > visibleIndex &&
    verificationIndex > gapIndex
  ) {
    return {
      outline: normalized.slice(outlinePrefix.length, visibleIndex).trim(),
      primary: normalized.slice(visibleIndex + visibleMarker.length, gapIndex).trim(),
      evidenceGap: normalized.slice(gapIndex + gapMarker.length, verificationIndex).trim(),
      verification: normalized.slice(verificationIndex + verificationMarker.length).trim(),
    };
  }

  return {
    evidenceGap: "",
    outline: "",
    primary: normalized,
    verification: "",
  };
}

function formatPaperCardSectionTitle(title: string): string {
  return title.replace(/^\s*\d{1,2}\s*[.、:：)）]\s*/, "").trim();
}

function splitPaperCardSectionParagraphs(content: string): string[] {
  const withSignalBreaks = content.replace(
    /;\s*(?=(?:method|dataset|metric|baseline|claim|limitation|type)=)/gi,
    ";\n",
  );
  const sourceLines = withSignalBreaks.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const paragraphs: string[] = [];
  for (const line of sourceLines) {
    const sentences = line.split(/(?<=[。！？])\s+/).map((sentence) => sentence.trim()).filter(Boolean);
    let current = "";
    for (const sentence of sentences) {
      if (current && current.length + sentence.length > 380) {
        paragraphs.push(current);
        current = sentence;
      } else {
        current = current ? `${current} ${sentence}` : sentence;
      }
    }
    if (current) {
      paragraphs.push(current);
    }
  }
  return paragraphs.length ? paragraphs : [content];
}

function ConferenceMarquee() {
  const repeatedBadges = [...conferenceBadges, ...conferenceBadges];
  return (
    <div className="conference-marquee" aria-hidden="true">
      <div className="conference-track">
        {repeatedBadges.map((label, index) => (
          <span className="conference-badge" key={`${label}-${index}`}>
            {label}
          </span>
        ))}
      </div>
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
      detail: apiStatus === "online" ? "SQLite 持久化" : "等待 API 连接",
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
  activeProject,
  agentBusy,
  agentPlan,
  agentRunStatus,
  agentTask,
  apiStatus,
  onAgentTaskChange,
  onCancelAgentRun,
  onCreateAgentPlan,
  onExecuteAgentRun,
}: {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentRunStatus: ApiAgentRunStatusResponse | null;
  agentTask: string;
  apiStatus: ApiStatus;
  onAgentTaskChange: (task: string) => void;
  onCancelAgentRun: () => void;
  onCreateAgentPlan: () => void;
  onExecuteAgentRun: () => void;
}) {
  const isDemo = isDemoProject(activeProject);
  const visibleRunStatus = agentRunStatus?.status ?? agentPlan?.status ?? "idle";
  const isRunning = visibleRunStatus === "running";
  const canPlan = !isDemo && !agentBusy && apiStatus === "online" && agentTask.trim().length > 0;
  const canExecute = Boolean(
    agentPlan &&
      !["running", "completed", "completed_with_warnings", "partial", "failed", "cancelled"].includes(visibleRunStatus) &&
      !agentBusy &&
      apiStatus === "online" &&
      !isDemo,
  );
  const canCancel = Boolean(agentPlan && isRunning && apiStatus === "online" && !isDemo);
  const isDemoMode = Boolean(agentPlan?.steps.some((step) => step.tool === "search_mock_papers"));
  const disabledReason = isDemo
    ? "Demo 项目是只读 preview，不会执行真实 Agent 工具链。请创建真实项目。"
    : apiStatus !== "online"
      ? "API 未连接。"
      : "";

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
          <span className={`run-status ${visibleRunStatus}`}>{visibleRunStatus}</span>
        </div>
      </div>

      <label className="agent-task-field">
        任务
        <textarea value={agentTask} onChange={(event) => onAgentTaskChange(event.target.value)} />
      </label>

      <div className="agent-action-row">
        <button
          className="secondary-command"
          disabled={!canPlan}
          title={disabledReason}
          type="button"
          onClick={onCreateAgentPlan}
        >
          <BrainCircuit size={17} />
          生成计划
        </button>
        <button className="secondary-command" disabled={!canExecute} title={disabledReason} type="button" onClick={onExecuteAgentRun}>
          <Play size={17} />
          {isRunning ? "执行中" : "确认执行"}
        </button>
        <button className="secondary-command" disabled={!canCancel} title={canCancel ? "当前 tool 完成后停止后续步骤。" : disabledReason || "只有 running 状态可以取消。"} type="button" onClick={onCancelAgentRun}>
          <X size={17} />
          取消运行
        </button>
      </div>

      {agentPlan ? (
        <div className="agent-plan-box">
          <p>{agentPlan.rationale}</p>
          {agentRunStatus ? (
            <div className="agent-run-progress" aria-label="agent run progress">
              <strong>{agentRunStatus.run_status_summary || `Agent Run ${agentRunStatus.status}`}</strong>
              <span aria-live="polite" data-testid="agent-run-current-tool">
                {agentRunStatus.status === "running"
                  ? `Timeline、artifacts 和 workflow steps 正在刷新${agentRunStatus.current_tool ? `；当前工具：${agentRunStatus.current_tool}` : ""}`
                  : `最终状态：${agentRunStatus.status}`}
              </span>
              {agentRunStatus.warnings.length ? (
                <ul>
                  {agentRunStatus.warnings.slice(0, 3).map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          <div className="agent-plan-list">
            {agentPlan.steps.map((step) => (
              <div className="agent-plan-row" key={step.id}>
                <StatusIcon status={toPlanStatus(step.status)} />
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.tool}{formatAgentStepMetrics(step)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function formatAgentStepMetrics(step: ApiAgentPlanStep): string {
  const metrics = step.metrics ?? {};
  const fragments: string[] = [];
  if (typeof metrics.review_status === "string") {
    fragments.push(metrics.review_status);
  }
  if (typeof metrics.experiment_status === "string") {
    fragments.push(`实验 ${metrics.experiment_status}`);
  }
  if (typeof metrics.warning_count === "number" && metrics.warning_count > 0) {
    fragments.push(`${metrics.warning_count} 条警告`);
  }
  if (typeof metrics.paper_count === "number") {
    fragments.push(`本步骤返回 ${metrics.paper_count} 篇`);
  }
  if (typeof metrics.gap_evidence_paper_count === "number") {
    fragments.push(`gap 证据 ${metrics.gap_evidence_paper_count} 篇`);
  }
  return fragments.length ? ` · ${fragments.join(" · ")}` : "";
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
            <p>{warningPreview(errors, 2)}</p>
          </div>
        ) : null}
      </section>

      <section className="table-shell" aria-label="paper table">
        {papers.length ? (
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
        ) : (
          <div className="empty-table-state">
            <h2>本次检索还没有返回论文</h2>
            <p>
              如果看到 OpenAlex 429，说明外部检索源暂时限流。可以稍后重试，或换一个更具体的关键词；系统不会再用旧 demo
              论文冒充本次搜索结果。
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

export function DirectionReviewView({
  apiMessage,
  apiStatus,
  direction,
  isGenerating,
  onDirectionChange,
  onGenerate,
  onLoadArtifact,
  onOpenPaperCard,
  onRoundChange,
  review,
  round,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  direction: string;
  isGenerating: boolean;
  onDirectionChange: (direction: string) => void;
  onGenerate: () => void;
  onLoadArtifact: (artifactId: string) => void;
  onOpenPaperCard: (paperId: string) => void;
  onRoundChange: (round: number) => void;
  review: ApiDirectionReviewResponse | null;
  round: number;
}) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const readings = review?.papers ?? [];
  const artifactRefs = getDirectionArtifactRefs(review);
  const recommendedPaperIds = review?.recommended_paper_ids ?? [];
  const recommendedReadings =
    readings.filter((reading) => recommendedPaperIds.includes(reading.paper.id) || reading.self_read_priority) ?? [];
  const canGenerate = apiStatus === "online" && !isGenerating && direction.trim().length > 0;
  const expectedRoundCount = review?.target_paper_count ?? 10;
  const actualRoundCount = review?.relevant_read_count ?? review?.round_read_count ?? readings.length;
  const fullTextCount = readings.filter((reading) => reading.evidence_level === "full_text").length;
  const isPartialReview = review?.review_status === "partial";
  const isBlockedReview = review?.review_status === "blocked";
  const coverage = review?.relevance_coverage ?? {};
  const partialRoundWarning =
    review && (isPartialReview || isBlockedReview || actualRoundCount < expectedRoundCount)
      ? `本轮已结构化阅读 ${actualRoundCount}/${expectedRoundCount} 篇强/中相关论文；已过滤 ${review.low_relevance_count ?? coverage.weak_match_count ?? 0} 篇弱相关、${review.off_topic_count ?? coverage.off_topic_count ?? 0} 篇离题候选。`
      : "";
  const reviewWarnings = review ? [partialRoundWarning, ...review.errors].filter(Boolean) : [];
  const statusLabel = review
    ? review.review_status === "complete"
      ? "候选覆盖完成"
      : review.review_status === "blocked"
        ? "证据阻塞"
        : "部分完成"
    : "等待生成";
  const directionSummary = formatAcademicText(review?.direction_summary ?? "");
  const directionSummaryPreview = buildDirectionSummaryPreview(directionSummary);

  return (
    <div className="direction-review-page">
      <section className="direction-review-controls" aria-label="direction review controls">
        <div className="direction-control-header">
          <div>
            <p className="section-kicker">Direction Review</p>
            <h2>方向精读工作台</h2>
            <p>每轮筛选并结构化阅读最多 10 篇强/中相关论文；详情在独立 Paper Card 页面打开。</p>
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
          <span title="read 指方向精读已生成结构化阅读记录的论文数，不等于本轮候选或项目累计论文数。">
            {review ? `目标 ${expectedRoundCount} 篇，已结构化阅读 ${actualRoundCount} 篇` : "每轮最多结构化阅读 10 篇"}
          </span>
          <span>顶会/顶刊优先</span>
          <span>点击进入独立 Paper Card</span>
        </div>

        <div className={`project-status-note ${apiStatus}`}>
          <Lightbulb size={18} />
          <span>{apiMessage}</span>
        </div>
      </section>

      {review ? (
        <>
          <section className="direction-summary-panel" aria-label="direction summary">
            <div className="direction-summary-header">
              <div>
                <p className="section-kicker">Round {review.round} · Cumulative Understanding</p>
                <h1>{formatAcademicText(review.direction)}</h1>
                <p className="direction-summary-intro">
                  {review.review_status === "complete"
                    ? `本轮候选覆盖达到方向级阈值，其中 ${fullTextCount}/${readings.length} 篇已解析全文；候选覆盖不等于全文精读完成。`
                    : "当前结果存在检索或证据缺口，请先查看警告再继续。"}
                </p>
              </div>
              <span className={`direction-status-badge ${review.review_status}`}>{statusLabel}</span>
            </div>

            <div className="direction-metric-strip" aria-label="direction review metrics">
              <div title="read：本轮已完成结构化阅读的强/中相关论文数；分母是本轮目标。">
                <span>已结构化阅读</span>
                <strong>{actualRoundCount}/{expectedRoundCount}</strong>
              </div>
              <div title="已上传或获取并成功解析全文的论文数；它不代表本轮所有论文均为全文级阅读。">
                <span>全文级证据</span>
                <strong>{fullTextCount}/{readings.length}</strong>
              </div>
              <div title="因离开当前研究领域或未命中核心主题而排除的候选数。">
                <span>过滤离题</span>
                <strong>{review.off_topic_count ?? coverage.off_topic_count ?? 0}</strong>
              </div>
              <div title="当前方向跨轮次已保存的结构化阅读记录数。">
                <span>累计已读</span>
                <strong>{review.total_read_count}</strong>
              </div>
            </div>

            {partialRoundWarning ? (
              <div className="partial-review-banner">
                <AlertTriangle size={18} />
                <div>
                  <strong>{isBlockedReview ? "Blocked" : "Partial"} Direction Review · {actualRoundCount}/{expectedRoundCount}</strong>
                  <p>{partialRoundWarning}</p>
                </div>
              </div>
            ) : null}

            <div
              className={summaryExpanded ? "direction-summary-copy expanded" : "direction-summary-copy"}
              id="direction-summary-copy"
            >
              <strong>本轮判断</strong>
              <p>{summaryExpanded ? directionSummary : directionSummaryPreview}</p>
            </div>
            <button
              aria-controls="direction-summary-copy"
              aria-expanded={summaryExpanded}
              className="direction-summary-toggle"
              type="button"
              onClick={() => setSummaryExpanded((value) => !value)}
            >
              {summaryExpanded ? "收起完整总结" : "展开完整总结"}
              <ChevronDown size={15} />
            </button>
          </section>

          <ResearchWarningPanel
            className="direction-visible-warning"
            title="检索与证据状态"
            warnings={reviewWarnings}
            fallback="当前 Direction Review 没有报告检索或证据边界警告。"
          />

          {readings.length ? (
            <section className="recommendation-panel" aria-label="recommended papers">
              <div className="direction-section-header">
                <div>
                  <p className="section-kicker">Personal Deep Reading</p>
                  <h2>优先亲自精读</h2>
                </div>
                <span>推荐精读 {Math.min(recommendedReadings.length, 3)} 篇</span>
              </div>
              <div className="recommendation-list">
                {recommendedReadings.slice(0, 3).map((reading, index) => (
                  <button
                    aria-describedby={`recommended-paper-description-${index}`}
                    aria-label={`打开推荐 Paper Card：${reading.paper.title}`}
                    className="recommendation-item"
                    key={`${reading.paper.id}-${reading.paper.title}-${index}`}
                    type="button"
                    onClick={() => onOpenPaperCard(reading.paper.id)}
                  >
                    <span>{index + 1}</span>
                    <div>
                      <strong>{formatAcademicText(reading.paper.title)}</strong>
                      <small id={`recommended-paper-description-${index}`}>{reading.why_selected}</small>
                    </div>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {readings.length ? (
            <section className="direction-paper-list" aria-label="direction paper cards">
              <div className="direction-section-header">
                <div>
                  <p className="section-kicker">Round {review.round} Library</p>
                  <h2>本轮全部 Paper Cards</h2>
                </div>
                <span>已结构化阅读 {actualRoundCount} 篇</span>
              </div>
              <div className="direction-paper-rows">
              {readings.map((reading, index) => {
                return (
                  <button
                    aria-describedby={`direction-paper-description-${index} direction-paper-metadata-${index} direction-paper-status-${index}`}
                    aria-label={`打开 Paper Card：${reading.paper.title}`}
                    className="direction-paper-row"
                    key={`${reading.paper.id}-${reading.paper.title}-${index}`}
                    type="button"
                    onClick={() => onOpenPaperCard(reading.paper.id)}
                  >
                    <span className="direction-paper-index">{String(index + 1).padStart(2, "0")}</span>
                    <div className="direction-paper-row-copy">
                      <h3>{formatAcademicText(reading.paper.title)}</h3>
                      <p id={`direction-paper-description-${index}`}>{reading.why_selected}</p>
                      <div className="direction-paper-meta" id={`direction-paper-metadata-${index}`}>
                        <span>{reading.paper.authors || "authors unknown"}</span>
                        <span>{reading.paper.year || "year unknown"}</span>
                        <span>{reading.paper.venue || reading.paper.source || "source unknown"}</span>
                      </div>
                    </div>
                    <div className="direction-paper-row-status" id={`direction-paper-status-${index}`}>
                      {reading.self_read_priority ? <strong>推荐精读</strong> : null}
                      <span className={`evidence-badge ${reading.evidence_level ?? "metadata_only"}`}>
                        {formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}
                      </span>
                    </div>
                    <ArrowRight size={17} />
                  </button>
                );
              })}
              </div>
            </section>
          ) : (
            <section className="direction-empty-state">
              <BookOpen size={22} />
              <div>
                <h2>精读详情已保存为 Artifact</h2>
                <p>为了控制 Direction Review 响应体，完整 BaselineMap、Paper Cards 和 Memory 不再随 POST 返回。点击上方 Artifact 可按需回读完整内容。</p>
              </div>
            </section>
          )}

          <details className="direction-evidence-details">
            <summary>
              <span>
                <strong>研究依据与产物</strong>
                <small>Scope、BaselineMap 与 {artifactRefs.length} 个已保存 Artifact</small>
              </span>
              <ChevronDown size={17} />
            </summary>
            <div className="direction-evidence-content">
              {review.scope ? (
                <>
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
                  <div className="direction-subtopic-row">
                    {review.scope.subtopics.map((subtopic) => (
                      <span key={subtopic}>{subtopic}</span>
                    ))}
                  </div>
                </>
              ) : null}
              {review.baseline_map ? <BaselineMapPanel baselineMap={review.baseline_map} /> : null}
              {artifactRefs.length ? (
                <DirectionArtifactRefs artifacts={artifactRefs} onLoadArtifact={onLoadArtifact} />
              ) : null}
            </div>
          </details>
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

function formatAcademicText(value: string): string {
  return value
    .replace(/\$\s*(\d+)\^\{\\circ\}\s*\$/g, "$1°")
    .replace(/(\d+)\^\{\\circ\}/g, "$1°")
    .replace(/\s+/g, " ")
    .trim();
}

function buildDirectionSummaryPreview(value: string, maxLength = 340): string {
  if (value.length <= maxLength) {
    return value;
  }
  const candidate = value.slice(0, maxLength);
  const sentenceEnd = Math.max(
    candidate.lastIndexOf("。"),
    candidate.lastIndexOf("；"),
    candidate.lastIndexOf(". "),
  );
  const cutoff = sentenceEnd >= Math.floor(maxLength * 0.58) ? sentenceEnd + 1 : maxLength;
  return `${candidate.slice(0, cutoff).trimEnd()}…`;
}

function BaselineReferenceList({
  references,
  title,
}: {
  references: NonNullable<ApiDirectionReviewResponse["baseline_map"]>["classic_baselines"];
  title: string;
}) {
  return (
    <div className="baseline-reference-list">
      <strong>{title}</strong>
      {references.length ? (
        references.slice(0, 3).map((reference, index) => (
          <article key={`${title}-${reference.title}-${reference.year}-${index}`}>
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

function BaselineMapPanel({ baselineMap }: { baselineMap: NonNullable<ApiDirectionReviewResponse["baseline_map"]> }) {
  return (
    <div className="baseline-map-panel" aria-label="baseline map">
      <div className="baseline-map-header">
        <div>
          <p className="section-kicker">BaselineMap</p>
          <h3>方向背景与对比参照</h3>
        </div>
          <span>{baselineMap.generated_from.length} candidates</span>
      </div>
      <p>{baselineMap.task_definition}</p>
      <div className="baseline-map-grid">
        <BaselineReferenceList title="经典 baseline" references={baselineMap.classic_baselines} />
        <BaselineReferenceList title="近三年强 baseline" references={baselineMap.recent_strong_baselines} />
        <BaselineReferenceList title="异质范式" references={baselineMap.alternative_paradigms} />
      </div>
      <div className="baseline-risk-grid">
        <div>
          <strong>证据约束</strong>
          <span>{baselineMap.evidence_summary}</span>
        </div>
        <div>
          <strong>常见 benchmark</strong>
          <span>{baselineMap.common_benchmarks.slice(0, 5).join(" / ")}</span>
        </div>
        <div>
          <strong>评价风险</strong>
          <span>{baselineMap.evaluation_risks.slice(0, 2).join("；")}</span>
        </div>
        <div>
          <strong>开放问题</strong>
          <span>{baselineMap.open_questions.slice(0, 2).join("；")}</span>
        </div>
      </div>
    </div>
  );
}

function DirectionArtifactRefs({
  artifacts,
  onLoadArtifact,
}: {
  artifacts: ApiArtifactRef[];
  onLoadArtifact: (artifactId: string) => void;
}) {
  return (
    <div className="direction-artifact-panel" aria-label="direction review artifacts">
      <div className="baseline-map-header">
        <div>
          <p className="section-kicker">Artifacts</p>
          <h3>完整内容按需回读</h3>
        </div>
        <span>{artifacts.length} saved</span>
      </div>
      <div className="direction-artifact-list">
        {artifacts.map((artifact) => (
          <button key={artifact.id} type="button" onClick={() => onLoadArtifact(artifact.id)}>
            <FileText size={16} />
            <div>
              <strong>{artifact.title}</strong>
              <small>{artifact.kind} · {formatArtifactDate(artifact.created_at)}</small>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function DirectionPaperDetail({
  canUpload,
  isGenerating,
  onOpenEvidenceInput,
  onPdfUpload,
  reading,
}: {
  canUpload: boolean;
  isGenerating: boolean;
  onOpenEvidenceInput: () => void;
  onPdfUpload: (paperId: string, file: File) => void;
  reading: ApiDirectionPaperReading;
}) {
  const [activeSectionNumber, setActiveSectionNumber] = useState(1);
  const signals = reading.signals;
  const missingSignals = signals?.missing_signals ?? [];
  const evidenceBoundary = buildEvidenceBoundary(reading.evidence_level);
  const missingEvidence = [
    ...(evidenceBoundary ? [evidenceBoundary.title] : []),
    ...missingSignals.map((signal) => `缺 ${signal}`),
  ];
  const sections = reading.sections ?? [];
  const activeSectionIndex = sections.length
    ? Math.min(Math.max(activeSectionNumber - 1, 0), sections.length - 1)
    : -1;
  const activeSection = activeSectionIndex >= 0 ? sections[activeSectionIndex] : null;
  const researchSight = normalizeResearchSight(reading.research_sight);
  const evidencePack = normalizeEvidencePack(researchSight.evidence_pack);
  const critiqueEvidence = new Map(
    (researchSight.critique_evidence ?? []).map((item) => [item.field, item]),
  );

  useEffect(() => {
    setActiveSectionNumber(1);
  }, [reading.paper?.id]);

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
          <h2 id="direction-paper-title" tabIndex={-1}>
            {formatAcademicText(reading.paper?.title ?? "Untitled paper")}
          </h2>
        </div>
        {reading.paper?.url ? (
          <a href={reading.paper.url} rel="noreferrer" target="_blank">
            open paper
          </a>
        ) : null}
      </div>

      <section className="reader-evidence-summary direction-reader-evidence" aria-label="direction paper evidence summary">
        <div className={`reader-evidence-level ${reading.evidence_level}`}>
          <ShieldCheck size={16} />
          <strong>{formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}</strong>
          <span>来源：{formatFullTextSource(reading.full_text?.source ?? "")}</span>
          {reading.full_text?.status === "extracted" ? (
            <span>
              {reading.full_text.page_count} 页 / {reading.full_text.character_count.toLocaleString("zh-CN")} 字符
            </span>
          ) : null}
          {reading.updated_at ? <span>更新：{formatArtifactDate(reading.updated_at)}</span> : null}
        </div>
        {evidenceBoundary ? <LimitedEvidenceSummary boundary={evidenceBoundary} /> : null}
        {missingEvidence.length ? <small>待补证据：{missingEvidence.join("；")}</small> : null}
      </section>

      <article className="direction-abstract">
        <h3>摘要中文内容</h3>
        <small>Evidence level: {formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}</small>
        <p>{reading.abstract_translation}</p>
      </article>

      <FullTextProvenanceStatus
        onOpenEvidenceInput={onOpenEvidenceInput}
        provenance={reading.full_text}
        updatedAt={reading.updated_at}
      />

      {reading.full_text?.status !== "extracted" ? (
        <PdfUploadControl
          busy={isGenerating}
          disabled={!canUpload}
          onUpload={onPdfUpload}
          paperId={reading.paper.id}
        />
      ) : null}

      {signals ? (
        <details className="paper-signals-panel direction-detail-disclosure" aria-label="paper evidence signals">
          <summary className="paper-signals-header">
            <div>
              <p className="section-kicker">Paper Signals</p>
              <h3>论文证据信号</h3>
            </div>
            <FileText size={18} />
          </summary>
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
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.method)}</small>
            </div>
            <div>
              <strong>数据集</strong>
              <span>{signals.dataset || "暂无"}</span>
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.dataset)}</small>
            </div>
            <div>
              <strong>指标</strong>
              <span>{signals.metric || "暂无"}</span>
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.metric)}</small>
            </div>
            <div>
              <strong>Claim</strong>
              <span>{signals.claim || "暂无"}</span>
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.claim)}</small>
            </div>
            <div>
              <strong>本论文自身 Limitation</strong>
              <span>{signals.limitation || "暂无"}</span>
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.limitation)}</small>
            </div>
            <div>
              <strong>已有研究不足</strong>
              <span>{signals.prior_work_limitation || "暂无可定位证据"}</span>
              <small className="critique-evidence-note">{formatSignalEvidenceLocation(signals.signal_evidence?.prior_work_limitation)}</small>
            </div>
            <div>
              <strong>缺失字段</strong>
              <span>{missingSignals.length ? missingSignals.join(", ") : "none"}</span>
            </div>
          </div>
        </details>
      ) : null}

      <details className="research-sight-panel direction-detail-disclosure">
        <summary className="research-sight-header">
          <div>
            <p className="section-kicker">Research Sight</p>
            <h3>科研审美评价</h3>
          </div>
          <BrainCircuit size={18} />
        </summary>
        <div className="research-sight-score-grid">
          <div>
            <strong>证据等级</strong>
            <span>
              {formatEvidenceLevel(reading.evidence_level ?? evidencePack.evidence_level)}；
              来源置信度 {evidencePack.source_confidence || "unknown"} / 抽取置信度 {evidencePack.extraction_confidence || "unknown"} /
              最终 {evidencePack.confidence || "low"}。{evidencePack.grounding_summary}
            </span>
          </div>
          <div>
            <strong>动机锋利度</strong>
            <span>{researchSight.motivation_sharpness || "暂无"}</span>
          </div>
          <div>
            <strong>解法优雅性</strong>
            <span>{researchSight.solution_elegance || "暂无"}</span>
          </div>
          <div>
            <strong>评估真实性</strong>
            <span>{researchSight.evaluation_integrity || "暂无"}</span>
          </div>
          <div>
            <strong>范式启发性</strong>
            <span>{researchSight.paradigm_inspiration || "暂无"}</span>
          </div>
        </div>
        <div className="research-sight-critique">
          <div>
            <strong>为什么好</strong>
            <p>{researchSight.why_good || "当前证据不足。"}</p>
            {renderCritiqueEvidence("why_good")}
          </div>
          <div>
            <strong>为什么不好</strong>
            <p>{researchSight.why_not_good || "当前证据不足。"}</p>
            {renderCritiqueEvidence("why_not_good")}
          </div>
          <div>
            <strong>更好角度</strong>
            <p>{researchSight.better_angle || "当前证据不足。"}</p>
            {renderCritiqueEvidence("better_angle")}
          </div>
          <div>
            <strong>Baseline 对比</strong>
            <p>{researchSight.baseline_comparison || "当前证据不足。"}</p>
            {renderCritiqueEvidence("baseline_comparison")}
          </div>
          <div>
            <strong>下一步 proposal</strong>
            <p>{researchSight.next_step_proposal || "当前证据不足。"}</p>
            {renderCritiqueEvidence("next_step_proposal")}
          </div>
        </div>
        <div className="sight-evidence-grid" aria-label="research sight evidence">
          <div>
            <strong>证据片段</strong>
            {evidencePack.snippets.length ? (
              evidencePack.snippets.slice(0, 4).map((snippet) => (
                <article key={`${snippet.source}-${snippet.id}`}>
                  <span>
                    {snippet.source} · {snippet.kind} · {snippet.confidence}
                    {snippet.section ? ` · ${snippet.section}` : ""}
                    {typeof snippet.page === "number" ? ` · p.${snippet.page}` : ""}
                  </span>
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
            {evidencePack.missing_evidence.length ? (
              <ul>
                {evidencePack.missing_evidence.slice(0, 5).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>当前没有显式缺失项。</p>
            )}
          </div>
        </div>
      </details>

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

      <section className="direction-section-reader" aria-label="12 段精读">
        <div className="question-board-head">
          <div>
            <p className="section-kicker">Deep Paper Card</p>
            <h2>12 段科研精读</h2>
          </div>
          <span>{sections.length}/12 已生成</span>
        </div>
        {sections.length ? (
          <div className="paper-reader-workspace direction-paper-section-workspace">
            <nav className="paper-reader-toc" aria-label="独立 Paper Card 精读目录">
              <ol>
                {sections.map((section, index) => {
                  const isActive = activeSectionIndex === index;
                  return (
                    <li key={`${section.id}-${index}`}>
                      <button
                        aria-controls={isActive ? `direction-paper-section-${index + 1}` : undefined}
                        aria-current={isActive ? true : undefined}
                        aria-label={`第 ${index + 1} 节：${section.title}`}
                        className="paper-reader-toc-item"
                        type="button"
                        onClick={() => setActiveSectionNumber(index + 1)}
                      >
                        <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                        <strong>{formatPaperCardSectionTitle(section.title)}</strong>
                        <Check size={14} aria-hidden="true" />
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            {activeSection ? (
              <article
                className="paper-reader-section direction-active-section"
                id={`direction-paper-section-${activeSectionIndex + 1}`}
                tabIndex={-1}
              >
                <header>
                  <span>
                    Section {String(activeSectionIndex + 1).padStart(2, "0")} / {sections.length}
                  </span>
                  <h3 data-testid={`direction-paper-section-heading-${activeSectionIndex + 1}`}>
                    {formatPaperCardSectionTitle(activeSection.title)}
                  </h3>
                </header>
                <div className="paper-reader-section-body direction-active-section-body">
                  {splitPaperCardSectionParagraphs(activeSection.content).map((paragraph, index) => (
                    <p key={`${activeSection.id}-paragraph-${index}`}>{paragraph}</p>
                  ))}
                </div>
                <footer className="paper-reader-section-nav" aria-label="独立 Paper Card 章节切换">
                  <button
                    disabled={activeSectionIndex <= 0}
                    type="button"
                    onClick={() => setActiveSectionNumber(activeSectionIndex)}
                  >
                    <ChevronLeft size={15} />
                    上一节
                  </button>
                  <span aria-live="polite">
                    {activeSectionIndex + 1} / {sections.length}
                  </span>
                  <button
                    disabled={activeSectionIndex >= sections.length - 1}
                    type="button"
                    onClick={() => setActiveSectionNumber(activeSectionIndex + 2)}
                  >
                    下一节
                    <ArrowRight size={15} />
                  </button>
                </footer>
              </article>
            ) : null}
          </div>
        ) : (
          <article className="direction-detail-section empty">
            <span>00</span>
            <div>
              <h3>暂无 12 sections</h3>
              <p>当前 artifact 没有提供 card.sections 或 sections 字段，但 Paper Signals 与 Research Sight 仍可查看。</p>
            </div>
          </article>
        )}
      </section>
    </section>
  );
}

export function ResearchMemoryView({
  apiMessage,
  apiStatus,
  direction,
  isQuerying,
  isRagQuerying,
  onQuestionChange,
  onQuery,
  onQueryRag,
  onSelectView,
  onTopKChange,
  question,
  ragResult,
  result,
  topK,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  direction: string;
  isQuerying: boolean;
  isRagQuerying: boolean;
  onQuestionChange: (question: string) => void;
  onQuery: () => void;
  onQueryRag: () => void;
  onSelectView: (view: ViewId) => void;
  onTopKChange: (topK: number) => void;
  question: string;
  ragResult: ApiRagAnswerResponse | null;
  result: ApiResearchMemoryQueryResponse | null;
  topK: number;
}) {
  const queryBusy = isQuerying || isRagQuerying;
  const canQuery = apiStatus === "online" && !queryBusy && question.trim().length > 0;
  const memoryHits = result?.hits ?? [];
  const memoryEvidenceBoundary = buildMemoryEvidenceBoundary(memoryHits);
  const memoryUnavailable = result?.reliability_status === "no_reliable_hit" || result?.reliability_status === "no_memory";
  const memoryUnavailableTitle =
    result?.reliability_status === "no_memory" ? "当前项目还没有可检索的论文记忆" : "当前记忆没有可靠证据回答此问题";

  return (
    <div className="memory-stack">
      <section className="memory-control-panel" aria-label="paper memory query">
        <div className="memory-control-header">
          <div>
            <p className="section-kicker">Paper Memory Bank</p>
            <h2>原文证据与结构化记忆问答</h2>
          </div>
          <div className="memory-query-actions">
            <button className="primary-command" disabled={!canQuery} type="button" onClick={onQueryRag}>
              <ShieldCheck size={17} />
              {isRagQuerying ? "核对原文中" : "检索原文并回答"}
            </button>
            <button className="secondary-command" disabled={!canQuery} type="button" onClick={onQuery}>
              <BrainCircuit size={17} />
              {isQuerying ? "检索记忆中" : "检索记忆并回答"}
            </button>
          </div>
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
          <span>原文 RAG：chunk + citation</span>
          <span>Paper Memory：Paper Card + ResearchSight</span>
          <span>无可靠证据则拒答</span>
        </div>
        {queryBusy ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}
      </section>

      <RagAnswerPanel result={ragResult} />

      {result && memoryUnavailable ? (
        <section className="memory-empty-state" aria-label="memory reliability boundary">
          <AlertTriangle size={22} />
          <div>
            <p className="section-kicker">Memory evidence boundary</p>
            <h2>{memoryUnavailableTitle}</h2>
            <p>
              {result.reliability_reason || "当前候选没有达到可靠命中门槛。"}
              系统没有将零分或弱相关论文包装成答案。
            </p>
            <ul>
              <li>重新检索包含任务对象和失败模式的更具体方向词。</li>
              <li>为关键论文上传 PDF，补齐 claim、dataset、metric、baseline 与原文片段。</li>
            </ul>
            <div className="memory-empty-actions">
              <button
                className="secondary-command"
                type="button"
                onClick={() => onQuestionChange(buildMemoryRewriteSuggestion(direction, question))}
              >
                <Sparkles size={15} />
                改写查询
              </button>
              <button className="secondary-command" type="button" onClick={() => onSelectView("paper-table")}>
                <Search size={15} />
                返回 Literature Search
              </button>
            </div>
            <ResearchWarningPanel title="拒答依据" warnings={result.warnings} />
          </div>
        </section>
      ) : null}

      {result && !memoryUnavailable ? (
        <>
          <section className="memory-answer-panel" aria-label="memory answer">
            <div className="memory-answer-header">
              <div>
                <p className="section-kicker">Memory-Grounded Answer</p>
                <h2>
                  {result.question}
                  {memoryEvidenceBoundary ? " · 摘要级证据，不是全文结论" : ""}
                </h2>
              </div>
              <div className="memory-stat-grid">
                <span title="当前方向下已保存的论文记忆数。">已保存记忆 {result.total_memories}</span>
                <span title="实际达到可靠命中门槛的论文数。">可靠命中 {memoryHits.length}</span>
                <span title="本次请求的最大返回数。">请求 top {result.top_k}</span>
              </div>
            </div>
            <p className="memory-answer-summary">{result.answer_summary || result.answer}</p>
            {result.claims?.length ? (
              <div className="memory-claim-list" aria-label="memory synthesized claims">
                {result.claims.map((claim) => (
                  <article key={claim.id}>
                    <div>
                      <strong>{claim.support_status === "corroborated" ? "多篇支持" : "单篇证据"}</strong>
                      <span className={`confidence ${claim.confidence}`}>{claim.confidence}</span>
                    </div>
                    <p>{claim.statement}</p>
                    <small>
                      {claim.evidence_refs
                        .map((reference) =>
                          [
                            reference.paper_id,
                            reference.source,
                            reference.section,
                            reference.page ? `p.${reference.page}` : "",
                          ]
                            .filter(Boolean)
                            .join(" · "),
                        )
                        .join(" / ")}
                    </small>
                  </article>
                ))}
              </div>
            ) : null}
            {result.unanswered_parts?.length ? (
              <div className="memory-unanswered" aria-label="memory unanswered parts">
                <strong>当前证据仍不能回答</strong>
                <ul>
                  {result.unanswered_parts.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {memoryEvidenceBoundary ? (
              <div className="partial-review-banner">
                <AlertTriangle size={18} />
                <div>
                  <strong>{memoryEvidenceBoundary.title}</strong>
                  <p>{memoryEvidenceBoundary.message}</p>
                </div>
              </div>
            ) : null}
            {result.direction_memory ? (
              <div className="memory-direction-box">
                <strong>{result.direction_memory.direction}</strong>
                <span>{result.direction_memory.summary}</span>
                {result.direction_memory.baseline_map ? (
                  <small>
                    BaselineMap：
                    {(result.direction_memory.baseline_map.recent_strong_baselines ?? [])
                      .slice(0, 2)
                      .map((reference) => reference.title)
                      .join(" / ") || "暂无强参照"}
                  </small>
                ) : null}
              </div>
            ) : null}
            <ResearchWarningPanel title="Memory 状态" warnings={result.warnings} />
          </section>

          <section className="memory-hit-list" aria-label="retrieved paper memories">
            {memoryHits.map((hit, index) => {
              const sight = normalizeResearchSight(hit.research_sight);
              const pack = normalizeEvidencePack(sight.evidence_pack);
              return (
                <article className="memory-hit-card" key={`${hit.paper?.id ?? "memory-hit"}-${index}`}>
                  <div className="memory-hit-header">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{(hit.score ?? 0).toFixed(2)}</strong>
                    {hit.self_read_priority ? <small>推荐精读</small> : null}
                  </div>
                  <h3>{hit.paper?.title ?? "Untitled memory"}</h3>
                  <div className="memory-hit-meta">
                    <span>Round {hit.round ?? 0}</span>
                    <span>{hit.paper?.year || "year unknown"}</span>
                    <span>{hit.paper?.venue || hit.paper?.source || "source unknown"}</span>
                  </div>
                  <details className="memory-hit-details">
                    <summary>查看证据、评分与研究备注</summary>
                    <div className="memory-hit-score-grid" aria-label="memory score breakdown">
                      <span>title {(hit.title_score ?? 0).toFixed(2)}</span>
                      <span>keyword {(hit.keyword_score ?? 0).toFixed(2)}</span>
                      <span>section {(hit.section_score ?? 0).toFixed(2)}</span>
                      <span>priority {(hit.priority_score ?? 0).toFixed(2)}</span>
                    </div>
                    <div className="memory-hit-evidence" data-testid="memory-hit-evidence">
                      <strong>命中理由</strong>
                      <span>{hit.paper?.relation || "标题、关键词或结构化字段与当前问题存在直接交集。"}</span>
                      <small>{formatEvidenceLevel(pack.evidence_level || hit.evidence_quality || "metadata_only")}</small>
                    </div>
                    <p>{hit.snippets?.[0] ?? "暂无命中片段。"}</p>
                    <dl>
                      <div>
                        <dt>最脆弱假设</dt>
                        <dd>{hit.weakest_assumption || "暂无"}</dd>
                      </div>
                      <div>
                        <dt>一周验证</dt>
                        <dd>{hit.minimal_reproduction || "暂无"}</dd>
                      </div>
                      <div>
                        <dt>反例设计</dt>
                        <dd>{hit.counterexample || "暂无"}</dd>
                      </div>
                      <div>
                        <dt>审美批判</dt>
                        <dd>{sight.why_not_good || "暂无 ResearchSight 批判字段"}</dd>
                      </div>
                      <div>
                        <dt>更好角度</dt>
                        <dd>{sight.better_angle || "暂无 ResearchSight 破局视角"}</dd>
                      </div>
                      <div>
                        <dt>证据等级</dt>
                        <dd>
                          {buildEvidenceBoundary(pack.evidence_level)?.title
                            ? `${buildEvidenceBoundary(pack.evidence_level)?.title}；`
                            : ""}
                          {pack.grounding_summary || "暂无 EvidencePack"}
                        </dd>
                      </div>
                    </dl>
                  </details>
                </article>
              );
            })}
          </section>
        </>
      ) : null}

      {!result && !ragResult ? (
        <section className="memory-empty-state">
          <BrainCircuit size={22} />
          <div>
            <h2>先检索论文，再选择问答方式</h2>
            <p>
              原文 RAG 可以直接查询已索引的摘要或 PDF chunk；结构化记忆需要先执行方向精读，
              再从 Paper Card、ResearchSight 和 direction memory 中召回。
            </p>
          </div>
        </section>
      ) : null}
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

export function GapBoardView({
  apiMessage,
  apiStatus,
  decision,
  goal,
  isGenerating,
  onGenerate,
  onGoalChange,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  decision: ApiResearchDecisionResponse | null;
  goal: string;
  isGenerating: boolean;
  onGenerate: () => void;
  onGoalChange: (goal: string) => void;
}) {
  const gaps = decision?.gaps ?? [];
  const decisionStatus = decision?.decision_status ?? "complete";
  const evidenceQuality = decision?.evidence_quality ?? {};
  const gapEvidenceCount = Number(evidenceQuality.gap_evidence_paper_count ?? 0);
  const evidenceThreshold = Number(evidenceQuality.minimum_gap_evidence_threshold ?? 5);
  const decisionEvidenceBoundary = buildDecisionEvidenceBoundary(decision);
  const isConservative = Boolean(decision && (decisionStatus !== "complete" || decisionEvidenceBoundary));

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
        {decision?.decision_intent ? (
          <div className="decision-intent-summary" aria-label="parsed decision intent">
            <strong>系统识别的目标约束</strong>
            <span>研究类型：{decision.decision_intent.contribution_type}</span>
            <span>
              目标关键词（锚点至少命中一项）：{decision.decision_intent.required_terms.join(" / ") || "未指定"}
            </span>
            <span>
              对照对象：{decision.decision_intent.contrast_terms.join(" / ") || "未指定"}
            </span>
            <span>
              明确排除：{decision.decision_intent.excluded_terms.join(" / ") || "无"}
            </span>
            <span>
              时间预算：
              {decision.decision_intent.time_budget_days
                ? `${decision.decision_intent.time_budget_days} 天`
                : "未指定，不自动假设 7 天"}
            </span>
          </div>
        ) : null}
        {isGenerating ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}
        {decision ? (
          <div className="validation-summary">
            <strong>Idea Validation · {decisionStatus}</strong>
            <p>{decision.validation.idea}</p>
            <span className={`risk ${decision.validation.novelty_risk}`}>{decision.validation.novelty_risk}</span>
            <span>{decision.validation.feasibility}</span>
            <span>
              gap evidence {gapEvidenceCount}/{evidenceThreshold}
            </span>
          </div>
        ) : null}
      </section>

      {isConservative ? (
        <section className="partial-review-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>{decisionEvidenceBoundary?.title ?? `Gap Board · ${decisionStatus}`}</strong>
            <p>
              {decisionEvidenceBoundary?.message ??
                "上游证据不足，Idea Validation 已降级为保守版本；当前不可把 gap 当作确定性科研结论。"}
            </p>
          </div>
        </section>
      ) : null}

      {decision?.warnings?.length ? (
        <ResearchWarningPanel title="Gap Board 证据状态" warnings={decision.warnings} />
      ) : null}

      {!decision ? (
        <section className="empty-state">
          <h2>尚未生成 Gap Board</h2>
          <p>请先点击生成研究决策。系统会基于当前项目的真实 paper table 和 paper card 生成 gap，不会填充演示卡片。</p>
        </section>
      ) : null}

      {decision && gaps.length === 0 ? (
        <section className="empty-state">
          <h2>当前没有可展示 gap</h2>
          <p>后端没有返回 gap。请先检索论文并生成 Paper Card，再重新生成研究决策。</p>
        </section>
      ) : null}

      {gaps.length ? (
        <div className="gap-board">
          {gaps.map((gap) => (
            <article className="gap-card" key={gap.id}>
              <div className="gap-card-header">
                <h2>{gap.title}</h2>
                <span className={`risk ${gap.novelty_risk}`}>{gap.novelty_risk}</span>
              </div>
              <div className={`gap-kind ${gap.kind}`}>{gap.kind}</div>
              {isConservative ? (
                <p className="gap-conservative-note">保守候选：先补齐原文证据并复核相邻工作，再决定是否投入实验。</p>
              ) : null}
              <dl>
                <div>
                  <dt>Evidence</dt>
                  <dd>{isConservative ? `保守提示：当前不是确定科研结论。${gap.evidence}` : gap.evidence}</dd>
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
      ) : null}
    </div>
  );
}

export function ExperimentPlannerView({
  apiMessage,
  apiStatus,
  decision,
  goal,
  isGenerating,
  onGenerate,
  onGoalChange,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  decision: ApiResearchDecisionResponse | null;
  goal: string;
  isGenerating: boolean;
  onGenerate: () => void;
  onGoalChange: (goal: string) => void;
}) {
  const plan = decision?.experiment;
  const isBlocked = plan?.status === "blocked";
  const decisionEvidenceBoundary = buildDecisionEvidenceBoundary(decision);

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
        {isGenerating ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}
      </section>

      {!decision ? (
        <section className="empty-state">
          <h2>尚未生成实验计划</h2>
          <p>请先点击生成实验计划。系统会检查是否存在可复现 anchor；没有 anchor 时不会生成伪计划。</p>
        </section>
      ) : null}

      {decisionEvidenceBoundary ? (
        <section className="partial-review-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>{decisionEvidenceBoundary.title}</strong>
            <p>{decisionEvidenceBoundary.message}</p>
          </div>
        </section>
      ) : null}

      {decision?.warnings?.length ? (
        <ResearchWarningPanel title="Experiment Plan 证据状态" warnings={decision.warnings} />
      ) : null}

      {plan && isBlocked ? (
        <section className="experiment-blocked-banner" role="status" aria-label="experiment blocked reason">
          <AlertTriangle size={18} />
          <div>
            <strong>实验计划已阻塞，不会生成伪计划</strong>
            <p>
              {plan.anchor_paper_title
                ? `锚点论文：${plan.anchor_paper_title}。`
                : "当前没有满足 claim + dataset + metric + baseline 的可验证锚点论文。"}
              {plan.unblock_suggestions[0] ? ` 下一步：${plan.unblock_suggestions[0]}` : " 下一步：上传关键论文 PDF 并重新生成 Paper Card。"}
            </p>
          </div>
        </section>
      ) : null}

      {plan ? (
        <section className={`experiment-detail ${isBlocked ? "blocked" : "ready"}`}>
          <h2>{plan.claim || (isBlocked ? "当前证据不足，无法形成可执行 claim" : "实验 claim 待补充")}</h2>
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
          {plan.goal_alignment ? (
            <div className="experiment-readiness" aria-label="experiment goal alignment">
              <strong>目标对齐</strong>
              <dl>
                {Object.entries(plan.goal_alignment).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{formatDecisionValue(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
          {plan.readiness_checks ? (
            <div className="experiment-readiness" aria-label="experiment readiness checks">
              <strong>执行前就绪检查</strong>
              <dl>
                {Object.entries(plan.readiness_checks).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd className={value.startsWith("unknown:") ? "unknown" : "ready"}>{value}</dd>
                  </div>
                ))}
              </dl>
              {plan.assumptions?.length ? (
                <>
                  <strong>尚未验证的假设</strong>
                  <ul>
                    {plan.assumptions.map((assumption) => (
                      <li key={assumption}>{assumption}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}
          {isBlocked && plan.unblock_suggestions.length ? (
            <div className="experiment-unblock">
              <strong>Unblock Suggestions</strong>
              <ul>
                {plan.unblock_suggestions.map((suggestion) => (
                  <li key={suggestion}>{suggestion}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>

      ) : null}

      {plan && !isBlocked ? (
        <div className="experiment-list">
          {plan.timeline.map((step, index) => {
            const isFinalStep = index === plan.timeline.length - 1;
            const item = {
              week: `Step ${index + 1}`,
              goal: step,
              deliverable: isFinalStep ? plan.success_criterion : experimentStepDeliverable(index),
              cost: index === 0 ? "setup" : isFinalStep ? "report" : "tracked",
            };
            return (
              <section className="experiment-row" key={item.week}>
                <div className="experiment-date">{item.week}</div>
                <div>
                  <h2>{item.goal}</h2>
                  <p>{item.deliverable}</p>
                </div>
                <span>{item.cost}</span>
              </section>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function formatDecisionValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length ? value.map(String).join(" / ") : "无";
  }
  if (value === null || value === undefined || value === "") {
    return "未指定";
  }
  return String(value);
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

function OperationStatusNote({ apiStatus, message }: { apiStatus: ApiStatus; message: string }) {
  return (
    <div className={`project-status-note operation-note ${apiStatus}`}>
      <Clock3 size={18} />
      <span>{message}</span>
    </div>
  );
}

function warningPreview(warnings: string[], limit: number) {
  const visible = warnings.slice(0, limit);
  const suffix = warnings.length > limit ? ` / 另有 ${warnings.length - limit} 条已折叠` : "";
  return `${visible.join(" / ")}${suffix}`;
}

function ResearchWarningPanel({
  className = "",
  fallback = "",
  title,
  warnings,
}: {
  className?: string;
  fallback?: string;
  title: string;
  warnings: string[];
}) {
  const { actionable, technical } = classifyResearchWarnings(warnings);
  const details = [...actionable.slice(1), ...technical];
  const summary = actionable.length
    ? `${actionable[0]}${actionable.length > 1 ? ` 另有 ${actionable.length - 1} 条可行动提示已归入详情。` : ""}`
    : technical.length
      ? "当前步骤返回了技术诊断；请查看详情，并在必要时重试或补充本地 PDF。"
      : fallback;
  if (!summary && technical.length === 0) {
    return null;
  }
  return (
    <section
      className={`research-warning-panel ${warnings.length === 0 ? "no-warnings" : ""} ${className}`.trim()}
      role="status"
    >
      <AlertTriangle size={17} />
      <div>
        <strong>{title}</strong>
        {summary ? <p>{summary}</p> : null}
        {details.length ? (
          <details className="research-warning-details">
            <summary>查看技术详情</summary>
            <ul>
              {details.map((warning, index) => (
                <li key={`${warning}-${index}`}>{warning}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </section>
  );
}

function classifyResearchWarnings(warnings: string[]): { actionable: string[]; technical: string[] } {
  const actionable: string[] = [];
  const technical: string[] = [];
  for (const warning of [...new Set(warnings.map((item) => item.trim()).filter(Boolean))]) {
    const lower = warning.toLowerCase();
    if (lower.includes("certificate_verify_failed") || lower.includes("ssl:")) {
      actionable.push("自动获取 PDF 暂不可用；可上传本地 PDF 继续全文级阅读。");
      technical.push(warning);
      continue;
    }
    if (lower.includes("429") || lower.includes("503") || lower.includes("504") || lower.includes("timeout")) {
      actionable.push("外部检索源暂时限流或超时；结果可能不完整，可稍后重试或缩小关键词范围。");
      technical.push(warning);
      continue;
    }
    if (lower.includes("relevance_coverage")) {
      actionable.push("系统已过滤弱相关和离题候选；请结合覆盖指标核对当前结果。");
      technical.push(warning);
      continue;
    }
    if (lower.includes("arxiv") || lower.includes("openalex") || lower.includes("cached") || lower.includes("query_relaxed")) {
      actionable.push("检索使用了降级、缓存或放宽后的候选；请优先核验结果相关性。");
      technical.push(warning);
      continue;
    }
    if (lower.includes("gap evidence")) {
      actionable.push("Gap 证据不足，当前结论保持保守；请先补充强/中相关且非综述的论文。");
      technical.push(warning);
      continue;
    }
    if (lower.includes("缺少绑定真实论文")) {
      actionable.push("缺少绑定真实论文的 Paper Card；请先生成卡片或上传全文证据。");
      technical.push(warning);
      continue;
    }
    if (
      lower.startsWith("先运行") ||
      lower.startsWith("先为") ||
      lower.startsWith("缺 dataset") ||
      lower.startsWith("缺 baseline") ||
      lower.startsWith("缺 metric")
    ) {
      actionable.push(warning);
      continue;
    }
    if (lower.includes("partial") || lower.includes("blocked") || lower.includes("low_recall")) {
      actionable.push(warning);
      continue;
    }
    technical.push(warning);
  }
  return {
    actionable: [...new Set(actionable)],
    technical,
  };
}

function summarizeWorkflowNotice(message: string): string {
  const { actionable, technical } = classifyResearchWarnings([message]);
  if (actionable.length) {
    return actionable[0];
  }
  if (technical.length) {
    return "当前步骤包含技术诊断；请在页面内展开详情后决定是否重试。";
  }
  return message;
}

function isSupersededFullTextNotice(message: string): boolean {
  const normalized = message.toLowerCase();
  const mentionsPdfAcquisition =
    normalized.includes("pdf") ||
    normalized.includes("certificate_verify_failed") ||
    normalized.includes("ssl");
  const mentionsFailure =
    normalized.includes("失败") ||
    normalized.includes("failed") ||
    normalized.includes("download") ||
    normalized.includes("not_available");
  return mentionsPdfAcquisition && mentionsFailure;
}

function escapeCsvCell(value: string | number | null | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function slugify(value: string) {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "scholarflow";
}

function isDemoProject(project: Pick<ApiProject, "id" | "workflow" | "stage" | "is_demo"> | null | undefined) {
  return Boolean(
    project?.is_demo ||
      project?.id === "local-bootstrap" ||
      project?.workflow === "demo-preview" ||
      project?.stage === "seed" ||
      project?.stage === "demo",
  );
}

function getDirectionArtifactRefs(review: ApiDirectionReviewResponse | null): ApiArtifactRef[] {
  if (!review) {
    return [];
  }
  if (review.artifact_refs?.length) {
    return review.artifact_refs;
  }
  return (review.artifacts ?? []).map((artifact) => ({
    id: artifact.id,
    title: artifact.title,
    kind: artifact.kind,
    created_at: artifact.created_at,
  }));
}

function formatArtifactDate(value: string) {
  if (!value) {
    return "unknown time";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function experimentStepDeliverable(index: number) {
  const deliverables = [
    "复核 anchor 字段和实验前置条件",
    "样本子集、baseline 运行记录",
    "按指标整理初步结果表",
    "失败切片和反例样本清单",
    "ablation 记录与错误分析",
    "复现实验报告草稿",
  ];
  return deliverables[index] ?? "当天结果、阻塞项与下一步记录";
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

export function ArtifactPreview({
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
        <span>{lastSavedArtifact ? `当前来源: ${lastSavedArtifact.id}` : "当前来源: 等待后端 artifact"}</span>
      </div>

      <textarea
        className="artifact-editor"
        value={content}
        onChange={(event) => updateArtifactField(activeTab, event.target.value)}
      />
    </aside>
  );
}
