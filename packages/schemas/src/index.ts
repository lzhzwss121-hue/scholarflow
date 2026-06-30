export const SCHOLARFLOW_VERSION = "0.1.0";

export type ResearchStage =
  | "skeleton"
  | "static-workspace"
  | "api"
  | "agent-loop"
  | "literature-retrieval"
  | "direction-review"
  | "research-memory"
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

export interface ApiPaperSignals {
  task: string;
  method: string;
  dataset: string;
  metric: string;
  claim: string;
  limitation: string;
  contribution_type: string;
  missing_signals: string[];
}

export interface ApiEvidenceSnippet {
  id: string;
  source: string;
  kind: string;
  text: string;
  note: string;
  confidence: string;
}

export interface ApiEvidencePack {
  evidence_level: string;
  confidence: string;
  snippets: ApiEvidenceSnippet[];
  missing_evidence: string[];
  grounding_summary: string;
}

export interface ApiResearchSightJudgment {
  field: string;
  evidence_snippet_id: string;
  confidence: string;
  rationale: string;
}

export interface ApiBaselineReference {
  title: string;
  year: string;
  venue: string;
  source: string;
  url: string;
  category: string;
  reason: string;
  strengths: string;
  risks: string;
  evidence_snippets: ApiEvidenceSnippet[];
  confidence: string;
  evidence_gap: string;
}

export interface ApiBaselineMap {
  direction: string;
  task_definition: string;
  classic_baselines: ApiBaselineReference[];
  recent_strong_baselines: ApiBaselineReference[];
  alternative_paradigms: ApiBaselineReference[];
  common_benchmarks: string[];
  evaluation_risks: string[];
  open_questions: string[];
  generated_from: string[];
  evidence_summary: string;
  curator_notes: string;
}

export interface ApiResearchSight {
  motivation_sharpness: string;
  solution_elegance: string;
  evaluation_integrity: string;
  paradigm_inspiration: string;
  why_good: string;
  why_not_good: string;
  better_angle: string;
  baseline_comparison: string;
  next_step_proposal: string;
  evidence_pack: ApiEvidencePack;
  critique_evidence: ApiResearchSightJudgment[];
}

export interface ApiPaperCard {
  id: string;
  project_id: string;
  paper_id: string | null;
  artifact_id: string | null;
  signals?: ApiPaperSignals;
  sections: ApiPaperCardSection[];
  weakest_assumption: string;
  minimal_reproduction: string;
  created_at: string;
}

export interface ApiPaperCardResponse {
  card: ApiPaperCard;
  artifact: ApiArtifact;
}

export interface ApiDirectionReviewRequest {
  direction: string;
  round?: number;
}

export interface ApiDirectionScope {
  direction: string;
  round: number;
  year_range: string;
  included_scope: string;
  excluded_scope: string;
  subtopics: string[];
  queries: string[];
}

export interface ApiDirectionPaperReading {
  paper: ApiPaper;
  abstract_translation: string;
  signals?: ApiPaperSignals;
  sections: ApiPaperCardSection[];
  research_sight: ApiResearchSight;
  weakest_assumption: string;
  minimal_reproduction: string;
  counterexample: string;
  follow_up_idea: string;
  why_selected: string;
  venue_signal: string;
  self_read_priority: boolean;
}

export interface ApiDirectionReviewResponse {
  direction: string;
  round: number;
  total_read_count: number;
  scope: ApiDirectionScope;
  baseline_map: ApiBaselineMap;
  papers: ApiDirectionPaperReading[];
  recommended_paper_ids: string[];
  direction_summary: string;
  artifacts: ApiArtifact[];
  errors: string[];
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
  status: "ready" | "blocked";
  anchor_paper_id: string;
  anchor_paper_title: string;
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

export interface ApiResearchMemoryQueryRequest {
  question: string;
  direction?: string;
  top_k?: number;
}

export interface ApiPaperMemoryHit {
  paper: ApiPaper;
  direction: string;
  round: number;
  score: number;
  title_score: number;
  keyword_score: number;
  section_score: number;
  priority_score: number;
  snippets: string[];
  abstract_translation: string;
  weakest_assumption: string;
  minimal_reproduction: string;
  counterexample: string;
  follow_up_idea: string;
  why_selected: string;
  research_sight: ApiResearchSight;
  self_read_priority: boolean;
}

export interface ApiDirectionMemory {
  direction: string;
  total_papers: number;
  round_count: number;
  summary: string;
  paper_ids: string[];
  baseline_map?: ApiBaselineMap | null;
  updated_at: string;
}

export interface ApiResearchMemoryQueryResponse {
  question: string;
  top_k: number;
  answer: string;
  hits: ApiPaperMemoryHit[];
  direction_memory: ApiDirectionMemory | null;
  total_memories: number;
  artifact: ApiArtifact;
  warnings: string[];
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
  papers: Array<Record<string, unknown>>;
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
