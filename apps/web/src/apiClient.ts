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

export function getHealth() {
  return request<ApiHealth>("/health");
}

export function listProjects() {
  return request<ApiProject[]>("/projects");
}

export function createProject(payload: ApiProjectCreate) {
  return request<ApiProject>("/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listProjectPapers(projectId: string) {
  return request<ApiPaper[]>(`/projects/${projectId}/papers`);
}

export function searchProjectLiterature(projectId: string, payload: ApiLiteratureSearchRequest) {
  return request<ApiLiteratureSearchResponse>(`/projects/${projectId}/literature/search`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createProjectPaperCard(projectId: string, payload: ApiPaperCardCreateRequest) {
  return request<ApiPaperCardResponse>(`/projects/${projectId}/paper-cards`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createDirectionReview(projectId: string, payload: ApiDirectionReviewRequest) {
  return request<ApiDirectionReviewResponse>(`/projects/${projectId}/direction-reviews`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createResearchDecisions(projectId: string, payload: ApiResearchDecisionRequest = {}) {
  return request<ApiResearchDecisionResponse>(`/projects/${projectId}/research-decisions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function queryResearchMemory(projectId: string, payload: ApiResearchMemoryQueryRequest) {
  return request<ApiResearchMemoryQueryResponse>(`/projects/${projectId}/research-memory/query`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listProjectArtifacts(projectId: string) {
  return request<ApiArtifact[]>(`/projects/${projectId}/artifacts`);
}

export function listProjectArtifactSummaries(projectId: string) {
  return request<ApiArtifactSummary[]>(`/projects/${projectId}/artifacts/summary`);
}

export function saveArtifact(payload: ApiArtifactCreate) {
  return request<ApiArtifact>("/artifacts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getArtifact(artifactId: string) {
  return request<ApiArtifact>(`/artifacts/${artifactId}`);
}

export function getProjectTimeline(projectId: string) {
  return request<ApiToolEvent[]>(`/projects/${projectId}/timeline`);
}

export function createAgentPlan(payload: ApiAgentPlanRequest) {
  return request<ApiAgentPlanResponse>("/agent/plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function executeAgentRun(runId: string, payload: ApiAgentExecuteRequest = { confirmed: true }) {
  return request<ApiAgentExecuteResponse>(`/agent/runs/${runId}/execute`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
