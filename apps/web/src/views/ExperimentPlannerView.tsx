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
  buildDecisionEvidenceBoundary,
  experimentStepDeliverable,
  OperationStatusNote,
  ResearchWarningPanel,
} from "./shared/ProductViewRuntime";

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
  const isPartial = plan?.status === "partial";
  const decisionEvidenceBoundary = buildDecisionEvidenceBoundary(decision);
  const goalConstraints = buildGoalConstraintDisplay(plan?.goal_alignment);
  const readinessItems = buildReadinessDisplay(plan?.readiness_checks);
  const experimentNotice = decisionEvidenceBoundary
    ? {
        message: decisionEvidenceBoundary.message,
        title: decisionEvidenceBoundary.title,
      }
    : plan && isBlocked
      ? {
          message: `${
            plan.anchor_paper_title
              ? `锚点论文：${plan.anchor_paper_title}。`
              : "当前没有满足主张、数据集、指标和基线要求的可验证锚点论文。"
          }${
            plan.unblock_suggestions[0]
              ? ` 下一步：${plan.unblock_suggestions[0]}`
              : " 下一步：上传关键论文 PDF 并重新生成 Paper Card。"
          }`,
          title: plan.anchor_paper_title ? "实验硬约束未满足" : "实验计划已阻塞",
        }
      : plan && isPartial
        ? {
            message:
              "科研锚点已有全文定位，但代码或 API、模型版本、样本量、随机种子、资源预算或停止阈值仍待确认。",
            title: "当前计划不能直接执行",
          }
        : null;

  return (
    <div className="view-stack">
      <section className="decision-panel" aria-label="experiment plan generator">
        <div className="decision-header">
          <div>
            <p className="section-kicker">Experiment Plan</p>
            <h2>
              {plan
                ? isBlocked
                  ? plan.anchor_paper_title
                    ? "实验约束尚未满足"
                    : "缺少可复现实验 anchor"
                  : isPartial
                    ? "科研锚点已确认，执行条件待补齐"
                    : "可执行的最小实验"
                : "从 gap 生成实验计划"}
            </h2>
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

      {experimentNotice ? (
        <section
          className={isBlocked ? "experiment-blocked-banner" : "experiment-partial-banner"}
          role="status"
          aria-label="experiment plan notice"
        >
          <AlertTriangle size={18} />
          <div>
            <strong>{experimentNotice.title}</strong>
            <p>{experimentNotice.message}</p>
          </div>
        </section>
      ) : null}

      {!experimentNotice && decision?.warnings?.length ? (
        <ResearchWarningPanel title="Experiment Plan 证据状态" warnings={decision.warnings} />
      ) : null}

      {plan ? (
        <section className={`experiment-detail ${plan.status}`}>
          <header className="experiment-detail-header">
            <div>
              <p className="section-kicker">Minimal experiment</p>
              <h2>{plan.claim || (isBlocked ? "尚未形成可执行实验主张" : "实验主张待补充")}</h2>
            </div>
            <span className="experiment-status-badge" data-status={plan.status}>
              {formatExperimentStatus(plan.status)}
            </span>
          </header>

          <div className="experiment-information-grid">
            <article className="experiment-information-group" aria-label="research anchors">
              <header>
                <span>01</span>
                <div>
                  <strong>科研锚点</strong>
                  <small>只展示已经进入计划的论文、数据和评测对象</small>
                </div>
              </header>
              <dl>
                <ExperimentField label="锚点论文" value={plan.anchor_paper_title} />
                <ExperimentField label="数据集" value={plan.dataset} />
                <ExperimentField label="对比基线" value={plan.baseline} />
                <ExperimentField label="评估指标" value={plan.metrics.join("、")} />
                <ExperimentField label="消融设计" value={plan.ablations.join("；")} />
              </dl>
            </article>

            <article className="experiment-information-group" aria-label="goal constraints">
              <header>
                <span>02</span>
                <div>
                  <strong>目标约束</strong>
                  <small>用户指定的方法、数据集、基线和排除条件</small>
                </div>
              </header>
              <dl>
                <div>
                  <dt>对齐状态</dt>
                  <dd className="constraint-status" data-status={goalConstraints.statusTone}>
                    {goalConstraints.statusLabel}
                  </dd>
                </div>
                <div>
                  <dt>匹配得分</dt>
                  <dd>{goalConstraints.scoreLabel}</dd>
                </div>
                <ExperimentField label="已满足术语" value={goalConstraints.matchedTerms.join("、")} />
                <ExperimentField label="缺失术语" value={goalConstraints.missingTerms.join("、")} tone={goalConstraints.missingTerms.length ? "blocked" : undefined} />
                <ExperimentField label="已满足硬约束" value={goalConstraints.matchedHardConstraints.join("、")} />
                <ExperimentField label="未满足硬约束" value={goalConstraints.missingHardConstraints.join("、")} tone={goalConstraints.missingHardConstraints.length ? "blocked" : undefined} />
                <ExperimentField label="对照对象" value={goalConstraints.contrastTerms.join("、")} />
                <ExperimentField label="排除冲突" value={goalConstraints.excludedMatches.join("、")} tone={goalConstraints.excludedMatches.length ? "blocked" : undefined} />
              </dl>
              {goalConstraints.groups.length ? (
                <ul className="constraint-group-list">
                  {goalConstraints.groups.map((group, index) => (
                    <li key={`${group.label}-${index}`} data-status={group.statusTone}>
                      <strong>{group.label}</strong>
                      <span>{group.terms.join("、") || "未提供具体对象"}</span>
                      <small>{group.detail}</small>
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>

            <article className="experiment-information-group" aria-label="execution conditions">
              <header>
                <span>03</span>
                <div>
                  <strong>执行条件</strong>
                  <small>只有全部关键条件明确后才允许标记为可执行</small>
                </div>
              </header>
              <p className="experiment-resource-note">{plan.resources || "尚未提供资源说明。"}</p>
              {readinessItems.length ? (
                <ul className="experiment-check-list">
                  {readinessItems.map((item) => (
                    <li key={item.key} data-status={item.status}>
                      <div>
                        <strong>{item.label}</strong>
                        <span>{item.statusLabel}</span>
                      </div>
                      <p>{item.detail}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="experiment-empty-checks">尚未生成执行条件检查。</p>
              )}
            </article>
          </div>

          {(isBlocked || isPartial) && plan.unblock_suggestions.length ? (
            <div className="experiment-unblock">
              <strong>下一步补齐</strong>
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
              week: `步骤 ${index + 1}`,
              goal: step,
              deliverable: isFinalStep ? plan.success_criterion : experimentStepDeliverable(index),
              cost: index === 0 ? "环境准备" : isFinalStep ? "结果汇总" : "过程记录",
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

function ExperimentField({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "blocked" | "ready" | "unknown";
  value: string;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd data-status={tone}>{value || "未指定"}</dd>
    </div>
  );
}

type ExperimentStatusTone = "ready" | "blocked" | "unknown" | "not-required";

type GoalConstraintGroupDisplay = {
  detail: string;
  label: string;
  statusTone: ExperimentStatusTone;
  terms: string[];
};

type GoalConstraintDisplay = {
  contrastTerms: string[];
  excludedMatches: string[];
  groups: GoalConstraintGroupDisplay[];
  matchedHardConstraints: string[];
  matchedTerms: string[];
  missingHardConstraints: string[];
  missingTerms: string[];
  scoreLabel: string;
  statusLabel: string;
  statusTone: ExperimentStatusTone;
};

type ReadinessDisplayItem = {
  detail: string;
  key: string;
  label: string;
  status: ExperimentStatusTone;
  statusLabel: string;
};

const readinessFieldLabels: Record<string, string> = {
  anchor: "论文锚点",
  annotation: "人工标注",
  baseline: "对比基线",
  code_or_api: "代码或 API",
  compute: "设备与算力",
  dataset: "数据集",
  metric: "评估指标",
  model_version: "模型版本",
  resource_budget: "资源预算",
  run_protocol: "运行协议",
  sample_size: "样本量",
  seed: "随机种子",
  stopping_threshold: "停止阈值",
  success_threshold: "成功阈值",
};

function buildGoalConstraintDisplay(alignment: Record<string, unknown> | undefined): GoalConstraintDisplay {
  const status = String(alignment?.status ?? "not_specified");
  const score = typeof alignment?.score === "number" ? alignment.score : null;
  const hardConstraintChecks =
    alignment?.hard_constraint_checks &&
    typeof alignment.hard_constraint_checks === "object" &&
    !Array.isArray(alignment.hard_constraint_checks)
      ? (alignment.hard_constraint_checks as Record<string, unknown>)
      : {};
  const derivedMatchedHardConstraints = Object.entries(hardConstraintChecks)
    .filter(([, value]) => value === "ready")
    .map(([label]) => label);
  const derivedMissingHardConstraints = Object.entries(hardConstraintChecks)
    .filter(([, value]) => value !== "ready")
    .map(([label]) => label);
  const groups = Array.isArray(alignment?.constraint_groups)
    ? alignment.constraint_groups.flatMap((value, index) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          return [];
        }
        const group = value as Record<string, unknown>;
        const legacyMode = String(group.mode ?? "");
        const operator = String(group.operator ?? (["any_of", "all_of"].includes(legacyMode) ? legacyMode : ""));
        const requirement = ["required", "preferred"].includes(legacyMode) ? legacyMode : "required";
        const terms = readStringList(group.values ?? group.terms);
        const matched = readStringList(group.matched_values ?? group.satisfied_by);
        const rawStatus = String(group.status ?? "");
        const statusTone: ExperimentStatusTone =
          rawStatus === "ready" || (matched.length > 0 && operator === "any_of")
            ? "ready"
            : rawStatus === "blocked" || rawStatus === "preferred_missing"
              ? "blocked"
              : "unknown";
        const operatorLabel =
          operator === "any_of" ? "任一满足" : operator === "all_of" ? "全部满足" : "逐项核对";
        const requirementLabel = requirement === "preferred" ? "偏好约束" : "必需约束";
        return [
          {
            detail: matched.length ? `已命中：${matched.join("、")}` : "尚未命中",
            label: `${requirementLabel} · ${operatorLabel}`,
            statusTone,
            terms,
          } satisfies GoalConstraintGroupDisplay,
        ];
      })
    : [];
  return {
    contrastTerms: readStringList(alignment?.contrast_terms),
    excludedMatches: readStringList(alignment?.excluded_matches),
    groups,
    matchedHardConstraints:
      readStringList(alignment?.matched_hard_constraints).length > 0
        ? readStringList(alignment?.matched_hard_constraints)
        : derivedMatchedHardConstraints,
    matchedTerms: readStringList(alignment?.matched_required_terms),
    missingHardConstraints:
      readStringList(alignment?.missing_hard_constraints).length > 0
        ? readStringList(alignment?.missing_hard_constraints)
        : derivedMissingHardConstraints,
    missingTerms: readStringList(alignment?.missing_required_terms),
    scoreLabel: score === null ? "未计算" : `${Math.round(score)} / 100`,
    statusLabel: formatGoalAlignmentStatus(status),
    statusTone: goalAlignmentTone(status),
  };
}

function buildReadinessDisplay(checks: Record<string, string> | undefined): ReadinessDisplayItem[] {
  if (!checks) {
    return [];
  }
  return Object.entries(checks).map(([key, rawValue]) => {
    const separator = rawValue.indexOf(":");
    const rawStatus = separator >= 0 ? rawValue.slice(0, separator).trim() : "unknown";
    const detail = separator >= 0 ? rawValue.slice(separator + 1).trim() : rawValue;
    const status: ExperimentStatusTone =
      rawStatus === "ready"
        ? "ready"
        : rawStatus === "blocked"
          ? "blocked"
          : rawStatus === "not_required"
            ? "not-required"
            : "unknown";
    return {
      detail: detail || "未提供说明",
      key,
      label: readinessFieldLabels[key] ?? "其他执行条件",
      status,
      statusLabel:
        status === "ready"
          ? "已确认"
          : status === "blocked"
            ? "已阻塞"
            : status === "not-required"
              ? "无需新增"
              : "待补充",
    };
  });
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function formatExperimentStatus(status: "ready" | "partial" | "blocked"): string {
  return status === "ready" ? "可执行" : status === "partial" ? "待补执行条件" : "已阻塞";
}

function formatGoalAlignmentStatus(status: string): string {
  if (status === "aligned") {
    return "目标已对齐";
  }
  if (status === "mismatch") {
    return "目标未对齐";
  }
  if (status === "excluded") {
    return "命中排除条件";
  }
  if (status === "blocked") {
    return "缺少可核验锚点";
  }
  return "未指定硬约束";
}

function goalAlignmentTone(status: string): ExperimentStatusTone {
  if (status === "aligned") {
    return "ready";
  }
  if (status === "mismatch" || status === "excluded" || status === "blocked") {
    return "blocked";
  }
  return "unknown";
}
