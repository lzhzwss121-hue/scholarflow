import type {
  ApiArtifact,
  ApiArtifactCreate,
  ApiHealth,
  ApiPaper,
  ApiProject,
  ApiProjectCreate,
  ApiToolEvent,
} from "@scholarflow/schemas";

const API_BASE_URL = "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `ScholarFlow API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
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

export function listProjectArtifacts(projectId: string) {
  return request<ApiArtifact[]>(`/projects/${projectId}/artifacts`);
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

