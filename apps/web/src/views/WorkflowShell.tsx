import { type ReactNode, type Ref, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  FileText,
  Plus,
  X,
} from "lucide-react";
import {
  SCHOLARFLOW_VERSION,
  type ApiArtifact,
  type ApiArtifactSummary,
} from "@scholarflow/schemas";
import {
  navItems,
  type ArtifactContent,
  type TimelineEvent,
  type ViewId,
} from "../mockData";
import type {
  WorkflowActions,
  WorkflowNotice,
  WorkflowStepStatus,
  WorkflowViewModel,
} from "../types/workflow";
import {
  formatBytes,
  formatProjectStage,
  getToolEventIcon,
  isDemoProject,
  isSupersededFullTextNotice,
  summarizeWorkflowNotice,
} from "./shared/ProductViewRuntime";
import { navIcons } from "./shared/navigation";

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
