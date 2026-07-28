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
  formatAcademicText,
  formatEvidenceLevel,
  formatResearchSignal,
  formatSignalEvidenceLocation,
} from "./shared/formatters";
import { formatContributionType } from "./shared/decisionFormatters";
import {
  buildEvidenceBoundary,
  buildMemoryEvidenceBoundary,
  buildMemoryRewriteSuggestion,
  formatResearchFacet,
  OperationStatusNote,
  ResearchWarningPanel,
} from "./shared/ProductViewRuntime";

export function ResearchMemoryView({
  apiStatus,
  direction,
  isQuerying,
  isRagQuerying,
  memoryMessage,
  onQuestionChange,
  onQuery,
  onQueryRag,
  onRagQuestionChange,
  onRagTopKChange,
  onSelectView,
  onTopKChange,
  question,
  ragMessage,
  ragQuestion,
  ragResult,
  ragTopK,
  result,
  topK,
}: {
  apiStatus: ApiStatus;
  direction: string;
  isQuerying: boolean;
  isRagQuerying: boolean;
  memoryMessage: string;
  onQuestionChange: (question: string) => void;
  onQuery: () => void;
  onQueryRag: () => void;
  onRagQuestionChange: (question: string) => void;
  onRagTopKChange: (topK: number) => void;
  onSelectView: (view: ViewId) => void;
  onTopKChange: (topK: number) => void;
  question: string;
  ragMessage: string;
  ragQuestion: string;
  ragResult: ApiRagAnswerResponse | null;
  ragTopK: number;
  result: ApiResearchMemoryQueryResponse | null;
  topK: number;
}) {
  const canQueryMemory = apiStatus === "online" && !isQuerying && question.trim().length > 0;
  const canQueryRag = apiStatus === "online" && !isRagQuerying && ragQuestion.trim().length > 0;
  const memoryHits = result?.hits ?? [];
  const memoryEvidenceBoundary = buildMemoryEvidenceBoundary(memoryHits);
  const memoryUnavailable = result?.reliability_status === "no_reliable_hit" || result?.reliability_status === "no_memory";
  const memoryUnavailableTitle =
    result?.reliability_status === "no_memory" ? "当前项目还没有可检索的论文记忆" : "当前记忆没有可靠证据回答此问题";
  const queryCoverage = result?.query_coverage;
  const queryCoverageValue = Number(queryCoverage?.coverage ?? 0);
  const matchedQueryTerms = queryCoverage?.matched_terms ?? [];
  const missingQueryTerms = queryCoverage?.missing_terms ?? [];
  const requestedFacets = queryCoverage?.requested_facets ?? [];
  const coveredFacets = queryCoverage?.covered_facets ?? [];
  const missingFacets = queryCoverage?.missing_facets ?? [];

  return (
    <div className="memory-stack">
      <section className="memory-control-panel" aria-label="paper memory query">
        <div className="memory-control-header">
          <div>
            <p className="section-kicker">Paper Memory Bank</p>
            <h2>原文证据与结构化记忆问答</h2>
            <p>两种检索拥有独立问题、top-k、运行状态和结果，不再互相覆盖。</p>
          </div>
        </div>

        <div className="memory-query-mode-grid">
          <article className="memory-query-mode rag-mode">
            <header>
              <ShieldCheck size={18} />
              <div>
                <strong>原文 RAG</strong>
                <span>检索 PDF/摘要 chunk，分开输出引用、词面与语义支持状态</span>
              </div>
            </header>
            <label>
              原文 RAG 问题
              <textarea value={ragQuestion} onChange={(event) => onRagQuestionChange(event.target.value)} />
            </label>
            <div className="memory-query-mode-actions">
              <label>
                RAG 证据数
                <select value={ragTopK} onChange={(event) => onRagTopKChange(Number(event.target.value))}>
                  <option value={3}>3 条</option>
                  <option value={5}>5 条</option>
                  <option value={8}>8 条</option>
                </select>
              </label>
              <button className="primary-command" disabled={!canQueryRag} type="button" onClick={onQueryRag}>
                <ShieldCheck size={17} />
                {isRagQuerying ? "核对原文中" : "检索原文并回答"}
              </button>
            </div>
            <OperationStatusNote apiStatus={apiStatus} message={ragMessage} />
          </article>

          <article className="memory-query-mode memory-mode">
            <header>
              <BrainCircuit size={18} />
              <div>
                <strong>结构化 Paper Memory</strong>
                <span>检索 Paper Card 与 ResearchSight，不等同于原文证据</span>
              </div>
            </header>
            <label>
              用户问题
              <textarea value={question} onChange={(event) => onQuestionChange(event.target.value)} />
            </label>
            <div className="memory-query-mode-actions">
              <label>
                检索论文数
                <select value={topK} onChange={(event) => onTopKChange(Number(event.target.value))}>
                  <option value={3}>3 篇</option>
                  <option value={5}>5 篇</option>
                  <option value={8}>8 篇</option>
                </select>
              </label>
              <button className="secondary-command" disabled={!canQueryMemory} type="button" onClick={onQuery}>
                <BrainCircuit size={17} />
                {isQuerying ? "检索记忆中" : "检索记忆并回答"}
              </button>
            </div>
            <OperationStatusNote apiStatus={apiStatus} message={memoryMessage} />
          </article>
        </div>

        <div className="memory-chip-row">
          <span>当前方向：{direction || "未指定"}</span>
          <span>原文 RAG：chunk + citation</span>
          <span>Paper Memory：Paper Card + ResearchSight</span>
          <span>无可靠证据则拒答</span>
        </div>
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
                <span title="可靠命中的原文证据对用户问题锚点的联合覆盖率。">
                  问题覆盖 {Math.round(queryCoverageValue * 100)}%
                </span>
              </div>
            </div>
            <p className="memory-answer-summary">{result.answer_summary || result.answer}</p>
            {queryCoverage ? (
              <div className="memory-query-coverage" aria-label="memory query coverage">
                <strong>本次回答覆盖范围</strong>
                {queryCoverage.scientific_query ? (
                  <p>实际科研检索式：{queryCoverage.scientific_query}</p>
                ) : null}
                <p>已覆盖：{matchedQueryTerms.join(" / ") || "无"}</p>
                <p>未覆盖：{missingQueryTerms.join(" / ") || "无，当前问题锚点已全部覆盖"}</p>
                {requestedFacets.length ? (
                  <>
                    <p>指定维度：{requestedFacets.map(formatResearchFacet).join(" / ")}</p>
                    <p>有证据：{coveredFacets.map(formatResearchFacet).join(" / ") || "无"}</p>
                    <p>待补证：{missingFacets.map(formatResearchFacet).join(" / ") || "无"}</p>
                  </>
                ) : null}
              </div>
            ) : null}
            {result.claims?.length ? (
              <div className="memory-claim-list" aria-label="memory synthesized claims">
                {result.claims.map((claim) => (
                  <article key={claim.id}>
                    <div>
                      {claim.facet ? (
                        <span className="memory-facet">{formatResearchFacet(claim.facet)}</span>
                      ) : null}
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
                      <span>问题覆盖 {Math.round((hit.query_coverage ?? 0) * 100)}%</span>
                    </div>
                    <div className="memory-hit-evidence" data-testid="memory-hit-evidence">
                      <strong>命中理由</strong>
                      <span>{hit.paper?.relation || "标题、关键词或结构化字段与当前问题存在直接交集。"}</span>
                      <span>直接命中：{hit.matched_query_terms?.join(" / ") || "未记录"}</span>
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
