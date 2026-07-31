import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type {
  ApiArtifact,
  ApiDirectionReviewResponse,
  ApiDirectionReviewRunStatusResponse,
  ApiProject,
} from "@scholarflow/schemas";
import { isAbortError, normalizeApiError } from "../apiClient";
import { getArtifact } from "../services/artifactService";
import {
  getDirectionReviewRun,
  startDirectionReviewRun,
} from "../services/directionService";
import {
  fetchProjectResourceSnapshot,
  type ProjectResourceSnapshot,
} from "./useProjectResources";
import type { RequestGuard } from "./useRequestCoordinator";

export function useDirectionReviewController({
  activeProject,
  activeProjectIdRef,
  applyBackendWorkflowSteps,
  beginDirectionRequest,
  blockDemoProjectAction,
  formatApiFailure,
  isDemoProject,
  onArtifact,
  onProjectResources,
  setApiMessage,
}: {
  activeProject: ApiProject | null;
  activeProjectIdRef: MutableRefObject<string | null>;
  applyBackendWorkflowSteps: (
    steps: ApiDirectionReviewResponse["workflow_steps"],
  ) => void;
  beginDirectionRequest: () => RequestGuard;
  blockDemoProjectAction: () => void;
  formatApiFailure: (error: unknown, fallback: string) => string;
  isDemoProject: (project: ApiProject | string | null | undefined) => boolean;
  onArtifact: (artifact: ApiArtifact) => void;
  onProjectResources: (
    projectId: string,
    snapshot: ProjectResourceSnapshot,
  ) => void;
  setApiMessage: (message: string) => void;
}) {
  const [directionInput, setDirectionInput] = useState("");
  const [directionRound, setDirectionRound] = useState(1);
  const [directionBusy, setDirectionBusy] = useState(false);
  const [directionReview, setDirectionReview] =
    useState<ApiDirectionReviewResponse | null>(null);
  const [directionRun, setDirectionRun] =
    useState<ApiDirectionReviewRunStatusResponse | null>(null);
  const [directionMessage, setDirectionMessage] = useState(
    "尚未启动 Direction Review 后端任务。",
  );
  const [selectedDirectionPaperId, setSelectedDirectionPaperId] =
    useState("");
  const pollingRef = useRef<number | null>(null);

  useEffect(() => stopPolling, []);

  function applyRunSnapshot(
    projectId: string,
    run: ApiDirectionReviewRunStatusResponse | null,
  ) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    setDirectionRun(run);
    if (!run) {
      setDirectionBusy(false);
      return;
    }
    setDirectionBusy(!isTerminalDirectionRunStatus(run.status));
    setDirectionMessage(run.message || `Direction Review ${run.status}`);
    if (run.result) {
      setDirectionReview(run.result);
      applyBackendWorkflowSteps(run.result.workflow_steps);
    }
  }

  function hydrateReview(review: ApiDirectionReviewResponse) {
    setDirectionReview(review);
    if (review.direction.trim()) {
      setDirectionInput(review.direction);
    }
  }

  async function finalizeRun(
    projectId: string,
    run: ApiDirectionReviewRunStatusResponse,
  ) {
    if (activeProjectIdRef.current !== projectId) {
      return;
    }
    stopPolling();
    applyRunSnapshot(projectId, run);
    const result = run.result;
    if (result) {
      const reviewArtifactRef =
        result.artifact_refs.find((artifact) =>
          artifact.title.toLowerCase().includes("direction_review"),
        ) ?? result.artifact_refs[0];
      if (reviewArtifactRef) {
        try {
          const artifact = await getArtifact(reviewArtifactRef.id);
          if (activeProjectIdRef.current === projectId) {
            onArtifact(artifact);
          }
        } catch (error) {
          if (
            !isAbortError(error) &&
            activeProjectIdRef.current === projectId
          ) {
            setDirectionMessage(
              `${run.message} ${formatApiFailure(
                error,
                "运行已结束，但 Direction Review artifact 回读失败。",
              )}`,
            );
          }
        }
      }
    }
    try {
      const snapshot = await fetchProjectResourceSnapshot(projectId);
      if (activeProjectIdRef.current === projectId) {
        onProjectResources(projectId, snapshot);
      }
    } catch (error) {
      if (
        !isAbortError(error) &&
        activeProjectIdRef.current === projectId
      ) {
        setDirectionMessage(
          `${run.message} 项目资源刷新失败，可重新进入项目恢复已保存结果。`,
        );
      }
    }
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
        const run = await getDirectionReviewRun(projectId, runId);
        if (activeProjectIdRef.current !== projectId) {
          return;
        }
        applyRunSnapshot(projectId, run);
        if (isTerminalDirectionRunStatus(run.status)) {
          await finalizeRun(projectId, run);
        }
      } catch (error) {
        if (
          !isAbortError(error) &&
          activeProjectIdRef.current === projectId
        ) {
          setDirectionMessage(
            formatApiFailure(
              error,
              "轮询 Direction Review 真实进度失败。",
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
    }, 1200);
  }

  function stopPolling() {
    if (pollingRef.current !== null) {
      window.clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }

  async function createDirectionReview() {
    if (!activeProject) {
      setApiMessage(
        "没有可写入的后端项目，请先创建或启动 API。",
      );
      return;
    }
    if (isDemoProject(activeProject.id)) {
      blockDemoProjectAction();
      return;
    }

    const projectId = activeProject.id;
    const guard = beginDirectionRequest();
    setDirectionBusy(true);
    setDirectionMessage(
      `正在向后端提交第 ${directionRound} 轮 Direction Review 任务...`,
    );
    try {
      const run = await startDirectionReviewRun(
        projectId,
        {
          direction: directionInput,
          round: directionRound,
        },
        { signal: guard.signal },
      );
      if (
        !guard.isCurrent() ||
        activeProjectIdRef.current !== projectId
      ) {
        return;
      }
      setSelectedDirectionPaperId("");
      applyRunSnapshot(projectId, run);
      if (isTerminalDirectionRunStatus(run.status)) {
        await finalizeRun(projectId, run);
      } else {
        startPolling(run.run_id, projectId);
      }
    } catch (error) {
      if (!isAbortError(error) && guard.isCurrent()) {
        const normalized = normalizeApiError(error);
        setDirectionMessage(
          normalized.kind === "timeout"
            ? "Direction Review 任务提交超时；请检查后端运行列表后再决定是否重试。"
            : formatApiFailure(
                error,
                "Direction Review 任务启动失败，请检查 API 日志。",
              ),
        );
        setDirectionBusy(false);
      }
    } finally {
      guard.finish();
    }
  }

  function reset() {
    stopPolling();
    setDirectionReview(null);
    setDirectionRun(null);
    setDirectionMessage("尚未启动 Direction Review 后端任务。");
    setSelectedDirectionPaperId("");
    setDirectionBusy(false);
  }

  return {
    applyRunSnapshot,
    createDirectionReview,
    directionBusy,
    directionInput,
    directionMessage,
    directionReview,
    directionRound,
    directionRun,
    hydrateReview,
    reset,
    selectedDirectionPaperId,
    setDirectionInput,
    setDirectionRound,
    setSelectedDirectionPaperId,
    startPolling,
    stopPolling,
  };
}

export function isTerminalDirectionRunStatus(status: string): boolean {
  return [
    "complete",
    "partial",
    "blocked",
    "failed",
    "cancelled",
  ].includes(status);
}
