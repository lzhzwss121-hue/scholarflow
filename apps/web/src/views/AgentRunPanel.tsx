import { BrainCircuit, Play, X } from "lucide-react";
import type {
  ApiAgentPlanResponse,
  ApiAgentPlanStep,
  ApiAgentRunStatusResponse,
  ApiProject,
} from "@scholarflow/schemas";
import { toPlanStatus } from "../lib/artifactHydration";
import type { ApiStatus } from "../types/workflow";
import {
  StatusIcon,
  formatArtifactDate,
  isDemoProject,
} from "./shared/ProductViewRuntime";

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
          <p className="section-kicker">Bounded Research Agent</p>
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
              模型 provider：
              {!agentPlan.model_call
                ? "Legacy record / 未保存模型审计"
                : agentPlan.model_call.response_status === "success"
                ? `${agentPlan.model_call.provider} / ${agentPlan.model_call.model}`
                : agentPlan.model_call.fallback_reason
                  ? `Local fallback / ${agentPlan.model_call.fallback_reason}`
                  : `${agentPlan.model_call.provider} / ${agentPlan.model_call.model}`}
            </strong>
            <span>
              {(agentRunStatus?.execution_mode ?? agentPlan.execution_mode) === "bounded_observe_reason_act"
                ? "执行模式：受限 Observe → Reason → Act。模型只能选择当前 allowlist 工具；确定性代码控制证据、拒答、科研状态和 Experiment readiness。"
                : "执行模式：确定性工具图 fallback。模型不能修改工具、证据等级、拒答、科研状态或 Experiment readiness。"}
            </span>
            <span>
              {agentPlan.model_call?.external_data_sent
                ? `已向 ${agentPlan.model_call.requested_provider || agentPlan.model_call.provider} 发送任务与项目上下文。`
                : "未向外部模型发送数据。"}
            </span>
          </div>
          {agentRunStatus ? (
            <div className="agent-run-progress" aria-label="agent run progress">
              <strong>{agentRunStatus.run_status_summary || `Bounded Research Agent ${agentRunStatus.status}`}</strong>
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
