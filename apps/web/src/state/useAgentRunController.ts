import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import type {
  ApiAgentPlanResponse,
  ApiAgentRunStatusResponse,
  ApiArtifact,
  ApiProject,
  ApiWorkflowStepState,
} from "@scholarflow/schemas";
import { isAbortError } from "../apiClient";
import {
  cancelAgentRun,
  createAgentPlan,
  executeAgentRun,
  getAgentRunStatus,
} from "../services/agentService";
import type { RequestGuard } from "./useRequestCoordinator";

type AgentRunControllerOptions = {
  activeProject: ApiProject | null;
  activeProjectIdRef: MutableRefObject<string | null>;
  applyBackendWorkflowSteps: (
    steps: ApiWorkflowStepState[] | undefined,
  ) => void;
  beginAgentRequest: () => RequestGuard;
  blockDemoProjectAction: () => void;
  formatApiFailure: (error: unknown, fallback: string) => string;
  isDemoProject: (
    projectOrId: ApiProject | string | undefined | null,
  ) => boolean;
  loadProjectResources: (
    projectId: string,
    guard: RequestGuard,
  ) => Promise<void>;
  onArtifact: (artifact: ApiArtifact) => void;
  refreshProjectResources: (projectId: string) => Promise<void>;
  setApiMessage: (message: string) => void;
};

const INITIAL_AGENT_TASK =
  "请根据我的研究方向，生成一个从文献检索到可验证 gap 的最小科研任务计划。";

export function useAgentRunController({
  activeProject,
  activeProjectIdRef,
  applyBackendWorkflowSteps,
  beginAgentRequest,
  blockDemoProjectAction,
  formatApiFailure,
  isDemoProject,
  loadProjectResources,
  onArtifact,
  refreshProjectResources,
  setApiMessage,
}: AgentRunControllerOptions) {
  const [agentTask, setAgentTask] = useState(INITIAL_AGENT_TASK);
  const [agentPlan, setAgentPlan] =
    useState<ApiAgentPlanResponse | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentRunStatus, setAgentRunStatus] =
    useState<ApiAgentRunStatusResponse | null>(null);
  const [agentRunWarnings, setAgentRunWarnings] = useState<string[]>([]);
  const pollingRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  function applySnapshot(
    projectId: string,
    status: ApiAgentRunStatusResponse,
  ) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    setAgentRunStatus(status);
    setAgentRunWarnings(status.warnings ?? []);
    applyBackendWorkflowSteps(status.workflow_steps);
    if (status.artifact) {
      onArtifact(status.artifact);
    }
    setAgentPlan((current) => {
      if (!current || current.run_id !== status.run_id) {
        return current;
      }
      return {
        ...current,
        agent_label: status.agent_label ?? current.agent_label,
        execution_mode: status.execution_mode ?? current.execution_mode,
        model_call: status.model_call ?? current.model_call,
        status: status.status,
        steps: status.steps,
        artifact: status.artifact ?? current.artifact,
      };
    });
    const statusMessage =
      status.run_status_summary ||
      `Bounded Research Agent ${status.status}`;
    setApiMessage(
      status.current_tool && status.status === "running"
        ? `${statusMessage} 当前工具：${status.current_tool}`
        : statusMessage,
    );
  }

  function startPolling(runId: string, projectId: string) {
    stopPolling();
    let inFlight = false;
    const poll = async () => {
      if (inFlight || activeProjectIdRef.current !== projectId) {
        return;
      }
      inFlight = true;
      try {
        const status = await getAgentRunStatus(runId);
        if (activeProjectIdRef.current !== projectId) {
          return;
        }
        applySnapshot(projectId, status);
        await refreshProjectResources(projectId);
        if (isTerminalAgentRunStatus(status.status)) {
          stopPolling();
          setAgentBusy(false);
        }
      } catch (error) {
        if (!isAbortError(error)) {
          setApiMessage(
            formatApiFailure(
              error,
              "轮询 Bounded Research Agent 状态失败，请查看 API 日志。",
            ),
          );
        }
      } finally {
        inFlight = false;
      }
    };
    void poll();
    pollingRef.current = window.setInterval(() => {
      void poll();
    }, 1500);
  }

  async function createPlan() {
    if (!activeProject) {
      setApiMessage("没有可运行的项目，请先创建项目或启动 API。");
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginAgentRequest();
    setAgentBusy(true);
    setApiMessage("正在生成 Research Plan...");
    try {
      const plan = await createAgentPlan(
        {
          project_id: projectId,
          task: agentTask,
        },
        { signal: guard.signal },
      );
      if (
        !guard.isCurrent() ||
        activeProjectIdRef.current !== projectId
      ) {
        return;
      }
      setAgentPlan(plan);
      setAgentRunStatus(null);
      setAgentRunWarnings([]);
      onArtifact(plan.artifact);
      setApiMessage(`Research Plan 已生成，run: ${plan.run_id}`);
      await loadProjectResources(projectId, guard);
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(
          formatApiFailure(
            error,
            "生成 Research Plan 失败，请确认 API 与 SQLite 工作区可用。",
          ),
        );
      }
    } finally {
      setAgentBusy(false);
      guard.finish();
    }
  }

  async function executeRun() {
    if (!agentPlan) {
      setApiMessage("请先生成 Research Plan。");
      return;
    }
    if (
      isDemoProject(agentPlan.project_id) ||
      isDemoProject(activeProject)
    ) {
      blockDemoProjectAction();
      return;
    }

    const guard = beginAgentRequest();
    setAgentBusy(true);
    stopPolling();
    try {
      const result = await executeAgentRun(
        agentPlan.run_id,
        { confirmed: true },
        { signal: guard.signal },
      );
      if (
        !guard.isCurrent() ||
        activeProjectIdRef.current !== agentPlan.project_id
      ) {
        return;
      }
      applySnapshot(agentPlan.project_id, {
        run_id: result.run_id,
        agent_label: result.agent_label,
        execution_mode: result.execution_mode,
        model_call: result.model_call,
        status: result.status,
        steps: result.steps,
        summary_metrics: result.summary_metrics,
        warnings: result.warnings ?? [],
        artifact_refs: result.artifact_refs ?? [],
        workflow_steps: result.workflow_steps ?? [],
        run_status_summary: result.run_status_summary,
        current_tool:
          result.current_tool ??
          result.steps.find((step) => step.status === "running")?.tool ??
          "",
        paper_count: result.paper_count,
        artifact: result.artifact,
        queued_at: result.queued_at,
        started_at: result.started_at,
        completed_at: result.completed_at,
        last_heartbeat: result.last_heartbeat,
        updated_at: result.updated_at ?? new Date().toISOString(),
      });
      await refreshProjectResources(agentPlan.project_id);
      if (isTerminalAgentRunStatus(result.status)) {
        setAgentBusy(false);
      } else {
        startPolling(agentPlan.run_id, agentPlan.project_id);
      }
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        setApiMessage(
          formatApiFailure(
            error,
            "执行 Bounded Research Agent 失败，请查看 API 日志。",
          ),
        );
        setAgentBusy(false);
      }
    } finally {
      guard.finish();
    }
  }

  async function cancelRun() {
    const runId = agentRunStatus?.run_id ?? agentPlan?.run_id;
    const projectId = agentPlan?.project_id ?? activeProject?.id;
    if (!runId || !projectId) {
      return;
    }
    try {
      const status = await cancelAgentRun(runId);
      applySnapshot(projectId, status);
      setApiMessage(
        status.run_status_summary ||
          "已请求取消 Bounded Research Agent。",
      );
      await refreshProjectResources(projectId);
      if (isTerminalAgentRunStatus(status.status)) {
        stopPolling();
        setAgentBusy(false);
      }
    } catch (error) {
      if (!isAbortError(error)) {
        setApiMessage(
          formatApiFailure(
            error,
            "取消 Bounded Research Agent 失败，请查看 API 日志。",
          ),
        );
      }
    }
  }

  function reset() {
    stopPolling();
    setAgentPlan(null);
    setAgentRunStatus(null);
    setAgentRunWarnings([]);
    setAgentBusy(false);
  }

  return {
    agentBusy,
    agentPlan,
    agentRunStatus,
    agentRunWarnings,
    agentTask,
    cancelRun,
    createPlan,
    executeRun,
    reset,
    setAgentTask,
    stopPolling,
  };
}

function isTerminalAgentRunStatus(status: string): boolean {
  return [
    "completed",
    "completed_with_warnings",
    "partial",
    "failed",
    "cancelled",
  ].includes(status);
}
