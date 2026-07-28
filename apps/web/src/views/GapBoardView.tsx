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
import {
  formatConfidence,
  formatContributionType,
  formatDecisionStatus,
  formatFeasibility,
  formatGapKind,
  formatGapSupportStatus,
  formatRiskLevel,
} from "./shared/decisionFormatters";
import {
  buildDecisionEvidenceBoundary,
  OperationStatusNote,
  ResearchWarningPanel,
} from "./shared/ProductViewRuntime";

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
  const groundedGapCount = Number(evidenceQuality.grounded_gap_evidence_count ?? 0);
  const specificGapCount = Number(evidenceQuality.specific_gap_evidence_count ?? 0);
  const corroboratedGapCount = Number(evidenceQuality.corroborated_gap_group_count ?? 0);
  const conflictedGapCount = Number(evidenceQuality.conflicted_gap_group_count ?? 0);
  const decisionEvidenceBoundary = buildDecisionEvidenceBoundary(decision);
  const isConservative = Boolean(decision && (decisionStatus !== "complete" || decisionEvidenceBoundary));

  return (
    <div className="view-stack">
      <section className="decision-panel" aria-label="research decision generator">
        <div className="decision-header">
          <div>
            <p className="section-kicker">Research Decision</p>
            <h2>研究空白与新颖性判断</h2>
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
            <span>研究类型：{formatContributionType(decision.decision_intent.contribution_type)}</span>
            <span>
              候选匹配术语：{decision.decision_intent.required_terms.join(" / ") || "未指定"}
            </span>
            <span>显式硬约束按 all_of 逐项校验；“A/B/C 任一”按 any_of 校验，组内命中一项即可。</span>
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
            <strong>研究判断 · {formatDecisionStatus(decisionStatus)}</strong>
            <p>{decision.validation.idea}</p>
            <span className={`risk ${decision.validation.novelty_risk}`}>
              新颖性风险：{formatRiskLevel(decision.validation.novelty_risk)}
            </span>
            <span>实施周期：{formatFeasibility(decision.validation.feasibility)}</span>
            <span>可定位限制 {groundedGapCount}</span>
            <span>满足具体性要求 {specificGapCount}</span>
            <span>全文跨论文一致 {corroboratedGapCount} 组</span>
            <span>冲突证据 {conflictedGapCount} 组</span>
          </div>
        ) : null}
      </section>

      {isConservative ? (
        <section className="partial-review-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>{decisionEvidenceBoundary?.title ?? `Gap Board · ${formatDecisionStatus(decisionStatus)}`}</strong>
            <p>
              {decisionEvidenceBoundary?.message ??
                "上游证据不足，Idea Validation 已降级为保守版本；当前不可把 gap 当作确定性科研结论。"}
            </p>
          </div>
        </section>
      ) : null}

      {!decisionEvidenceBoundary && decision?.warnings?.length ? (
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
                <span className={`risk ${gap.novelty_risk}`}>
                  {formatRiskLevel(gap.novelty_risk)}风险
                </span>
              </div>
              <div className="gap-classification-row">
                <div className={`gap-kind ${gap.kind}`}>{formatGapKind(gap.kind)}</div>
                <span className={`confidence ${gap.confidence ?? "low"}`}>
                  {formatGapSupportStatus(gap.support_status)} · {formatConfidence(gap.confidence)}
                </span>
                <span className="gap-consistency-score">
                  一致性 {Math.round((gap.consistency_score ?? 0) * 100)}%
                </span>
              </div>
              <dl>
                <div>
                  <dt>证据结论</dt>
                  <dd>{gap.evidence}</dd>
                </div>
                <div>
                  <dt>现有不足</dt>
                  <dd>{gap.weakness}</dd>
                </div>
                <div>
                  <dt>研究机会</dt>
                  <dd>{gap.opportunity}</dd>
                </div>
                <div>
                  <dt>可行性</dt>
                  <dd>{gap.feasibility}</dd>
                </div>
              </dl>
              {gap.evidence_refs?.length ? (
                <details className="gap-evidence-details">
                  <summary>查看原文证据锚点（{gap.evidence_refs.length}）</summary>
                  <div>
                    {gap.evidence_refs.map((reference) => (
                      <article key={`${gap.id}-${reference.paper_id}-${reference.snippet_id}`}>
                        <strong>{reference.paper_title || reference.paper_id}</strong>
                        <small>
                          {[
                            reference.source,
                            reference.section,
                            reference.page ? `p.${reference.page}` : "",
                            reference.evidence_level,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </small>
                        <p>{reference.text}</p>
                      </article>
                    ))}
                  </div>
                </details>
              ) : null}
              {gap.validation_requirements?.length ? (
                <div className="gap-validation-requirements">
                  <strong>升级为可投入课题前必须完成</strong>
                  <ul>
                    {gap.validation_requirements.map((requirement) => (
                      <li key={requirement}>{requirement}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
