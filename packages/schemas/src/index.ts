export const SCHOLARFLOW_VERSION = "0.1.0";

export type ResearchStage =
  | "skeleton"
  | "static-workspace"
  | "api"
  | "agent-loop"
  | "literature-retrieval"
  | "paper-card"
  | "experiment-planning";

export interface ProjectSummary {
  id: string;
  title: string;
  stage: ResearchStage;
}

export interface ApiHealth {
  status: "ok";
  service: "scholarflow-api";
  version: string;
}

export interface ApiProject {
  id: string;
  title: string;
  description: string;
  keyword: string;
  field: string;
  language: string;
  workflow: string;
  stage: string;
  active_session_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiProjectCreate {
  title: string;
  description?: string;
  keyword?: string;
  field?: string;
  language?: string;
  workflow?: string;
}

export interface ApiPaper {
  id: string;
  project_id: string;
  title: string;
  authors: string;
  abstract: string;
  year: string;
  type: string;
  venue: string;
  source: string;
  url: string;
  relation: string;
  priority: string;
  code: string;
  relevance_score: number;
  created_at: string;
}

export interface ApiArtifact {
  id: string;
  project_id: string;
  title: string;
  kind: string;
  content_markdown: string;
  content_json: string;
  diff: string;
  created_at: string;
  updated_at: string;
}

export interface ApiArtifactCreate {
  project_id: string;
  title: string;
  kind?: string;
  content_markdown?: string;
  content_json?: string;
  diff?: string;
}

export interface ApiLiteratureSearchRequest {
  query: string;
  max_results?: number;
  sources?: Array<"arxiv" | "openalex">;
}

export interface ApiLiteratureSearchResponse {
  query: string;
  expanded_queries: string[];
  papers: ApiPaper[];
  artifact: ApiArtifact;
  errors: string[];
}

export interface ApiPaperCardCreateRequest {
  paper_id?: string | null;
  title?: string;
  abstract?: string;
  paper_text?: string;
}

export interface ApiPaperCardSection {
  id: string;
  title: string;
  content: string;
}

export interface ApiPaperCard {
  id: string;
  project_id: string;
  paper_id: string | null;
  artifact_id: string | null;
  sections: ApiPaperCardSection[];
  weakest_assumption: string;
  minimal_reproduction: string;
  created_at: string;
}

export interface ApiPaperCardResponse {
  card: ApiPaperCard;
  artifact: ApiArtifact;
}

export interface ApiResearchDecisionRequest {
  goal?: string;
}

export interface ApiGapDecision {
  id: string;
  title: string;
  kind: "true_gap" | "engineering_gap" | "pseudo_gap";
  evidence: string;
  weakness: string;
  opportunity: string;
  novelty_risk: "low" | "medium" | "high";
  feasibility: "one-week" | "one-month" | "thesis-scale";
}

export interface ApiIdeaValidation {
  idea: string;
  why_not_incremental: string;
  difference_from_existing_work: string;
  novelty_risk: "low" | "medium" | "high";
  feasibility: "one-week" | "one-month" | "thesis-scale";
  key_risks: string[];
}

export interface ApiExperimentPlan {
  claim: string;
  dataset: string;
  baseline: string;
  metrics: string[];
  ablations: string[];
  resources: string;
  timeline: string[];
  success_criterion: string;
  failure_criterion: string;
}

export interface ApiResearchDecisionResponse {
  gaps: ApiGapDecision[];
  validation: ApiIdeaValidation;
  experiment: ApiExperimentPlan;
  artifacts: ApiArtifact[];
}

export interface ApiAgentPlanRequest {
  project_id: string;
  task: string;
  provider?: string;
}

export interface ApiAgentExecuteRequest {
  confirmed?: boolean;
}

export interface ApiAgentPlanStep {
  id: string;
  title: string;
  detail: string;
  tool: string;
  status: "done" | "running" | "queued";
}

export interface ApiAgentPlanResponse {
  run_id: string;
  project_id: string;
  session_id: string;
  task: string;
  provider: string;
  status: "planned" | "running" | "completed";
  rationale: string;
  steps: ApiAgentPlanStep[];
  artifact: ApiArtifact;
}

export interface ApiAgentExecuteResponse {
  run_id: string;
  status: "completed";
  artifact: ApiArtifact;
  papers: Array<Record<string, string>>;
  steps: ApiAgentPlanStep[];
}

export interface ApiSession {
  id: string;
  project_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApiToolEvent {
  id: string;
  session_id: string;
  time_label: string;
  tool: string;
  status: "done" | "running" | "queued";
  summary: string;
  created_at: string;
}
