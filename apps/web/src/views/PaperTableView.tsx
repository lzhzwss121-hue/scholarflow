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
} from "../mockData";
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
import {
  ConferenceLogoBelt,
  escapeCsvCell,
  isDemoProject,
  OperationStatusNote,
  ProjectSidebar,
  ResearchWarningPanel,
  slugify,
} from "./shared/ProductViewRuntime";
import { formatAcademicText } from "./shared/formatters";

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
