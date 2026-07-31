import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  BrainCircuit,
  ChevronDown,
  FileText,
  Lightbulb,
} from "lucide-react";
import type {
  ApiArtifactRef,
  ApiDirectionReviewResponse,
  ApiDirectionReviewRunStatusResponse,
} from "@scholarflow/schemas";
import type { ApiStatus } from "../types/workflow";
import {
  formatAcademicText,
  formatEvidenceLevel,
} from "./shared/formatters";
import {
  ResearchWarningPanel,
  formatArtifactDate,
} from "./shared/ProductViewRuntime";

export function DirectionReviewPanel({
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
