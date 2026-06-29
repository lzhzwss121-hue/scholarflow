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


class PaperCard(BaseModel):
    id: str
    project_id: str
    paper_id: str | None
    artifact_id: str | None
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
    sections: list[PaperCardSection]
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
    total_read_count: int
    scope: DirectionScope
    papers: list[DirectionPaperReading]
    recommended_paper_ids: list[str]
    direction_summary: str
    artifacts: list[Artifact]
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
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    ablations: list[str]
    resources: str
    timeline: list[str]
    success_criterion: str
    failure_criterion: str


class ResearchDecisionResponse(BaseModel):
    gaps: list[GapDecision]
    validation: IdeaValidation
    experiment: ExperimentPlan
    artifacts: list[Artifact]


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
    status: Literal["done", "running", "queued"]


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
    papers: list[dict[str, str]]
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
