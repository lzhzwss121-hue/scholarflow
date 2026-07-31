import { useCallback, type MutableRefObject } from "react";
import type {
  ApiArtifact,
  ApiArtifactSummary,
  ApiDirectionReviewRunStatusResponse,
  ApiPaper,
  ApiPaperCard,
} from "@scholarflow/schemas";
import { isAbortError, normalizeApiError } from "../apiClient";
import { loadHydrationArtifacts } from "../lib/artifactHydration";
import {
  getLatestDirectionReviewRun,
  getProjectTimeline,
  listProjectArtifactSummaries,
  listProjectPaperCards,
  listProjectPapers,
} from "../services/projectService";
import type { RequestGuard } from "./useRequestCoordinator";

export type ProjectResourceSnapshot = {
  papers?: ApiPaper[];
  timeline?: Awaited<ReturnType<typeof getProjectTimeline>>;
  artifactSummaries?: ApiArtifactSummary[];
  artifacts?: ApiArtifact[];
  paperCards?: ApiPaperCard[];
  directionRun?: ApiDirectionReviewRunStatusResponse | null;
  warnings: string[];
};

export function useProjectResources({
  activeProjectIdRef,
  beginResourceRequest,
  onLoadError,
  onSnapshot,
}: {
  activeProjectIdRef: MutableRefObject<string | null>;
  beginResourceRequest: () => RequestGuard;
  onLoadError: (error: unknown) => void;
  onSnapshot: (
    projectId: string,
    snapshot: ProjectResourceSnapshot,
  ) => void;
}) {
  const loadProjectResources = useCallback(
    async (projectId: string, outerGuard?: RequestGuard) => {
      const guard = outerGuard ?? beginResourceRequest();
      try {
        const snapshot = await fetchProjectResourceSnapshot(projectId, {
          signal: guard.signal,
        });
        if (
          !guard.isCurrent() ||
          activeProjectIdRef.current !== projectId
        ) {
          return;
        }
        onSnapshot(projectId, snapshot);
      } catch (error) {
        if (!guard.isCurrent() || isAbortError(error)) {
          return;
        }
        onLoadError(error);
      } finally {
        if (!outerGuard) {
          guard.finish();
        }
      }
    },
    [
      activeProjectIdRef,
      beginResourceRequest,
      onLoadError,
      onSnapshot,
    ],
  );

  return { loadProjectResources };
}

export async function fetchProjectResourceSnapshot(
  projectId: string,
  options?: RequestInit,
): Promise<ProjectResourceSnapshot> {
  const [
    papersResult,
    timelineResult,
    artifactSummariesResult,
    paperCardsResult,
    directionRunResult,
  ] = await Promise.allSettled([
    listProjectPapers(projectId, options),
    getProjectTimeline(projectId, options),
    listProjectArtifactSummaries(projectId, options),
    listProjectPaperCards(projectId, options),
    getLatestDirectionReviewRun(projectId, options),
  ]);
  const results = [
    papersResult,
    timelineResult,
    artifactSummariesResult,
    paperCardsResult,
    directionRunResult,
  ];
  const aborted = results.find(
    (result) =>
      result.status === "rejected" && isAbortError(result.reason),
  );
  if (aborted?.status === "rejected") {
    throw aborted.reason;
  }

  const snapshot: ProjectResourceSnapshot = { warnings: [] };
  if (papersResult.status === "fulfilled") {
    snapshot.papers = papersResult.value;
  } else {
    snapshot.warnings.push(
      projectResourceWarning("论文列表", papersResult.reason),
    );
  }
  if (timelineResult.status === "fulfilled") {
    snapshot.timeline = timelineResult.value;
  } else {
    snapshot.warnings.push(
      projectResourceWarning("运行时间线", timelineResult.reason),
    );
  }
  if (artifactSummariesResult.status === "fulfilled") {
    snapshot.artifactSummaries = artifactSummariesResult.value;
    snapshot.artifacts = await loadHydrationArtifacts(
      artifactSummariesResult.value,
      options,
    );
  } else {
    snapshot.warnings.push(
      projectResourceWarning(
        "Artifact 列表",
        artifactSummariesResult.reason,
      ),
    );
  }
  if (paperCardsResult.status === "fulfilled") {
    snapshot.paperCards = paperCardsResult.value;
  } else {
    snapshot.warnings.push(
      projectResourceWarning(
        "Paper Card 列表",
        paperCardsResult.reason,
      ),
    );
  }
  if (directionRunResult.status === "fulfilled") {
    snapshot.directionRun = directionRunResult.value;
  } else {
    snapshot.warnings.push(
      projectResourceWarning(
        "Direction Review 运行状态",
        directionRunResult.reason,
      ),
    );
  }
  return snapshot;
}

function projectResourceWarning(
  label: string,
  error: unknown,
): string {
  const normalized = normalizeApiError(error);
  return `${label}读取失败，其他项目数据已保留：${
    normalized.detail || normalized.message
  }`;
}
