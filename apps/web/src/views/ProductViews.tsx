import { type ReactNode, useState } from "react";
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
  MoreHorizontal,
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
  Upload,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  SCHOLARFLOW_VERSION,
  type ApiAgentPlanResponse,
  type ApiAgentPlanStep,
  type ApiArtifact,
  type ApiArtifactRef,
  type ApiArtifactSummary,
  type ApiDirectionPaperReading,
  type ApiDirectionReviewResponse,
  type ApiEvidencePack,
  type ApiPaperCard,
  type ApiProject,
  type ApiResearchDecisionResponse,
  type ApiResearchMemoryQueryResponse,
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
import { isRetrievalWarning } from "../apiClient";
import { normalizeEvidencePack, normalizeResearchSight, toPlanStatus } from "../lib/artifactHydration";
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
  const latestNotice = viewModel.warnings[0] ?? null;
  const activeStep = viewModel.workflowSteps.find((step) => step.id === activeView);

  return (
    <div className="workflow-shell">
      <aside className="workflow-rail" aria-label="workflow steps">
        <button className="workflow-brand" type="button" onClick={() => onSelectView("dashboard")}>
          <span className="sf-logo small">SF</span>
          <span>
            <strong>ScholarFlow</strong>
            <small>Research Workspace</small>
          </span>
        </button>

        <label className="project-select-block">
          <span>项目</span>
          <select
            value={viewModel.activeProject?.id ?? ""}
            onChange={(event) => actions.onSelectProject(event.target.value)}
          >
            {!viewModel.projects.length ? <option value="">尚未创建项目</option> : null}
            {viewModel.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.id === "local-bootstrap" ? "Demo: " : ""}
                {project.title}
              </option>
            ))}
          </select>
        </label>

        <nav className="workflow-step-list">
          {viewModel.workflowSteps.map((step) => {
            const Icon = navIcons[step.id];
            const isActive = step.id === activeView || (activeView === "paper-reader" && step.id === "paper-reader");
            return (
              <button
                className={isActive ? "workflow-step active" : "workflow-step"}
                key={step.id}
                type="button"
                onClick={() => onSelectView(step.id)}
              >
                <Icon size={17} />
                <span>
                  <strong>{step.label}</strong>
                  <small>{step.summary}</small>
                </span>
                <StatusPill status={step.status} />
              </button>
            );
          })}
        </nav>
      </aside>

      <main className="workflow-main" aria-label={ariaLabel}>
        <header className="workflow-header">
          <div>
            <p className="section-kicker">Current Workspace</p>
            <h1>{viewModel.activeProject?.title ?? "尚未选择项目"}</h1>
            <span>{viewModel.activeProject?.workflow ?? "创建项目后开始真实科研工作流"}</span>
          </div>
          <div className="workflow-header-meta">
            <span className={`api-chip ${viewModel.apiStatus}`}>{viewModel.apiStatus}</span>
            <span>{viewModel.paperRows.length} papers</span>
            <span>{viewModel.artifactCount} artifacts</span>
            <button className="secondary-command compact" type="button" onClick={() => onSelectView("new-project")}>
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

      <aside className="workflow-inspector" aria-label="workflow artifacts and warnings">
        <WorkflowNoticeList notices={viewModel.warnings} />
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
  return <em className={`workflow-status ${status}`}>{status}</em>;
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
            <article className={`workflow-notice ${notice.kind}`} key={notice.id}>
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
    <section className="workflow-side-section">
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
  agentTask: string;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
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
  onLoadArtifact: (artifactId: string) => void;
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

export function ActiveView({
  activeProject,
  agentBusy,
  agentPlan,
  agentTask,
  apiMessage,
  apiStatus,
  artifactCount,
  artifactSummaries,
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
  onLoadArtifact,
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
            artifactSummaries={artifactSummaries}
            isGenerating={paperCardBusy}
            onGenerate={onGeneratePaperCard}
            onInputChange={onPaperCardInputChange}
            onLoadArtifact={onLoadArtifact}
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
            onRoundChange={onDirectionRoundChange}
            onSelectedPaperChange={onSelectedDirectionPaperChange}
            review={directionReview}
            round={directionRound}
            selectedPaperId={selectedDirectionPaperId}
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
            onQuestionChange={onMemoryQuestionChange}
            onQuery={onQueryResearchMemory}
            onTopKChange={onMemoryTopKChange}
            question={memoryQuestion}
            result={memoryResult}
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

export function ProductHomeView({
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
    <div className="dashboard-workbench">
      <section className="workbench-summary-panel">
        <div>
          <p className="section-kicker">Project Snapshot</p>
          <h2>{activeProject?.title ?? "先创建一个科研项目"}</h2>
          <p>
            {activeProject
              ? activeProject.description || "当前项目已经连接到本地 SQLite 工作区。"
              : "ScholarFlow 只展示真实项目状态。创建项目后，Paper Table、Direction Review、Paper Memory、Gap Board 和 Experiment Plan 才会逐步进入可用状态。"}
          </p>
        </div>
        <div className="workbench-action-row">
          <button className="secondary-command" type="button" onClick={() => onSelectView("new-project")}>
            <Plus size={17} />
            新建项目
          </button>
          <button
            className="secondary-command"
            disabled={!activeProject || apiStatus !== "online"}
            type="button"
            onClick={() => onSelectView("paper-table")}
          >
            <Search size={17} />
            进入 Paper Table
          </button>
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
        agentBusy={agentBusy}
        agentPlan={agentPlan}
        agentTask={agentTask}
        apiStatus={apiStatus}
        onAgentTaskChange={onAgentTaskChange}
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
            <button className="select-like" type="button">
              {draft.field || "Artificial Intelligence / Multimodal Learning"}
              <ChevronDown size={18} />
            </button>
          </label>
          <label>
            <span>工作流模板 <sup>*</sup></span>
            <button className="select-like" type="button">
              Survey → Deep Reading → Memory → Gap → Experiment
              <ChevronDown size={18} />
            </button>
          </label>
        </div>

        <div className="form-action-row">
          <button className="gradient-button form-primary" disabled={apiStatus === "checking"} type="button" onClick={onCreateProject}>
            创建项目
          </button>
          <button className="outline-button form-secondary" type="button">
            <Upload size={17} />
            导入已有论文
          </button>
          <button className="outline-button form-secondary" type="button">
            <Save size={17} />
            保存草稿
          </button>
        </div>

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
  onLoadArtifact: (artifactId: string) => void;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  onSelectView: (view: ViewId) => void;
  papers: PaperRow[];
  projectCount: number;
  query: string;
}) {
  const [highOnly, setHighOnly] = useState(false);
  const displayPapers = highOnly ? papers.filter((paper) => paper.priority === "High") : papers;
  const highCount = papers.filter((paper) => paper.priority === "High").length;
  const retrievalWarnings = errors.filter(isRetrievalWarning);
  const backendErrors = errors.filter((error) => !isRetrievalWarning(error));
  const tableRows = displayPapers.map((paper) => ({
    title: paper.title,
    authors: paper.authors,
    year: paper.year,
    type: paper.type,
    source: paper.source,
    priority: paper.priority,
    relation: paper.relation,
  }));

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
            <button className="outline-button" type="button">
              <Download size={17} />
              导出 CSV
            </button>
            <button className="gradient-button" disabled={apiStatus !== "online"} type="button" onClick={() => onSelectView("direction-review")}>
              <Sparkles size={17} />
              生成 Direction Review
            </button>
          </div>
        </div>

        <div className="table-metrics">
          <MetricCard icon={FileText} label="检索论文" value={String(papers.length)} />
          <MetricCard icon={Target} label="High Priority" value={String(highCount)} />
          <MetricCard icon={ShieldCheck} label="Retrieval Warning" value={String(retrievalWarnings.length)} amber />
          <MetricCard icon={AlertTriangle} label="Backend Error" value={String(backendErrors.length)} amber={backendErrors.length > 0} />
        </div>

        <div className="paper-search-strip">
          <label className="paper-query-box">
            <Search size={20} />
            <input
              value={query}
              placeholder={activeProject?.keyword || "multimodal large language model visual question answering evidence faithfulness"}
              onChange={(event) => onQueryChange(event.target.value)}
            />
            {query ? (
              <button type="button" onClick={() => onQueryChange("")} aria-label="clear search">
                <X size={19} />
              </button>
            ) : null}
          </label>
          <button
            className="outline-button search-again"
            disabled={apiStatus !== "online" || isSearching || query.trim().length === 0}
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
          <button className="square-more" type="button" aria-label="more">
            <MoreHorizontal size={20} />
          </button>
        </div>

        {isSearching ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}

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
                <tr key={`${paper.title}-${index}`}>
                  <td>
                    <strong>{paper.title}</strong>
                    <small>{paper.authors}</small>
                  </td>
                  <td>{paper.year}</td>
                  <td>
                    <span className={`paper-type type-${paper.type.toLowerCase()}`}>{paper.type || "Method"}</span>
                  </td>
                  <td>{paper.source}</td>
                  <td>
                    <span className={`priority ${paper.priority.toLowerCase()}`}>{paper.priority}</span>
                  </td>
                  <td>{paper.relation}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tableRows.length === 0 ? (
            <div className="product-table-empty">
              <h2>{apiStatus === "offline" ? "API 未连接" : "本次没有可展示论文"}</h2>
              <p>
                {apiStatus === "offline"
                  ? "请先启动 ScholarFlow 后端服务。当前不是“没有论文”，而是前端无法读取真实 paper table。"
                  : highOnly
                    ? "当前没有 High Priority 论文。可以关闭筛选，或重新检索更具体的方向。"
                    : "请先运行 Literature Search，系统不会用内置示例论文填充表格。"}
              </p>
            </div>
          ) : null}
        </div>

        <div className="table-warning">
          <Lightbulb size={17} />
          <span>
            {errors.length
              ? retrievalWarnings.length
                ? `检索源降级 warning：${warningPreview(retrievalWarnings, 2)}`
                : `后端错误：${warningPreview(backendErrors, 2)}`
              : "当前没有检索警告。表格只展示本项目真实论文记录，不使用内置示例数据。"}
          </span>
        </div>
      </section>

      <ConferenceLogoBelt withTitle={false} />
    </div>
  );
}

function MetricCard({
  amber = false,
  icon: Icon,
  label,
  value,
}: {
  amber?: boolean;
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <article className={amber ? "metric-card amber" : "metric-card"}>
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
  isGenerating,
  onGenerate,
  onInputChange,
  onLoadArtifact,
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
  isGenerating: boolean;
  onGenerate: () => void;
  onInputChange: (value: string) => void;
  onLoadArtifact: (artifactId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  papers: PaperRow[];
  projectCount: number;
  selectedPaperId: string;
  supplementalInput: string;
}) {
  const [activeQuestion, setActiveQuestion] = useState(1);
  const selectedPaper = papers.find((paper) => paper.id === selectedPaperId) ?? papers[0];
  const cardSections = card?.sections ?? [];
  const signals = card?.signals;
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
  const signalTags = [
    signals?.task ? `task: ${signals.task}` : "",
    signals?.method ? `method: ${signals.method}` : "",
    signals?.dataset ? `dataset: ${signals.dataset}` : "",
    signals?.metric ? `metric: ${signals.metric}` : "",
    signals?.claim ? `claim: ${signals.claim}` : "",
  ].filter(Boolean);
  const selectedSummary = selectedPaper?.abstract || selectedPaper?.relation || "";

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
              <h1>论文精读 · Deep Paper Card</h1>
              <p>
                {selectedPaper?.title ?? "尚未选择论文"}
                {selectedPaper?.venue || selectedPaper?.year ? <span>{selectedPaper.venue || selectedPaper.year}</span> : null}
              </p>
              <small>只展示当前项目真实论文和已生成的 Paper Card；没有生成时不会填充示例结论。</small>
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
              <strong>{card ? "Paper Card 摘要" : "待生成 Paper Card"}</strong>
              <p>{selectedSummary || "请先在 Paper Table 选择论文，或粘贴摘要/正文片段后生成 Paper Card。"}</p>
            </div>
          </article>

          <section className="question-board">
            <div className="question-board-head">
              <h2>核心问题（12 个）</h2>
              <span>{cardSections.length}/12 已生成</span>
            </div>
            {cardSections.length ? (
              <div className="question-grid">
                {cardSections.map((section, index) => (
                  <button
                    className={activeQuestion === index + 1 ? "question-card active" : "question-card"}
                    key={section.id}
                    type="button"
                    onClick={() => setActiveQuestion(index + 1)}
                  >
                    <span>{index + 1}</span>
                    <strong>{section.title}</strong>
                    <p>{section.content}</p>
                    <CheckCircle2 size={15} />
                  </button>
                ))}
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
                <strong>{cardSections.length}</strong>
                <span>Sections</span>
              </div>
            </div>
          </section>

          <section className="evidence-chain-card">
            <div className="aside-heading compact">
              <h2>生成状态</h2>
              <span>{card ? "已生成" : "待生成"}</span>
            </div>
            <div className="chain-step">
              <span>1</span>
              <div>
                <strong>最脆弱假设</strong>
                <p>{card?.weakest_assumption || "尚未生成，系统不会编造论文局限。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>2</span>
              <div>
                <strong>一周最小复现</strong>
                <p>{card?.minimal_reproduction || "需要生成 Paper Card 后才能给出具体实验切口。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>3</span>
              <div>
                <strong>输入来源</strong>
                <p>{selectedPaper ? "来自当前项目 Paper Table。" : supplementalInput.trim() ? "来自用户粘贴内容。" : "暂无输入。"}</p>
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
  onRoundChange,
  onSelectedPaperChange,
  review,
  round,
  selectedPaperId,
}: {
  apiMessage: string;
  apiStatus: ApiStatus;
  direction: string;
  isGenerating: boolean;
  onDirectionChange: (direction: string) => void;
  onGenerate: () => void;
  onLoadArtifact: (artifactId: string) => void;
  onRoundChange: (round: number) => void;
  onSelectedPaperChange: (paperId: string) => void;
  review: ApiDirectionReviewResponse | null;
  round: number;
  selectedPaperId: string;
}) {
  const readings = review?.papers ?? [];
  const artifactRefs = getDirectionArtifactRefs(review);
  const selectedReading = readings.find((reading) => reading.paper.id === selectedPaperId) ?? null;
  const recommendedPaperIds = review?.recommended_paper_ids ?? [];
  const recommendedReadings =
    readings.filter((reading) => recommendedPaperIds.includes(reading.paper.id) || reading.self_read_priority) ?? [];
  const canGenerate = apiStatus === "online" && !isGenerating && direction.trim().length > 0;
  const expectedRoundCount = review?.target_paper_count ?? 10;
  const actualRoundCount = review?.round_read_count ?? readings.length;
  const isPartialReview = review?.review_status === "partial";
  const partialRoundWarning =
    review && (isPartialReview || actualRoundCount < expectedRoundCount)
      ? `本轮实际只读取 ${actualRoundCount}/${expectedRoundCount} 篇。可能是检索源限流、候选不足或去重后不足 10 篇。`
      : "";
  const reviewWarnings = review ? [partialRoundWarning, ...review.errors].filter(Boolean) : [];

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
                <p className="section-kicker">Cumulative Understanding</p>
                <h2>{review.direction}</h2>
              </div>
              <div className="direction-stat-grid">
                <span>Round {review.round}</span>
                <span>{isPartialReview ? "Partial" : "Complete"}</span>
                <span>本轮 {actualRoundCount}/{expectedRoundCount}</span>
                <span>累计 {review.total_read_count} papers</span>
                {review.scope ? <span>{review.scope.year_range}</span> : null}
              </div>
            </div>
            <p>{review.direction_summary}</p>
            {partialRoundWarning ? (
              <div className="partial-review-banner">
                <AlertTriangle size={18} />
                <div>
                  <strong>Partial Direction Review · {actualRoundCount}/{expectedRoundCount}</strong>
                  <p>{partialRoundWarning}</p>
                </div>
              </div>
            ) : null}
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
                <div className="direction-chip-row">
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
            {reviewWarnings.length ? (
              <div className="retrieval-errors">
                <strong>检索警告</strong>
                <p>{warningPreview(reviewWarnings, 3)}</p>
              </div>
            ) : null}
          </section>

          {readings.length ? (
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
          ) : null}

          {readings.length ? (
          <div className="direction-reader-layout">
            <section className="direction-paper-grid" aria-label="direction paper cards">
              {readings.map((reading, index) => {
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
          ) : (
            <section className="direction-empty-state">
              <BookOpen size={22} />
              <div>
                <h2>精读详情已保存为 Artifact</h2>
                <p>为了控制 Direction Review 响应体，完整 BaselineMap、Paper Cards 和 Memory 不再随 POST 返回。点击上方 Artifact 可按需回读完整内容。</p>
              </div>
            </section>
          )}
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
  references: NonNullable<ApiDirectionReviewResponse["baseline_map"]>["classic_baselines"];
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

function DirectionPaperDetail({ reading }: { reading: ApiDirectionPaperReading }) {
  const signals = reading.signals;
  const missingSignals = signals?.missing_signals ?? [];
  const sections = reading.sections ?? [];
  const researchSight = normalizeResearchSight(reading.research_sight);
  const evidencePack = normalizeEvidencePack(researchSight.evidence_pack);
  const critiqueEvidence = new Map(
    (researchSight.critique_evidence ?? []).map((item) => [item.field, item]),
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
          <h2>{reading.paper?.title ?? "Untitled paper"}</h2>
        </div>
        {reading.paper?.url ? (
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
            <span>{evidencePack.grounding_summary}</span>
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
        {sections.length ? (
          sections.map((section, index) => (
            <article className="direction-detail-section" key={section.id}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{section.title}</h3>
                <p>{section.content}</p>
              </div>
            </article>
          ))
        ) : (
          <article className="direction-detail-section empty">
            <span>00</span>
            <div>
              <h3>暂无 12 sections</h3>
              <p>当前 artifact 没有提供 card.sections 或 sections 字段，但 Paper Signals 与 Research Sight 仍可查看。</p>
            </div>
          </article>
        )}
      </div>
    </section>
  );
}

export function ResearchMemoryView({
  apiMessage,
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
  apiMessage: string;
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
  const memoryHits = result?.hits ?? [];

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
        {isQuerying ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}
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
                <span>{memoryHits.length} hits</span>
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
                    {(result.direction_memory.baseline_map.recent_strong_baselines ?? [])
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
                  <div className="memory-hit-score-grid" aria-label="memory score breakdown">
                    <span>title {(hit.title_score ?? 0).toFixed(2)}</span>
                    <span>keyword {(hit.keyword_score ?? 0).toFixed(2)}</span>
                    <span>section {(hit.section_score ?? 0).toFixed(2)}</span>
                    <span>priority {(hit.priority_score ?? 0).toFixed(2)}</span>
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
                      <dd>{pack.grounding_summary || "暂无 EvidencePack"}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}
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
        {isGenerating ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}
        {decision ? (
          <div className="validation-summary">
            <strong>Idea Validation</strong>
            <p>{decision.validation.idea}</p>
            <span className={`risk ${decision.validation.novelty_risk}`}>{decision.validation.novelty_risk}</span>
            <span>{decision.validation.feasibility}</span>
          </div>
        ) : null}
      </section>

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
