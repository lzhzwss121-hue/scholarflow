import type {
  ApiAgentExecuteRequest,
  ApiAgentExecuteResponse,
  ApiAgentPlanRequest,
  ApiAgentPlanResponse,
  ApiArtifact,
  ApiArtifactCreate,
  ApiArtifactSummary,
  ApiDirectionReviewRequest,
  ApiDirectionReviewResponse,
  ApiHealth,
  ApiLiteratureSearchRequest,
  ApiLiteratureSearchResponse,
  ApiPaper,
  ApiPaperCardCreateRequest,
  ApiPaperCardResponse,
  ApiProject,
  ApiProjectCreate,
  ApiResearchDecisionRequest,
  ApiResearchDecisionResponse,
  ApiResearchMemoryQueryRequest,
  ApiResearchMemoryQueryResponse,
  ApiToolEvent,
} from "@scholarflow/schemas";

const API_BASE_URL = import.meta.env.VITE_SCHOLARFLOW_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_REQUEST_TIMEOUT_MS = readPositiveIntegerEnv(import.meta.env.VITE_SCHOLARFLOW_API_TIMEOUT_MS, 30000);

export type ScholarFlowApiErrorKind =
  | "timeout"
  | "offline"
  | "validation"
  | "backend"
  | "retrieval-degraded"
  | "aborted"
  | "unknown";

export class ScholarFlowApiError extends Error {
  readonly status?: number;
  readonly path: string;
  readonly detail: string;

  constructor(message: string, options: { path: string; status?: number; detail?: string }) {
    super(message);
    this.name = "ScholarFlowApiError";
    this.status = options.status;
    this.path = options.path;
    this.detail = options.detail ?? "";
  }
}

export type ApiErrorView = {
  kind: ScholarFlowApiErrorKind;
  message: string;
  detail: string;
  status?: number;
  path?: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);
  const upstreamSignal = options?.signal;
  const abortFromUpstream = () => controller.abort(upstreamSignal?.reason);

  if (upstreamSignal?.aborted) {
    controller.abort(upstreamSignal.reason);
  } else {
    upstreamSignal?.addEventListener("abort", abortFromUpstream, { once: true });
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const detail = await readResponseDetail(response);
      throw new ScholarFlowApiError(formatApiError(path, response.status, detail), {
        path,
        status: response.status,
        detail,
      });
    }

    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ScholarFlowApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      if (upstreamSignal?.aborted) {
        throw new ScholarFlowApiError(`ScholarFlow API request was cancelled: ${path}`, {
          path,
          detail: "aborted",
        });
      }
      throw new ScholarFlowApiError(
        `ScholarFlow API request timed out after ${Math.round(API_REQUEST_TIMEOUT_MS / 1000)}s: ${path}`,
        { path, detail: "timeout" },
      );
    }
    const detail = error instanceof Error ? error.message : String(error);
    throw new ScholarFlowApiError(`ScholarFlow API request failed before response: ${path}. ${detail}`, {
      path,
      detail,
    });
  } finally {
    window.clearTimeout(timeoutId);
    upstreamSignal?.removeEventListener("abort", abortFromUpstream);
  }
}

function readPositiveIntegerEnv(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function readResponseDetail(response: Response) {
  const raw = await response.text();
  if (!raw.trim()) {
    return "";
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return raw;
  }
  try {
    return stringifyApiDetail(JSON.parse(raw));
  } catch {
    return raw;
  }
}

function stringifyApiDetail(payload: unknown): string {
  if (typeof payload === "string") {
    return payload;
  }
  if (Array.isArray(payload)) {
    return payload.map(stringifyApiDetail).filter(Boolean).join("; ");
  }
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if ("detail" in record) {
      return stringifyApiDetail(record.detail);
    }
    if (typeof record.message === "string") {
      return record.message;
    }
    return JSON.stringify(record);
  }
  return String(payload);
}

function formatApiError(path: string, status: number, detail: string) {
  const suffix = detail ? ` ${detail}` : "";
  return `ScholarFlow API request failed: ${path} returned ${status}.${suffix}`;
}

export function normalizeApiError(error: unknown): ApiErrorView {
  if (error instanceof ScholarFlowApiError) {
    const detail = error.detail || error.message;
    return {
      kind: classifyApiError(error),
      message: error.message,
      detail,
      status: error.status,
      path: error.path,
    };
  }
  const detail = error instanceof Error ? error.message : String(error);
  return {
    kind: "unknown",
    message: detail || "未知错误",
    detail,
  };
}

export function isAbortError(error: unknown): boolean {
  return error instanceof ScholarFlowApiError && error.detail === "aborted";
}

export function isRetrievalWarning(value: string): boolean {
  const normalized = value.toLowerCase();
  return [
    "using_cached_results",
    "openalex_cooldown",
    "arxiv_rate_limited",
    "low_recall",
    "relevance_coverage",
    "too many requests",
    "503",
    "504",
    "retrieval",
  ].some((marker) => normalized.includes(marker));
}

function classifyApiError(error: ScholarFlowApiError): ScholarFlowApiErrorKind {
  const detail = error.detail.toLowerCase();
  const message = error.message.toLowerCase();
  if (detail === "aborted") {
    return "aborted";
  }
  if (detail === "timeout" || message.includes("timed out")) {
    return "timeout";
  }
  if (!error.status) {
    return "offline";
  }
  if (error.status >= 400 && error.status < 500) {
    return "validation";
  }
  if (isRetrievalWarning(detail) || isRetrievalWarning(message)) {
    return "retrieval-degraded";
  }
  if (error.status >= 500) {
    return "backend";
  }
  return "unknown";
}

export function getHealth(options?: RequestInit) {
  return request<ApiHealth>("/health", options);
}

export function listProjects(options?: RequestInit) {
  return request<ApiProject[]>("/projects", options);
}

export function createProject(payload: ApiProjectCreate, options?: RequestInit) {
  return request<ApiProject>("/projects", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listProjectPapers(projectId: string, options?: RequestInit) {
  return request<ApiPaper[]>(`/projects/${projectId}/papers`, options);
}

export function searchProjectLiterature(projectId: string, payload: ApiLiteratureSearchRequest, options?: RequestInit) {
  return request<ApiLiteratureSearchResponse>(`/projects/${projectId}/literature/search`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createProjectPaperCard(projectId: string, payload: ApiPaperCardCreateRequest, options?: RequestInit) {
  return request<ApiPaperCardResponse>(`/projects/${projectId}/paper-cards`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createDirectionReview(projectId: string, payload: ApiDirectionReviewRequest, options?: RequestInit) {
  return request<ApiDirectionReviewResponse>(`/projects/${projectId}/direction-reviews`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createResearchDecisions(projectId: string, payload: ApiResearchDecisionRequest = {}, options?: RequestInit) {
  return request<ApiResearchDecisionResponse>(`/projects/${projectId}/research-decisions`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function queryResearchMemory(projectId: string, payload: ApiResearchMemoryQueryRequest, options?: RequestInit) {
  return request<ApiResearchMemoryQueryResponse>(`/projects/${projectId}/research-memory/query`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listProjectArtifacts(projectId: string, options?: RequestInit) {
  return request<ApiArtifact[]>(`/projects/${projectId}/artifacts`, options);
}

export function listProjectArtifactSummaries(projectId: string, options?: RequestInit) {
  return request<ApiArtifactSummary[]>(`/projects/${projectId}/artifacts/summary`, options);
}

export function saveArtifact(payload: ApiArtifactCreate, options?: RequestInit) {
  return request<ApiArtifact>("/artifacts", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getArtifact(artifactId: string, options?: RequestInit) {
  return request<ApiArtifact>(`/artifacts/${artifactId}`, options);
}

export function getProjectTimeline(projectId: string, options?: RequestInit) {
  return request<ApiToolEvent[]>(`/projects/${projectId}/timeline`, options);
}

export function createAgentPlan(payload: ApiAgentPlanRequest, options?: RequestInit) {
  return request<ApiAgentPlanResponse>("/agent/plan", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function executeAgentRun(runId: string, payload: ApiAgentExecuteRequest = { confirmed: true }, options?: RequestInit) {
  return request<ApiAgentExecuteResponse>(`/agent/runs/${runId}/execute`, {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}
