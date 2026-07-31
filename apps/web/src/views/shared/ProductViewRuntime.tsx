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
import { navIcons } from "./navigation";

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

export const PROJECT_DRAFT_STORAGE_KEY = "scholarflow.projectDraft";

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

export function summarizeWorkflowNotice(message: string): string {
  const { actionable, technical } = classifyResearchWarnings([message]);
  if (actionable.length) {
    return actionable[0];
  }
  if (technical.length) {
    return "当前步骤包含技术诊断；请在页面内展开详情后决定是否重试。";
  }
  return message;
}

export function isSupersededFullTextNotice(message: string): boolean {
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

export function formatArtifactDate(value: string) {
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

export function formatBytes(value: number) {
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

export function StatusIcon({ status }: { status: PlanStatus }) {
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

export function getToolEventIcon(tool: string): LucideIcon {
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
