from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    relation: str
    priority: str
    code: str
    relevance_score: float
    created_at: str


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


class PaperCardCreateRequest(BaseModel):
    paper_id: str | None = None
    title: str = ""
    abstract: str = ""
    paper_text: str = Field(default="", max_length=50000)


class PaperCardSection(BaseModel):
    id: str
    title: str
    content: str


class PaperSignals(BaseModel):
    task: str = ""
    method: str = ""
    dataset: str = ""
    metric: str = ""
    claim: str = ""
    limitation: str = ""
    contribution_type: str = ""
    missing_signals: list[str] = Field(default_factory=list)


class EvidenceSnippet(BaseModel):
    id: str = ""
    source: str = ""
    kind: str = ""
    text: str = ""
    note: str = ""
    confidence: str = ""


class EvidencePack(BaseModel):
    evidence_level: str = ""
    confidence: str = ""
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
    artifact_id: str | None
    signals: PaperSignals = Field(default_factory=PaperSignals)
    sections: list[PaperCardSection]
    weakest_assumption: str
    minimal_reproduction: str
    created_at: str


class PaperCardResponse(BaseModel):
    card: PaperCard
    artifact: Artifact


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
    review_status: Literal["complete", "partial"] = "complete"
    target_paper_count: int = 10
    round_read_count: int
    total_read_count: int
    recommended_paper_ids: list[str]
    direction_summary: str
    artifact_refs: list[ArtifactRef]
    errors: list[str]


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


class ResearchDecisionResponse(BaseModel):
    gaps: list[GapDecision]
    validation: IdeaValidation
    experiment: ExperimentPlan
    artifacts: list[Artifact]


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


class ResearchMemoryQueryResponse(BaseModel):
    question: str
    top_k: int
    answer: str
    hits: list[PaperMemoryHit]
    direction_memory: DirectionMemory | None
    total_memories: int
    artifact: Artifact
    warnings: list[str]


class AgentPlanRequest(BaseModel):
    project_id: str
    task: str = Field(min_length=1, max_length=1000)
    provider: str = "openrouter"


class AgentExecuteRequest(BaseModel):
    confirmed: bool = True


class AgentPlanStep(BaseModel):
    id: str
    title: str
    detail: str
    tool: str
    status: Literal["done", "running", "queued", "failed"]
    metrics: dict[str, object] = Field(default_factory=dict)


class AgentRun(BaseModel):
    id: str
    project_id: str
    session_id: str
    task: str
    provider: str
    mode: str
    status: Literal["planned", "running", "completed"]
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
    status: Literal["planned", "running", "completed"]
    rationale: str
    steps: list[AgentPlanStep]
    artifact: Artifact


class AgentExecuteResponse(BaseModel):
    run_id: str
    status: Literal["completed"]
    artifact: Artifact
    papers: list[dict[str, object]]
    paper_count: int
    summary_metrics: dict[str, object] = Field(default_factory=dict)
    steps: list[AgentPlanStep]


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
    status: Literal["done", "running", "queued"]
    summary: str
    created_at: str
