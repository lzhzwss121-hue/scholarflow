import type { ApiSchema } from "./api.generated";

export type { ApiSchema, components, paths } from "./api.generated";

export const SCHOLARFLOW_VERSION = "0.1.0";
export type ResearchStage = "skeleton" | "static-workspace" | "api" | "agent-loop" | "workflow-run" | "literature-retrieval" | "direction-review" | "research-memory" | "paper-card" | "experiment-planning";
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
export type ApiProject = ApiSchema<"Project">;
export type ApiProjectCreate = ApiSchema<"ProjectCreate">;
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
    pdf_url?: string;
    doi?: string;
    arxiv_id?: string;
    openalex_id?: string;
    canonical_work_id?: string;
    relation: string;
    priority: string;
    code: string;
    relevance_score: number;
    relevance_quality?: "strong" | "medium" | "weak" | "off_topic";
    matched_terms?: string[];
    matched_terms_json?: string;
    review_required?: boolean;
    created_at: string;
}
export type ApiArtifact = ApiSchema<"Artifact">;
export type ApiArtifactSummary = ApiSchema<"ArtifactSummary">;
export type ApiArtifactSummaryPage = ApiSchema<"ArtifactSummaryPage">;
export type ApiArtifactRef = ApiSchema<"ArtifactRef">;
export type ApiWorkflowStepStatus = "idle" | "ready" | "running" | "partial" | "complete" | "blocked" | "error";
export interface ApiWorkflowStepState {
    step_id: string;
    status: ApiWorkflowStepStatus;
    label: string;
    summary: string;
    warnings: string[];
    errors: string[];
    artifact_refs: ApiArtifactRef[];
    updated_at: string;
}
export type ApiArtifactCreate = ApiSchema<"ArtifactCreate">;
export type ApiLiteratureSearchRequest = ApiSchema<"LiteratureSearchRequest">;
export interface ApiLiteratureSearchResponse {
    query: string;
    expanded_queries: string[];
    papers: ApiPaper[];
    artifact: ApiArtifact;
    errors: string[];
    relevance_coverage?: Record<string, number>;
    workflow_steps?: ApiWorkflowStepState[];
}
export type ApiPaperCardCreateRequest = ApiSchema<"PaperCardCreateRequest">;
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
    baseline: string;
    claim: string;
    limitation: string;
    prior_work_limitation?: string;
    contribution_type: string;
    contribution_evidence?: string;
    missing_signals: string[];
    signal_evidence?: Record<string, ApiSignalEvidence>;
}
export interface ApiSignalEvidence {
    field: string;
    canonical_value: string;
    raw_value: string;
    source: string;
    section: string;
    page: number | null;
    quote: string;
    confidence: string;
    validation_errors: string[];
    evidence_refs?: ApiSignalEvidenceRef[];
    availability?: "verified" | "partial" | "missing" | "invalid";
}
export interface ApiSignalEvidenceRef {
    canonical_value: string;
    raw_value: string;
    source: string;
    section: string;
    page: number | null;
    quote: string;
    confidence: string;
    validation_errors: string[];
}
export type ApiFullTextStatus = "extracted" | "supplemental_text" | "not_available" | "download_failed" | "parse_failed" | "disabled";
export type ApiEvidenceLevel = "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
export interface ApiEvidenceQualification {
    level: ApiEvidenceLevel;
    verified: boolean;
    source_origin: string;
    character_count: number;
    page_count: number;
    section_names: string[];
    reason: string;
}
export interface ApiFullTextProvenance {
    status: ApiFullTextStatus;
    pdf_url: string;
    source: string;
    page_count: number;
    character_count: number;
    error: string;
    failure_stage?: string;
    recovery_hint?: string;
    page_numbers?: number[];
    section_names?: string[];
    evidence_qualification?: ApiEvidenceQualification;
}
export interface ApiEvidenceSnippet {
    id: string;
    source: string;
    kind: string;
    text: string;
    note: string;
    confidence: string;
    section?: string;
    page?: number | null;
}
export interface ApiEvidencePack {
    evidence_level: string;
    confidence: string;
    source_confidence?: string;
    extraction_confidence?: string;
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
export interface ApiBaselineVerification {
    evidence_level: string;
    selection_basis: string;
    citation_status: string;
    citation_note: string;
    code_status: string;
    code_url: string;
    code_source: string;
    reproduction_status: string;
    checks: Record<string, string>;
    missing_evidence: string[];
    summary: string;
}
export interface ApiBaselineReference {
    title: string;
    year: string;
    venue: string;
    source: string;
    url: string;
    category: string;
    method_family?: string;
    reason: string;
    strengths: string;
    risks: string;
    evidence_snippets: ApiEvidenceSnippet[];
    confidence: string;
    evidence_gap: string;
    comparison_role?: string;
    actionability_status?: "ready" | "partial" | "blocked";
    next_action?: string;
    experiment_anchor?: Record<string, string>;
    verification?: ApiBaselineVerification;
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
    action_plan?: string[];
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
    paper_title?: string;
    artifact_id: string | null;
    source_artifact_title?: string;
    card_source?: "paper_table" | "direction_review_artifact" | "manual_unbound";
    evidence_level?: ApiEvidenceLevel;
    evidence_qualification?: ApiEvidenceQualification;
    full_text?: ApiFullTextProvenance;
    signals?: ApiPaperSignals;
    sections: ApiPaperCardSection[];
    weakest_assumption: string;
    minimal_reproduction: string;
    created_at: string;
    updated_at?: string;
}
export interface ApiPaperCardResponse {
    card: ApiPaperCard;
    artifact: ApiArtifact;
}
export interface ApiPaperFullTextExtractResponse {
    paper_id: string;
    text: string;
    evidence_level: ApiEvidenceLevel;
    evidence_quality: ApiEvidenceLevel;
    evidence_qualification: ApiEvidenceQualification;
    source: string;
    page_count: number;
    char_count: number;
    updated_at: string;
    full_text: ApiFullTextProvenance;
    card: ApiPaperCard | null;
    artifact: ApiArtifact | null;
}
export type ApiDirectionReviewRequest = ApiSchema<"DirectionReviewRequest">;
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
    paper_id?: string;
    paper_title?: string;
    artifact_id?: string | null;
    artifact_title?: string;
    updated_at?: string;
    abstract_translation: string;
    evidence_level?: ApiEvidenceLevel;
    evidence_qualification?: ApiEvidenceQualification;
    full_text?: ApiFullTextProvenance;
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
    schema_version?: string;
    direction: string;
    round: number;
    review_status: "complete" | "partial" | "blocked";
    target_paper_count: number;
    round_read_count: number;
    relevant_read_count?: number;
    low_relevance_count?: number;
    off_topic_count?: number;
    relevance_coverage?: Record<string, number>;
    total_read_count: number;
    scope?: ApiDirectionScope;
    baseline_map?: ApiBaselineMap;
    papers?: ApiDirectionPaperReading[];
    recommended_paper_ids: string[];
    direction_summary: string;
    artifact_refs: ApiArtifactRef[];
    artifacts?: ApiArtifact[];
    errors: string[];
    workflow_steps?: ApiWorkflowStepState[];
}
export type ApiWorkflowNoticeSeverity = "info" | "warning" | "error";
export interface ApiWorkflowNoticeMessage {
    severity: ApiWorkflowNoticeSeverity;
    code: string;
    stage: string;
    message: string;
    occurred_at: string;
}
export interface ApiDirectionReviewRunStatusResponse {
    run_id: string;
    project_id: string;
    direction: string;
    round: number;
    status: "queued" | "running" | "complete" | "partial" | "blocked" | "failed" | "cancelled";
    stage: "queued" | "scoping" | "retrieving" | "reading" | "curating" | "persisting" | "completed" | "failed" | "cancelled";
    progress: number;
    message: string;
    notices: ApiWorkflowNoticeMessage[];
    result: ApiDirectionReviewResponse | null;
    queued_at?: string;
    started_at?: string;
    current_tool?: string;
    last_heartbeat?: string;
    created_at: string;
    updated_at: string;
    completed_at: string | null;
}
export type ApiResearchDecisionRequest = ApiSchema<"ResearchDecisionRequest">;
export interface ApiGapDecision {
    id: string;
    title: string;
    kind: "true_gap" | "engineering_gap" | "pseudo_gap";
    evidence: string;
    weakness: string;
    opportunity: string;
    novelty_risk: "low" | "medium" | "high";
    feasibility: "one-week" | "one-month" | "thesis-scale";
    support_status?: "insufficient" | "single_source" | "corroborated" | "conflicted";
    confidence?: "low" | "medium" | "high";
    paper_ids?: string[];
    evidence_refs?: Array<{
        paper_id: string;
        paper_title: string;
        snippet_id: string;
        source: string;
        section: string;
        page: string;
        text: string;
        evidence_level: string;
    }>;
    validation_requirements?: string[];
    gap_signature?: Record<string, string>;
    consistency_score?: number;
    conflict_detected?: boolean;
}
export interface ApiIdeaValidation {
    idea: string;
    why_not_incremental: string;
    difference_from_existing_work: string;
    novelty_risk: "low" | "medium" | "high";
    feasibility: "one-week" | "one-month" | "thesis-scale";
    key_risks: string[];
}
export interface ApiDecisionIntent {
    raw_goal: string;
    focus: string;
    required_terms: string[];
    contrast_terms: string[];
    excluded_terms: string[];
    contribution_type: string;
    time_budget_days: number | null;
}
export interface ApiExperimentPlan {
    status: "ready" | "partial" | "blocked";
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
    unblock_suggestions: string[];
    goal_alignment?: Record<string, unknown>;
    readiness_checks?: Record<string, string>;
    assumptions?: string[];
}
export interface ApiResearchDecisionResponse {
    gaps: ApiGapDecision[];
    validation: ApiIdeaValidation;
    experiment: ApiExperimentPlan;
    artifacts: ApiArtifact[];
    decision_status?: "complete" | "partial" | "blocked";
    evidence_quality?: Record<string, unknown>;
    warnings?: string[];
    decision_intent?: ApiDecisionIntent | null;
    workflow_steps?: ApiWorkflowStepState[];
}
export type ApiResearchMemoryQueryRequest = ApiSchema<"ResearchMemoryQueryRequest">;
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
    matched_query_terms?: string[];
    query_coverage?: number;
    evidence_quality?: ApiEvidenceLevel;
    evidence_refs?: Array<{
        id: string;
        source: string;
        text: string;
        confidence: string;
        section?: string;
        page?: string;
    }>;
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
export interface ApiResearchMemoryClaim {
    id: string;
    facet?: string;
    statement: string;
    support_status: "corroborated" | "single_source" | "conflicted";
    confidence: "low" | "medium" | "high";
    paper_ids: string[];
    evidence_refs: Array<{
        paper_id: string;
        paper_title: string;
        snippet_id: string;
        source: string;
        section: string;
        page: string;
        text: string;
        confidence: string;
    }>;
}
export interface ApiResearchMemoryQueryResponse {
    schema_version?: string;
    question: string;
    top_k: number;
    answer: string;
    hits: ApiPaperMemoryHit[];
    direction_memory: ApiDirectionMemory | null;
    total_memories: number;
    reliability_status?: "reliable" | "no_reliable_hit" | "no_memory";
    reliability_reason?: string;
    answer_summary?: string;
    claims?: ApiResearchMemoryClaim[];
    unanswered_parts?: string[];
    query_coverage?: {
        anchor_terms?: string[];
        matched_terms?: string[];
        missing_terms?: string[];
        scientific_query?: string;
        answer_constraints?: string[];
        requested_facets?: string[];
        covered_facets?: string[];
        missing_facets?: string[];
        facet_status?: "covered" | "partial" | "uncovered" | "not_requested";
        coverage?: number;
        minimum_coverage?: number;
        status?: "covered" | "partial" | "uncovered";
    };
    source_chunks?: ApiRagSearchHit[];
    artifact: ApiArtifact;
    warnings: string[];
    workflow_steps?: ApiWorkflowStepState[];
}
export type ApiRagAnswerRequest = ApiSchema<"RagAnswerRequest">;
export interface ApiRagSearchHit {
    rank: number;
    citation_id: string;
    project_id: string;
    paper_id: string;
    paper_title: string;
    paper_authors: string;
    paper_year: string;
    paper_venue: string;
    paper_url: string;
    chunk_id: string;
    chunk_index: number;
    chunk_hash: string;
    doi?: string;
    arxiv_id?: string;
    openalex_id?: string;
    canonical_work_id?: string;
    duplicate_paper_ids?: string[];
    source: string;
    source_origin: string;
    evidence_level: ApiEvidenceLevel;
    evidence_verified?: boolean;
    parser_version?: string;
    section: string;
    page_start: number | null;
    page_end: number | null;
    text: string;
    bm25_score?: number;
    lexical_score: number;
    vector_score: number;
    hybrid_score: number;
    anchor_coverage: number;
    matched_query_terms: string[];
    stance?: "support_candidate" | "counterevidence" | "context";
    candidate_source?: "fts5_bm25" | "bounded_embedding_pool";
    match_strength: "strong" | "moderate" | "borderline";
    match_explanation: string;
}
export interface ApiRagSearchResponse {
    query: string;
    scientific_query?: string;
    answer_constraints?: string[];
    requested_facets?: string[];
    status: "complete" | "partial" | "no_reliable_hit" | "failed";
    retrieval_mode: "hybrid" | "lexical_only";
    provider: string;
    embedding_model: string;
    embedding_dimensions: number;
    external_data_transfer: boolean;
    candidate_chunks: number;
    fts_candidate_chunks?: number;
    vector_ready_chunks: number;
    returned_hits: number;
    top_k: number;
    min_score: number;
    query_anchor_terms: string[];
    rejected_by_relevance_gate: number;
    rejected_by_evidence_gate?: number;
    supporting_hits?: number;
    counterevidence_hits?: number;
    lexical_backend?: string;
    embedding_channel?: "lexical_hash" | "semantic_external" | "disabled";
    pipeline_stages?: string[];
    score_explanation: string;
    hits: ApiRagSearchHit[];
    warnings: string[];
}
export interface ApiRagAnswerClaim {
    id: string;
    statement: string;
    citation_ids: string[];
    confidence: "low" | "medium" | "high";
    evidence_level: ApiEvidenceLevel;
    verification: ApiRagClaimVerification;
}
export interface ApiRagClaimVerification {
    status: "supported" | "contradicted" | "insufficient" | "not_checked";
    method: "exact_quote" | "numeric_lexical" | "rule_based" | "model_checked" | "human";
    reasons: string[];
    citation_ids: string[];
    provider: string;
    model: string;
    prompt_version: string;
}
export interface ApiRagCitationValidation {
    available_citation_ids: string[];
    used_citation_ids: string[];
    rejected_citation_ids: string[];
    rejected_claim_count: number;
}
export interface ApiRagQualityCheck {
    id: string;
    label: string;
    status: "pass" | "warn" | "fail" | "not_applicable";
    detail: string;
    remediation: string;
}
export interface ApiRagQualityAssessment {
    evaluation_id: string;
    quality_status: "strong_evidence" | "review_required" | "safe_refusal" | "insufficient_evidence";
    score: number | null;
    metrics: Record<string, number>;
    checks: ApiRagQualityCheck[];
    strengths: string[];
    risk_flags: string[];
    human_review_required: boolean;
    disclaimer: string;
    evaluated_at: string;
}
export interface ApiRagAnswerResponse {
    question: string;
    status: "complete" | "partial" | "no_reliable_hit" | "failed";
    answer_kind: "grounded_synthesis" | "extractive_evidence" | "no_answer";
    answer: string;
    claims: ApiRagAnswerClaim[];
    unanswered_parts: string[];
    limitations: string[];
    retrieval: ApiRagSearchResponse;
    citations: ApiRagSearchHit[];
    citation_validation: ApiRagCitationValidation;
    generation_provider: string;
    generation_model: string;
    external_data_transfer: boolean;
    quality_assessment?: ApiRagQualityAssessment | null;
    artifact: ApiArtifact | null;
    warnings: string[];
}
export interface ApiRagEvaluationRecord {
    id: string;
    project_id: string;
    answer_artifact_id: string | null;
    question: string;
    answer_status: ApiRagAnswerResponse["status"];
    answer_kind: ApiRagAnswerResponse["answer_kind"];
    quality_status: ApiRagQualityAssessment["quality_status"];
    score: number | null;
    generation_provider: string;
    generation_model: string;
    assessment: ApiRagQualityAssessment;
    created_at: string;
}
export interface ApiRagEvaluationListResponse {
    project_id: string;
    total: number;
    evaluations: ApiRagEvaluationRecord[];
}
export type ApiAgentPlanRequest = ApiSchema<"AgentPlanRequest">;
export type ApiAgentExecuteRequest = ApiSchema<"AgentExecuteRequest">;
export type ApiAgentRunStatus = "planned" | "running" | "completed" | "completed_with_warnings" | "partial" | "failed" | "cancelled";
export interface ApiAgentPlanStep {
    id: string;
    title: string;
    detail: string;
    tool: string;
    status: "done" | "running" | "queued" | "partial" | "blocked" | "failed" | "cancelled";
    metrics?: Record<string, unknown>;
}
export interface ApiModelCallAudit {
    provider: string;
    model: string;
    purpose: string;
    prompt_version: string;
    request_timestamp: string;
    latency_ms: number;
    response_status: string;
    fallback_reason: string;
    requested_provider: string;
    requested_model: string;
    external_data_sent: boolean;
    estimated_cost_usd?: number | null;
}
export interface ApiAgentPlanResponse {
    run_id: string;
    project_id: string;
    session_id: string;
    task: string;
    provider: string;
    run_kind: "research_workflow";
    agent_label: "Bounded Research Agent";
    execution_mode: "bounded_observe_reason_act" | "deterministic_tool_graph";
    model_call?: ApiModelCallAudit;
    status: ApiAgentRunStatus;
    rationale: string;
    steps: ApiAgentPlanStep[];
    artifact: ApiArtifact;
}
export interface ApiAgentExecuteResponse {
    run_id: string;
    run_kind?: "research_workflow";
    agent_label?: "Bounded Research Agent";
    execution_mode?: "bounded_observe_reason_act" | "deterministic_tool_graph";
    model_call?: ApiModelCallAudit | null;
    status: ApiAgentRunStatus;
    artifact?: ApiArtifact | null;
    papers: Array<Record<string, unknown>>;
    paper_count: number;
    summary_metrics: Record<string, unknown>;
    run_status_summary?: string;
    warnings?: string[];
    artifact_refs?: ApiArtifactRef[];
    workflow_steps?: ApiWorkflowStepState[];
    steps: ApiAgentPlanStep[];
    queued_at?: string;
    started_at?: string;
    completed_at?: string | null;
    current_tool?: string;
    last_heartbeat?: string;
    updated_at?: string;
}
export interface ApiAgentRunStatusResponse {
    run_id: string;
    run_kind?: "research_workflow";
    agent_label?: "Bounded Research Agent";
    execution_mode?: "bounded_observe_reason_act" | "deterministic_tool_graph";
    model_call?: ApiModelCallAudit | null;
    status: ApiAgentRunStatus;
    steps: ApiAgentPlanStep[];
    summary_metrics: Record<string, unknown>;
    warnings: string[];
    artifact_refs: ApiArtifactRef[];
    workflow_steps: ApiWorkflowStepState[];
    run_status_summary?: string;
    current_tool?: string;
    papers?: Array<Record<string, unknown>>;
    paper_count: number;
    artifact?: ApiArtifact | null;
    queued_at?: string;
    started_at?: string;
    completed_at?: string | null;
    last_heartbeat?: string;
    updated_at: string;
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
    status: "done" | "running" | "queued" | "partial" | "blocked" | "failed" | "cancelled";
    summary: string;
    created_at: string;
}
