import { type ReactNode, type Ref, useEffect, useState } from "react";
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
  type ApiDirectionReviewRunStatusResponse,
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
} from "../../mockData";
import { RagAnswerPanel } from "../../components/RagAnswerPanel";
import { isRetrievalWarning } from "../../apiClient";
import {
  normalizeEvidencePack,
  normalizeResearchSight,
  resolvePaperCardForPaper,
  toPlanStatus,
} from "../../lib/artifactHydration";
import type { PaperCardMatchSource } from "../../lib/artifactHydration";
import type {
  ApiStatus,
  ArtifactTab,
  ProjectDraft,
  WorkflowActions,
  WorkflowNotice,
  WorkflowStepStatus,
  WorkflowViewModel,
} from "../../types/workflow";
import {
  formatAcademicText,
  formatEvidenceLevel,
  formatResearchSignal,
  formatSignalEvidenceLocation,
} from "./formatters";
import { formatContributionType } from "./decisionFormatters";

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

export const PROJECT_DRAFT_STORAGE_KEY = "scholarflow.projectDraft";

export function WorkflowShell({
  activeView,
  actions,
  ariaLabel,
  children,
  mainRef,
  onSelectView,
  viewModel,
}: {
  activeView: ViewId;
  actions: WorkflowActions;
  ariaLabel: string;
  children: ReactNode;
  mainRef: Ref<HTMLElement>;
  onSelectView: (view: ViewId) => void;
  viewModel: WorkflowViewModel;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window === "undefined" ? true : window.innerWidth > 860,
  );
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const verifiedReaderCard =
    activeView === "paper-reader" &&
    viewModel.latestPaperCard?.evidence_qualification?.level === "full_text" &&
    viewModel.latestPaperCard.evidence_qualification.verified;
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
              ? `${viewModel.activeProject.field || "General research"} · ${formatProjectStage(viewModel.activeProject.stage)}`
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

      <main className="workflow-main" aria-label={ariaLabel} ref={mainRef}>
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

export function ConferenceLogoBelt({ withTitle = true }: { withTitle?: boolean }) {
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
  const evidenceQualification = displayCard?.evidence_qualification;
  const readerTitle = formatReaderTitle(evidenceLevel, Boolean(displayCard));
  const evidenceBoundary = buildEvidenceBoundary(evidenceLevel);
  const missingEvidence = buildMissingEvidenceChecklist(displayCard);
  const decisionBrief = buildPaperDecisionBrief(displayCard);
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
    const normalized = formatResearchSignal(value, "");
    if (!normalized) {
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
              {evidenceQualification?.level === "full_text" && evidenceQualification.verified ? (
                <span>
                  {evidenceQualification.page_count} 页 / {evidenceQualification.character_count.toLocaleString("zh-CN")} 字符
                </span>
              ) : null}
              {evidenceQualification?.reason ? <span>{evidenceQualification.reason}</span> : null}
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

          {displayCard ? (
            <section
              className="paper-decision-brief"
              aria-label="paper research decision brief"
              data-testid="paper-research-decision-brief"
            >
              <header>
                <div>
                  <p className="section-kicker">Research decision brief</p>
                  <h2>先判断这篇论文是否值得继续投入</h2>
                </div>
                <span data-readiness={decisionBrief.readiness}>{decisionBrief.label}</span>
              </header>
              <div className="paper-decision-grid">
                {decisionBrief.items.map((item) => (
                  <article key={item.label}>
                    <div className="paper-decision-field-head">
                      <span>{item.label}</span>
                      <small data-source={item.sourceStatus}>{item.sourceLabel}</small>
                    </div>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>
              <div className="paper-decision-next">
                <Target size={17} />
                <div>
                  <strong>建议下一步</strong>
                  <p>{decisionBrief.nextAction}</p>
                </div>
              </div>
              {decisionBrief.evidence.length ? (
                <details className="paper-decision-evidence">
                  <summary>查看任务、方法与主张的原文定位</summary>
                  <dl>
                    {decisionBrief.evidence.map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.location}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              ) : null}
            </section>
          ) : null}

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
                      {activeSectionParagraphs.length ? (
                        activeSectionParagraphs.map((paragraph, index) => (
                          <p key={`${activeSection.id}-paragraph-${index}`}>{paragraph}</p>
                        ))
                      ) : (
                        <div className="paper-reader-section-empty" role="status">
                          <strong>本段暂无可定位内容</strong>
                          <span>所需字段已汇总在上方“待补证据与核验清单”。</span>
                        </div>
                      )}
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
              <h2>科研字段（自动抽取）</h2>
              <span>{signals ? "已生成" : "暂无"}</span>
            </div>
            {signals ? (
              <div className="signal-chip-grid">
                {[
                  ["task", "研究任务", signals.task],
                  ["method", "核心方法", signals.method],
                  ["dataset", "数据集", signals.dataset],
                  ["metric", "评估指标", signals.metric],
                  ["baseline", "对比基线", signals.baseline],
                  ["claim", "主要主张", signals.claim],
                  ["limitation", "论文局限", signals.limitation],
                ].map(([field, label, value], index) => {
                  const source = classifySignalEvidence(signals.signal_evidence?.[field]);
                  return (
                    <article className={`signal-chip tone-${index}`} key={field}>
                      <div>
                        <strong>{label}</strong>
                        <small data-source={source.status}>{source.label}</small>
                      </div>
                      <span>{formatResearchSignal(value, "未定位")}</span>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="reader-empty-state compact">
                <FileText size={19} />
                <div>
                  <h3>暂无科研字段</h3>
                  <p>生成 Paper Card 后才会显示研究任务、方法、数据集、指标、基线和主要主张。</p>
                </div>
              </div>
            )}
          </section>
        </aside>
      </section>
    </div>
  );
}

function classifySignalEvidence(
  evidence: ApiSignalEvidence | undefined,
): { label: string; status: "full_text" | "supplemental_text" | "abstract_only" | "missing" | "invalid" } {
  if (!evidence || evidence.availability === "missing") {
    return { label: "缺失", status: "missing" };
  }
  if (evidence.availability === "invalid" || evidence.validation_errors.length > 0) {
    return { label: "异常", status: "invalid" };
  }
  const refs = evidence.evidence_refs?.length ? evidence.evidence_refs : [evidence];
  const allFullText = refs.every(
    (ref) => ref.source === "pdf.full_text" && ref.validation_errors.length === 0,
  );
  if (allFullText && evidence.availability !== "partial") {
    return { label: "全文", status: "full_text" };
  }
  if (refs.some((ref) => ref.source === "user.supplemental_text")) {
    return { label: "补充文本", status: "supplemental_text" };
  }
  return { label: "摘要", status: "abstract_only" };
}

function PaperSignalDetail({
  evidence,
  label,
  value,
}: {
  evidence: ApiSignalEvidence | undefined;
  label: string;
  value: string | undefined;
}) {
  const source = classifySignalEvidence(evidence);
  return (
    <div className="paper-signal-detail">
      <div className="paper-signal-field-head">
        <strong>{label}</strong>
        <small data-source={source.status}>{source.label}</small>
      </div>
      <span>{formatResearchSignal(value, "未定位")}</span>
      <small className="critique-evidence-note">{formatSignalEvidenceLocation(evidence)}</small>
    </div>
  );
}

function buildPaperDecisionBrief(card: ApiPaperCard | null): {
  readiness: "ready" | "partial" | "blocked";
  label: string;
  items: Array<{
    label: string;
    value: string;
    sourceLabel: string;
    sourceStatus: "full_text" | "supplemental_text" | "abstract_only" | "missing" | "invalid";
  }>;
  nextAction: string;
  evidence: Array<{ label: string; location: string }>;
} {
  const signals = card?.signals;
  const useful = (value: string | undefined, fallback: string) => {
    return formatResearchSignal(value, fallback);
  };
  const coreEvidence = [
    signals?.signal_evidence?.task,
    signals?.signal_evidence?.method,
    signals?.signal_evidence?.claim,
  ];
  const coreSignalsPresent = Boolean(
    signals && useful(signals.task, "") && useful(signals.method, "") && useful(signals.claim, ""),
  );
  const coreEvidenceStatuses = coreEvidence.map((evidence) => classifySignalEvidence(evidence).status);
  const coreSignalsVerified = coreEvidenceStatuses.every((status) => status === "full_text");
  const cardHasVerifiedFullText =
    card?.evidence_qualification?.level === "full_text" &&
    card.evidence_qualification.verified;
  const readiness =
    cardHasVerifiedFullText && coreSignalsPresent && coreSignalsVerified
      ? "ready"
      : coreSignalsPresent || card?.evidence_level === "abstract_only"
        ? "partial"
        : "blocked";
  const label =
    readiness === "ready"
      ? "可进入人工核验"
      : readiness === "partial"
        ? "仅作选读线索"
        : "证据不足";
  const nextAction =
    readiness === "ready"
      ? useful(
          card?.minimal_reproduction,
          "先回到 PDF 核对方法、实验设置和失败案例，再决定是否进入复现。",
        )
      : cardHasVerifiedFullText
        ? "卡片已绑定全文，但任务、方法或主要主张仍有字段缺少全文定位；请先核对对应 PDF 段落，再决定是否进入复现。"
      : "上传或绑定论文 PDF，重点补齐方法、实验设置、baseline、ablation 与失败案例后重新生成。";
  const evidenceFields: Array<[string, ApiSignalEvidence | undefined]> = [
    ["研究任务", signals?.signal_evidence?.task],
    ["核心方法", signals?.signal_evidence?.method],
    ["主要主张", signals?.signal_evidence?.claim],
  ];
  return {
    readiness,
    label,
    items: [
      {
        label: "研究任务",
        value: useful(signals?.task, "尚未定位到明确、可检验的研究任务。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.task).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.task).status,
      },
      {
        label: "核心方法",
        value: useful(signals?.method, "尚未定位到具体方法机制。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.method).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.method).status,
      },
      {
        label: "主要主张",
        value: useful(signals?.claim, "尚未定位到论文的主要经验主张。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.claim).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.claim).status,
      },
    ],
    nextAction,
    evidence: evidenceFields.flatMap(([field, evidence]) =>
      evidence
        ? [{ label: field, location: formatSignalEvidenceLocation(evidence) }]
        : [],
    ),
  };
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
  if (evidenceLevel === "supplemental_text") {
    return "补充文本辅助阅读 · Paper Card";
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
    return "用户补充文本，未通过 PDF 验证";
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
    evidence_qualification: card.evidence_qualification ?? reading.evidence_qualification,
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

function evidenceRank(
  level: string | undefined,
  provenance?: ApiFullTextProvenance,
): number {
  const qualification = provenance?.evidence_qualification;
  if (qualification?.level === "full_text" && qualification.verified) {
    return 4;
  }
  if (qualification?.level === "supplemental_text" || level === "supplemental_text") {
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
  if (provenance.status === "supplemental_text") {
    return "用户补充文本，未通过 PDF 验证";
  }
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

  const qualification = provenance.evidence_qualification;
  const extracted = Boolean(
    qualification?.level === "full_text" && qualification.verified,
  );
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
            ? `已验证 PDF 全文 · ${provenance.page_count.toLocaleString("zh-CN")} 页 / ${provenance.character_count.toLocaleString("zh-CN")} 字符`
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

export function buildEvidenceBoundary(evidenceLevel: string | undefined): EvidenceBoundary | null {
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
      nextAction: "上传本地 PDF，系统会重新绑定当前论文并升级为已验证 PDF 全文。",
    };
  }
  if (evidenceLevel === "supplemental_text") {
    return {
      title: "用户补充文本，未通过 PDF 验证",
      message: "当前卡片可使用用户粘贴内容辅助阅读，但该内容没有经过 PDF 来源、页码、文本层和解析状态验证。",
      confirmed: "用户明确提供的文本内容，以及其中可直接看到的关键词和陈述。",
      cannotConfirm: "PDF 原文位置、完整上下文、全文级 claim、true gap 和实验 anchor。",
      nextAction: "上传带可复制文本层的 PDF；只有通过统一资格检查后才会升级为已验证 PDF 全文。",
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

export function buildMemoryEvidenceBoundary(
  hits: NonNullable<ApiResearchMemoryQueryResponse["hits"]>,
): { title: string; message: string } | null {
  if (!hits.length) {
    return null;
  }
  const levels = hits.map((hit) => normalizeEvidencePack(normalizeResearchSight(hit.research_sight).evidence_pack).evidence_level);
  const limitedCount = levels.filter(
    (level) =>
      level === "supplemental_text" ||
      level === "abstract_only" ||
      level === "metadata_only" ||
      level === "unknown",
  ).length;
  const fullTextCount = levels.filter((level) => level === "full_text").length;
  if (limitedCount > 0 && fullTextCount === 0) {
    return {
      title: "摘要级证据，不是全文结论",
      message: `当前 ${hits.length} 条 memory hit 主要来自摘要级或元数据级 Paper Card。回答可用于定位线索，但不能当作已经核验全文后的确定判断。`,
    };
  }
  return null;
}

export function buildMemoryRewriteSuggestion(direction: string, question: string): string {
  const topic = direction.trim() || question.trim() || "当前研究方向";
  return `${topic}：具体研究对象、失败模式、数据集、指标与 baseline 分别是什么？`;
}

export function buildDecisionEvidenceBoundary(
  decision: ApiResearchDecisionResponse | null,
): { title: string; message: string } | null {
  const quality = decision?.evidence_quality;
  if (!quality) {
    return null;
  }
  const abstractCount = Number(quality.abstract_only_card_count ?? 0);
  const supplementalCount = Number(quality.supplemental_text_card_count ?? 0);
  const metadataCount = Number(quality.metadata_only_card_count ?? 0);
  const fullTextCount = Number(quality.full_text_card_count ?? 0);
  const limitedCount = abstractCount + supplementalCount + metadataCount;
  if (limitedCount > 0 && fullTextCount === 0) {
    return {
      title: "摘要级证据，不是全文结论",
      message: `当前研究决策主要依赖 ${supplementalCount} 张未验证补充文本 card、${abstractCount} 张摘要级 card 和 ${metadataCount} 张元数据级 card。Gap、Idea Validation 和实验计划只能作为保守候选，不能视为已完成全文级论证。`,
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
  if (card.evidence_level === "supplemental_text") {
    checklist.push("用户补充文本未通过 PDF 来源、页码和解析验证");
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
    /^证据边界[（(](?:metadata_only|abstract_only|supplemental_text)[）)][:：][\s\S]*?(?=\n阅读提纲[:：])/,
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
  if (!content.trim()) {
    return [];
  }
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
  return paragraphs.length ? paragraphs : [];
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

export function WorkflowGuide({
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
      label: "Workflow Mode",
      value: ["agent-loop", "workflow-run"].includes(stage) ? "planning" : "ready",
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
          <p className="section-kicker">Workflow Runtime</p>
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

export function AgentRunPanel({
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
    ? "Demo 项目是只读 preview，不会执行真实 Research Workflow 工具链。请创建真实项目。"
    : apiStatus !== "online"
      ? "API 未连接。"
      : "";

  return (
    <section className="agent-run-panel" aria-label="research workflow run">
      <div className="agent-run-header">
        <div>
          <p className="section-kicker">Research Workflow Run</p>
          <h2>{agentPlan ? `Run ${agentPlan.run_id}` : "Research Workflow Task"}</h2>
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
          <div className="agent-run-progress" aria-label="model provider status">
            <strong>
              模型建议：
              {!agentPlan.model_call
                ? "Legacy record / 未保存模型审计"
                : agentPlan.model_call.response_status === "success"
                ? `${agentPlan.model_call.provider} / ${agentPlan.model_call.model}`
                : agentPlan.model_call.fallback_reason
                  ? `Local fallback / ${agentPlan.model_call.fallback_reason}`
                  : `${agentPlan.model_call.provider} / ${agentPlan.model_call.model}`}
            </strong>
            <span>
              执行模式：确定性工具图。模型不能修改工具、证据等级、拒答、科研状态或 Experiment readiness。
            </span>
            <span>
              {agentPlan.model_call?.external_data_sent
                ? `已向 ${agentPlan.model_call.requested_provider || agentPlan.model_call.provider} 发送任务与项目上下文。`
                : "未向外部模型发送数据。"}
            </span>
          </div>
          {agentRunStatus ? (
            <div className="agent-run-progress" aria-label="agent run progress">
              <strong>{agentRunStatus.run_status_summary || `Research Workflow Run ${agentRunStatus.status}`}</strong>
              <span aria-live="polite" data-testid="agent-run-current-tool">
                {agentRunStatus.status === "running"
                  ? `Timeline、artifacts 和 workflow steps 正在刷新${agentRunStatus.current_tool ? `；当前工具：${agentRunStatus.current_tool}` : ""}`
                  : `最终状态：${agentRunStatus.status}`}
              </span>
              <div className="agent-run-time-grid" aria-label="agent run timestamps">
                <span>排队：{formatArtifactDate(agentRunStatus.queued_at ?? "")}</span>
                <span>启动：{formatArtifactDate(agentRunStatus.started_at ?? "")}</span>
                <span>心跳：{formatArtifactDate(agentRunStatus.last_heartbeat ?? agentRunStatus.updated_at)}</span>
                {agentRunStatus.completed_at ? (
                  <span>完成：{formatArtifactDate(agentRunStatus.completed_at)}</span>
                ) : null}
              </div>
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
  if (typeof metrics.warning_count_unique === "number" && metrics.warning_count_unique > 0) {
    const rawCount =
      typeof metrics.warning_count_raw === "number"
        ? metrics.warning_count_raw
        : metrics.warning_count_unique;
    fragments.push(
      rawCount === metrics.warning_count_unique
        ? `${metrics.warning_count_unique} 条警告`
        : `${metrics.warning_count_unique} 类警告（原始 ${rawCount} 条）`,
    );
  } else if (typeof metrics.warning_count === "number" && metrics.warning_count > 0) {
    fragments.push(`${metrics.warning_count} 条警告`);
  }
  if (typeof metrics.round_read_count === "number") {
    fragments.push(`本轮可靠阅读 ${metrics.round_read_count} 篇`);
  } else if (typeof metrics.paper_count === "number") {
    fragments.push(`本步骤返回 ${metrics.paper_count} 篇`);
  }
  if (typeof metrics.total_read_count === "number") {
    fragments.push(`累计可靠阅读 ${metrics.total_read_count} 篇`);
  }
  if (typeof metrics.off_topic_count === "number" && metrics.off_topic_count > 0) {
    fragments.push(`过滤离题 ${metrics.off_topic_count} 篇`);
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
  run,
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
  run: ApiDirectionReviewRunStatusResponse | null;
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
  const fullTextCount = readings.filter(
    (reading) =>
      reading.evidence_qualification?.level === "full_text" &&
      reading.evidence_qualification.verified,
  ).length;
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

        {run ? (
          <section className="direction-run-progress" aria-label="direction review server progress">
            <div className="direction-run-progress-header">
              <div>
                <span>后端真实进度</span>
                <strong>{formatDirectionRunStage(run.stage)}</strong>
              </div>
              <em data-status={run.status}>{run.status}</em>
            </div>
            <progress max={100} value={run.progress} />
            <div className="direction-run-progress-meta">
              <span>{run.progress}%</span>
              <span>
                {run.current_tool
                  ? `当前阶段：${formatDirectionRunStage(run.current_tool as ApiDirectionReviewRunStatusResponse["stage"])}`
                  : "当前无执行中的阶段"}
              </span>
              <span>{run.message}</span>
              <time dateTime={run.updated_at}>{formatArtifactDate(run.updated_at)}</time>
            </div>
            {run.notices.length ? (
              <ul className="direction-run-notices" aria-label="direction review notices">
                {run.notices.slice(-3).map((notice) => (
                  <li data-severity={notice.severity} key={`${notice.code}-${notice.occurred_at}`}>
                    <strong>{notice.severity}</strong>
                    <span>{notice.message}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}

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
                <span>本轮可靠阅读</span>
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

const baselineCheckLabels: Record<string, string> = {
  full_text: "PDF 全文",
  supplemental_text: "用户补充文本",
  method: "方法证据",
  dataset: "数据集",
  metric: "指标",
  baseline: "对照方法",
  code: "代码仓库",
};

function formatBaselineVerificationValue(value: string): string {
  return (
    {
      ready: "已具备",
      partial: "部分具备",
      blocked: "阻塞",
      missing: "缺失",
      unverified: "未核验",
      not_checked: "未检查",
      link_present: "已发现链接",
      claimed_unverified: "仅有声明",
      not_found: "未发现",
      full_text: "PDF 全文",
      abstract_only: "仅摘要",
      metadata_only: "仅元数据",
    }[value] ?? value.replace(/_/g, " ")
  );
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
          <article
            data-testid={`baseline-reference-${reference.category}-${index}`}
            key={`${title}-${reference.title}-${reference.year}-${index}`}
          >
            <span>
              {reference.year || "year unknown"} · {reference.method_family || reference.category} ·{" "}
              {reference.confidence || "unknown"} confidence
            </span>
            <h4>{reference.title}</h4>
            <div className="baseline-action-row">
              <span>{reference.comparison_role || "candidate_reference"}</span>
              <strong data-status={reference.actionability_status ?? reference.verification?.reproduction_status ?? "blocked"}>
                {formatBaselineVerificationValue(
                  reference.actionability_status ?? reference.verification?.reproduction_status ?? "blocked",
                )}
              </strong>
            </div>
            <p>{reference.reason}</p>
            <small>{reference.evidence_gap}</small>
            {reference.next_action ? <p className="baseline-next-action">下一步：{reference.next_action}</p> : null}
            {reference.verification ? (
              <details
                className="baseline-verification"
                aria-label={`验证与复现条件：${reference.title}`}
              >
                <summary>
                  <span>验证与复现条件</span>
                  <strong data-status={reference.verification.reproduction_status}>
                    {formatBaselineVerificationValue(reference.verification.reproduction_status)}
                  </strong>
                </summary>
                <div className="baseline-verification-body">
                  <p>{reference.verification.summary}</p>
                  <dl>
                    {Object.entries(reference.verification.checks).map(([check, status]) => (
                      <div key={check}>
                        <dt>{baselineCheckLabels[check] ?? check}</dt>
                        <dd data-status={status}>{formatBaselineVerificationValue(status)}</dd>
                      </div>
                    ))}
                  </dl>
                  <p>
                    引用关系：{formatBaselineVerificationValue(reference.verification.citation_status)}。
                    {reference.verification.citation_note}
                  </p>
                  {reference.verification.code_url ? (
                    <p>
                      代码来源：{reference.verification.code_source || "unknown"} ·{" "}
                      <a href={reference.verification.code_url} rel="noreferrer" target="_blank">
                        打开代码仓库
                      </a>
                    </p>
                  ) : null}
                  {reference.verification.missing_evidence.length ? (
                    <p>仍缺少：{reference.verification.missing_evidence.join("、")}。</p>
                  ) : null}
                  {reference.experiment_anchor ? (
                    <dl className="baseline-experiment-anchor">
                      {Object.entries(reference.experiment_anchor)
                        .filter(([, value]) => Boolean(value))
                        .map(([field, value]) => (
                          <div key={field}>
                            <dt>{baselineCheckLabels[field] ?? field}</dt>
                            <dd>{value}</dd>
                          </div>
                        ))}
                    </dl>
                  ) : null}
                </div>
              </details>
            ) : null}
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
        <BaselineReferenceList title="近三年直接候选" references={baselineMap.recent_strong_baselines} />
        <BaselineReferenceList title="异质范式" references={baselineMap.alternative_paradigms} />
      </div>
      <div className="baseline-risk-grid">
        <div>
          <strong>执行顺序</strong>
          <span>{baselineMap.action_plan?.join("；") || "当前没有 reproduction-ready baseline，实验计划应保持 blocked/partial。"}</span>
        </div>
        <div>
          <strong>证据约束</strong>
          <span>{baselineMap.evidence_summary}</span>
        </div>
        <div>
          <strong>常见 benchmark</strong>
          <span>{baselineMap.common_benchmarks.slice(0, 5).join(" / ") || "尚未从候选论文中核验出稳定 benchmark"}</span>
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
              <strong>类型</strong>
              <span>{formatContributionType(signals.contribution_type || "")}</span>
            </div>
            <PaperSignalDetail evidence={signals.signal_evidence?.task} label="研究任务" value={signals.task} />
            <PaperSignalDetail evidence={signals.signal_evidence?.method} label="核心方法" value={signals.method} />
            <PaperSignalDetail evidence={signals.signal_evidence?.dataset} label="数据集" value={signals.dataset} />
            <PaperSignalDetail evidence={signals.signal_evidence?.metric} label="评估指标" value={signals.metric} />
            <PaperSignalDetail evidence={signals.signal_evidence?.baseline} label="对比基线" value={signals.baseline} />
            <PaperSignalDetail evidence={signals.signal_evidence?.claim} label="主要主张" value={signals.claim} />
            <PaperSignalDetail evidence={signals.signal_evidence?.limitation} label="论文局限" value={signals.limitation} />
            <PaperSignalDetail
              evidence={signals.signal_evidence?.prior_work_limitation}
              label="已有研究不足"
              value={signals.prior_work_limitation}
            />
            <div>
              <strong>未定位字段</strong>
              <span>{missingSignals.length ? missingSignals.join(", ") : "无"}</span>
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
            <p>{researchSight.why_good || "尚未形成可引用的正面评价。"}</p>
            {renderCritiqueEvidence("why_good")}
          </div>
          <div>
            <strong>为什么不好</strong>
            <p>{researchSight.why_not_good || "尚未形成可引用的局限评价。"}</p>
            {renderCritiqueEvidence("why_not_good")}
          </div>
          <div>
            <strong>更好角度</strong>
            <p>{researchSight.better_angle || "尚未形成论文专属的研究角度。"}</p>
            {renderCritiqueEvidence("better_angle")}
          </div>
          <div>
            <strong>Baseline 对比</strong>
            <p>{researchSight.baseline_comparison || "尚未定位到可复核的对照结论。"}</p>
            {renderCritiqueEvidence("baseline_comparison")}
          </div>
          <div>
            <strong>下一步 proposal</strong>
            <p>{researchSight.next_step_proposal || "尚未形成论文专属的下一步建议。"}</p>
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
                    {" · "}
                    {reading.full_text?.status === "extracted"
                      ? `PDF 全文 ${reading.full_text.page_count} 页`
                      : formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}
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

export function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

export function OperationStatusNote({ apiStatus, message }: { apiStatus: ApiStatus; message: string }) {
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

export function ResearchWarningPanel({
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
  const { actionable } = classifyResearchWarnings(warnings);
  const details = actionable.slice(1);
  const summary = actionable.length
    ? `${actionable[0]}${actionable.length > 1 ? ` 另有 ${actionable.length - 1} 条可行动提示已归入详情。` : ""}`
    : fallback;
  if (!summary) {
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
            <summary>查看诊断详情</summary>
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

export function escapeCsvCell(value: string | number | null | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

export function slugify(value: string) {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "scholarflow";
}

export function formatProjectStage(stage: string): string {
  return stage === "agent-loop" || stage === "workflow-run"
    ? "research-workflow"
    : stage;
}

export function isDemoProject(project: Pick<ApiProject, "id" | "workflow" | "stage" | "is_demo"> | null | undefined) {
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

function formatDirectionRunStage(stage: ApiDirectionReviewRunStatusResponse["stage"]): string {
  return {
    queued: "等待后端执行",
    scoping: "界定方向范围",
    retrieving: "检索与相关性筛选",
    reading: "获取 PDF 与结构化阅读",
    curating: "校准 BaselineMap 与 ResearchSight",
    persisting: "写入科研资产",
    completed: "运行结束",
    failed: "执行失败",
    cancelled: "已取消",
  }[stage];
}

export function formatResearchFacet(facet: string): string {
  return {
    dataset: "数据集 / benchmark",
    metric: "评测指标",
    failure_mode: "失败模式",
    baseline: "对照基线",
    method: "方法",
    claim: "主要结论",
  }[facet] ?? facet;
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

export function experimentStepDeliverable(index: number) {
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
