from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator


EvidenceLevel = Literal["metadata_only", "abstract_only", "full_text"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    keyword: str = ""
    field: str = ""
    language: str = "zh-CN"
    workflow: str = "survey-to-experiment"


class Project(BaseModel):
    id: str
    title: str
    description: str
    keyword: str
    field: str
    language: str
    workflow: str
    stage: str
    active_session_id: str | None
    created_at: str
    updated_at: str
    is_demo: bool = False


class Paper(BaseModel):
    id: str
    project_id: str
    title: str
    authors: str
    abstract: str
    year: str
    type: str
    venue: str
    source: str
    url: str
    pdf_url: str = ""
    relation: str
    priority: str
    code: str
    relevance_score: float
    relevance_quality: Literal["strong", "medium", "weak", "off_topic"] = "medium"
    matched_terms: list[str] = Field(default_factory=list)
    matched_terms_json: str = "[]"
    review_required: bool = False
    created_at: str

    @model_validator(mode="before")
    @classmethod
    def hydrate_matched_terms(cls, data):
        if isinstance(data, dict) and "matched_terms" not in data:
            try:
                parsed = json.loads(str(data.get("matched_terms_json") or "[]"))
            except json.JSONDecodeError:
                parsed = []
            data = dict(data)
            data["matched_terms"] = [str(item) for item in parsed] if isinstance(parsed, list) else []
        return data


class ArtifactCreate(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    kind: str = "markdown"
    content_markdown: str = ""
    content_json: str = ""
    diff: str = ""


class Artifact(BaseModel):
    id: str
    project_id: str
    title: str
    kind: str
    content_markdown: str
    content_json: str
    diff: str
    created_at: str
    updated_at: str


class ArtifactSummary(BaseModel):
    id: str
    project_id: str
    title: str
    kind: str
    created_at: str
    updated_at: str
    markdown_bytes: int
    json_bytes: int
    markdown_preview: str
    json_schema_version: str


class ArtifactRef(BaseModel):
    id: str
    title: str
    kind: str
    created_at: str


class WorkflowStepState(BaseModel):
    step_id: str
    status: Literal["idle", "ready", "running", "partial", "complete", "blocked", "error"]
    label: str
    summary: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    updated_at: str


class LiteratureSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=12, ge=1, le=30)
    sources: list[Literal["arxiv", "openalex"]] = Field(default_factory=lambda: ["arxiv", "openalex"])


class LiteratureSearchResponse(BaseModel):
    query: str
    expanded_queries: list[str]
    papers: list[Paper]
    artifact: Artifact
    errors: list[str]
    relevance_coverage: dict[str, int] = Field(default_factory=dict)
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)


class PaperCardCreateRequest(BaseModel):
    paper_id: str | None = None
    title: str = ""
    abstract: str = ""
    paper_text: str = Field(default="", max_length=50000)


class PaperCardSection(BaseModel):
    id: str
    title: str
    content: str


class SignalEvidence(BaseModel):
    field: str = ""
    canonical_value: str = ""
    raw_value: str = ""
    source: str = ""
    section: str = ""
    page: int | None = None
    quote: str = ""
    confidence: str = ""
    validation_errors: list[str] = Field(default_factory=list)


class PaperSignals(BaseModel):
    task: str = ""
    method: str = ""
    dataset: str = ""
    metric: str = ""
    baseline: str = ""
    claim: str = ""
    limitation: str = ""
    prior_work_limitation: str = ""
    contribution_type: str = ""
    contribution_evidence: str = ""
    missing_signals: list[str] = Field(default_factory=list)
    signal_evidence: dict[str, SignalEvidence] = Field(default_factory=dict)


class FullTextProvenance(BaseModel):
    status: Literal[
        "extracted",
        "not_available",
        "download_failed",
        "parse_failed",
        "disabled",
    ] = "not_available"
    pdf_url: str = ""
    source: str = ""
    page_count: int = 0
    character_count: int = 0
    error: str = ""
    failure_stage: str = ""
    recovery_hint: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    section_names: list[str] = Field(default_factory=list)


class EvidenceSnippet(BaseModel):
    id: str = ""
    source: str = ""
    kind: str = ""
    text: str = ""
    note: str = ""
    confidence: str = ""
    section: str = ""
    page: int | None = None


class EvidencePack(BaseModel):
    evidence_level: str = ""
    confidence: str = ""
    source_confidence: str = ""
    extraction_confidence: str = ""
    snippets: list[EvidenceSnippet] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    grounding_summary: str = ""


class ResearchSightJudgment(BaseModel):
    field: str = ""
    evidence_snippet_id: str = ""
    confidence: str = ""
    rationale: str = ""


class BaselineReference(BaseModel):
    title: str
    year: str
    venue: str
    source: str
    url: str
    category: str
    reason: str
    strengths: str
    risks: str
    evidence_snippets: list[EvidenceSnippet] = Field(default_factory=list)
    confidence: str = ""
    evidence_gap: str = ""


class BaselineMap(BaseModel):
    direction: str
    task_definition: str
    classic_baselines: list[BaselineReference]
    recent_strong_baselines: list[BaselineReference]
    alternative_paradigms: list[BaselineReference]
    common_benchmarks: list[str]
    evaluation_risks: list[str]
    open_questions: list[str]
    generated_from: list[str]
    evidence_summary: str = ""
    curator_notes: str


class ResearchSight(BaseModel):
    motivation_sharpness: str
    solution_elegance: str
    evaluation_integrity: str
    paradigm_inspiration: str
    why_good: str
    why_not_good: str
    better_angle: str
    baseline_comparison: str
    next_step_proposal: str
    evidence_pack: EvidencePack = Field(default_factory=EvidencePack)
    critique_evidence: list[ResearchSightJudgment] = Field(default_factory=list)


class PaperCard(BaseModel):
    id: str
    project_id: str
    paper_id: str | None
    paper_title: str = ""
    artifact_id: str | None
    source_artifact_title: str = ""
    card_source: Literal["paper_table", "direction_review_artifact", "manual_unbound"] = "paper_table"
    evidence_level: EvidenceLevel = "metadata_only"
    full_text: FullTextProvenance = Field(default_factory=FullTextProvenance)
    signals: PaperSignals = Field(default_factory=PaperSignals)
    sections: list[PaperCardSection]
    weakest_assumption: str
    minimal_reproduction: str
    created_at: str
    updated_at: str = ""


class PaperCardResponse(BaseModel):
    card: PaperCard
    artifact: Artifact


class PaperFullTextExtractResponse(BaseModel):
    paper_id: str
    text: str = ""
    evidence_level: EvidenceLevel = "metadata_only"
    evidence_quality: EvidenceLevel = "metadata_only"
    source: str = ""
    page_count: int = 0
    char_count: int = 0
    updated_at: str = ""
    full_text: FullTextProvenance = Field(default_factory=FullTextProvenance)
    card: PaperCard | None = None
    artifact: Artifact | None = None


class DirectionReviewRequest(BaseModel):
    direction: str = Field(min_length=1, max_length=500)
    round: int = Field(default=1, ge=1, le=3)


class DirectionScope(BaseModel):
    direction: str
    round: int
    year_range: str
    included_scope: str
    excluded_scope: str
    subtopics: list[str]
    queries: list[str]


class DirectionPaperReading(BaseModel):
    paper: Paper
    abstract_translation: str
    evidence_level: EvidenceLevel = "metadata_only"
    full_text: FullTextProvenance = Field(default_factory=FullTextProvenance)
    signals: PaperSignals = Field(default_factory=PaperSignals)
    sections: list[PaperCardSection]
    research_sight: ResearchSight
    weakest_assumption: str
    minimal_reproduction: str
    counterexample: str
    follow_up_idea: str
    why_selected: str
    venue_signal: str
    self_read_priority: bool


class DirectionReviewResponse(BaseModel):
    direction: str
    round: int
    review_status: Literal["complete", "partial", "blocked"] = "complete"
    target_paper_count: int = 10
    round_read_count: int
    relevant_read_count: int = 0
    low_relevance_count: int = 0
    off_topic_count: int = 0
    relevance_coverage: dict[str, int] = Field(default_factory=dict)
    total_read_count: int
    recommended_paper_ids: list[str]
    direction_summary: str
    artifact_refs: list[ArtifactRef]
    errors: list[str]
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)


class ResearchDecisionRequest(BaseModel):
    goal: str = Field(default="", max_length=1000)


class GapDecision(BaseModel):
    id: str
    title: str
    kind: Literal["true_gap", "engineering_gap", "pseudo_gap"]
    evidence: str
    weakness: str
    opportunity: str
    novelty_risk: Literal["low", "medium", "high"]
    feasibility: Literal["one-week", "one-month", "thesis-scale"]


class IdeaValidation(BaseModel):
    idea: str
    why_not_incremental: str
    difference_from_existing_work: str
    novelty_risk: Literal["low", "medium", "high"]
    feasibility: Literal["one-week", "one-month", "thesis-scale"]
    key_risks: list[str]


class DecisionIntent(BaseModel):
    raw_goal: str = ""
    focus: str = ""
    required_terms: list[str] = Field(default_factory=list)
    contrast_terms: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    contribution_type: str = "unspecified"
    time_budget_days: int | None = None


class ExperimentPlan(BaseModel):
    status: Literal["ready", "blocked"] = "ready"
    anchor_paper_id: str = ""
    anchor_paper_title: str = ""
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    ablations: list[str]
    resources: str
    timeline: list[str]
    success_criterion: str
    failure_criterion: str
    unblock_suggestions: list[str] = Field(default_factory=list)
    goal_alignment: dict[str, object] = Field(default_factory=dict)
    readiness_checks: dict[str, str] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class ResearchDecisionResponse(BaseModel):
    gaps: list[GapDecision]
    validation: IdeaValidation
    experiment: ExperimentPlan
    artifacts: list[Artifact]
    decision_status: Literal["complete", "partial", "blocked"] = "complete"
    evidence_quality: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    decision_intent: DecisionIntent | None = None
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)


class ResearchMemoryQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    direction: str = Field(default="", max_length=500)
    top_k: int = Field(default=5, ge=3, le=8)


class PaperMemoryHit(BaseModel):
    paper: Paper
    direction: str
    round: int
    score: float
    title_score: float = 0.0
    keyword_score: float = 0.0
    section_score: float = 0.0
    priority_score: float = 0.0
    snippets: list[str]
    evidence_quality: Literal["metadata_only", "abstract_only", "full_text"] = "metadata_only"
    evidence_refs: list[dict[str, str]] = Field(default_factory=list)
    abstract_translation: str
    weakest_assumption: str
    minimal_reproduction: str
    counterexample: str
    follow_up_idea: str
    why_selected: str
    research_sight: ResearchSight
    self_read_priority: bool


class DirectionMemory(BaseModel):
    direction: str
    total_papers: int
    round_count: int
    summary: str
    paper_ids: list[str]
    baseline_map: BaselineMap | None = None
    updated_at: str


class ResearchMemoryClaim(BaseModel):
    id: str
    statement: str
    support_status: Literal["corroborated", "single_source", "conflicted"]
    confidence: Literal["low", "medium", "high"]
    paper_ids: list[str]
    evidence_refs: list[dict[str, str]] = Field(default_factory=list)


class ResearchMemoryQueryResponse(BaseModel):
    question: str
    top_k: int
    answer: str
    hits: list[PaperMemoryHit]
    direction_memory: DirectionMemory | None
    total_memories: int
    reliability_status: str = "reliable"
    reliability_reason: str = ""
    answer_summary: str = ""
    claims: list[ResearchMemoryClaim] = Field(default_factory=list)
    unanswered_parts: list[str] = Field(default_factory=list)
    artifact: Artifact
    warnings: list[str]
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)


class AgentPlanRequest(BaseModel):
    project_id: str
    task: str = Field(min_length=1, max_length=1000)
    provider: str = "openrouter"


class AgentExecuteRequest(BaseModel):
    confirmed: bool = True


AgentRunStatusLiteral = Literal[
    "planned",
    "running",
    "completed",
    "completed_with_warnings",
    "partial",
    "failed",
    "cancelled",
]

ToolEventStatusLiteral = Literal[
    "done",
    "running",
    "queued",
    "partial",
    "blocked",
    "failed",
    "cancelled",
]


class AgentPlanStep(BaseModel):
    id: str
    title: str
    detail: str
    tool: str
    status: Literal["done", "running", "queued", "partial", "blocked", "failed", "cancelled"]
    metrics: dict[str, object] = Field(default_factory=dict)


class AgentRun(BaseModel):
    id: str
    project_id: str
    session_id: str
    task: str
    provider: str
    mode: str
    status: AgentRunStatusLiteral
    plan_json: str
    plan_artifact_id: str | None
    result_artifact_id: str | None
    created_at: str
    updated_at: str


class AgentPlanResponse(BaseModel):
    run_id: str
    project_id: str
    session_id: str
    task: str
    provider: str
    status: AgentRunStatusLiteral
    rationale: str
    steps: list[AgentPlanStep]
    artifact: Artifact


class AgentExecuteResponse(BaseModel):
    run_id: str
    status: AgentRunStatusLiteral
    artifact: Artifact | None = None
    papers: list[dict[str, object]] = Field(default_factory=list)
    paper_count: int = 0
    summary_metrics: dict[str, object] = Field(default_factory=dict)
    run_status_summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)
    steps: list[AgentPlanStep]
    updated_at: str = ""


class AgentRunStatusResponse(BaseModel):
    run_id: str
    status: AgentRunStatusLiteral
    steps: list[AgentPlanStep]
    summary_metrics: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    workflow_steps: list[WorkflowStepState] = Field(default_factory=list)
    run_status_summary: str = ""
    current_tool: str = ""
    papers: list[dict[str, object]] = Field(default_factory=list)
    paper_count: int = 0
    artifact: Artifact | None = None
    updated_at: str


class Session(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    created_at: str
    updated_at: str


class ToolEvent(BaseModel):
    id: str
    session_id: str
    time_label: str
    tool: str
    status: ToolEventStatusLiteral
    summary: str
    created_at: str
