import type {
  ApiAgentPlanStep,
  ApiArtifact,
  ApiArtifactRef,
  ApiArtifactSummary,
  ApiDirectionPaperReading,
  ApiDirectionReviewResponse,
  ApiEvidencePack,
  ApiPaper,
  ApiPaperCard,
  ApiPaperCardSection,
  ApiPaperMemoryHit,
  ApiPaperSignals,
  ApiResearchDecisionResponse,
  ApiResearchMemoryQueryResponse,
  ApiResearchSight,
  ApiToolEvent,
} from "@scholarflow/schemas";
import { getArtifact } from "../apiClient";
import type { PaperRow, PlanStep, PlanStatus, TimelineEvent, ViewId } from "../mockData";

export type HydratedWorkflowState = {
  directionReview: ApiDirectionReviewResponse | null;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  paperCard: ApiPaperCard | null;
  researchDecision: ApiResearchDecisionResponse | null;
};

export function hydrateWorkflowStateFromArtifacts(items: ApiArtifact[]): HydratedWorkflowState {
  return {
    directionReview: hydrateDirectionReview(items),
    memoryResult: hydrateResearchMemory(items),
    paperCard: hydratePaperCard(items),
    researchDecision: hydrateResearchDecision(items),
  };
}

export async function loadHydrationArtifacts(summaries: ApiArtifactSummary[], options?: RequestInit): Promise<ApiArtifact[]> {
  const ids = selectHydrationArtifactIds(summaries);
  const results = await Promise.allSettled(ids.map((id) => getArtifact(id, options)));
  return results.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
}

export function collectArtifactHydrationWarnings(items: ApiArtifact[]): string[] {
  return items.flatMap((artifact) => {
    if (!artifact.content_json.trim()) {
      return [];
    }
    try {
      const payload = JSON.parse(artifact.content_json) as unknown;
      if (isRecord(payload)) {
        return [];
      }
      return [`Artifact JSON 不是对象，已跳过 hydration：${artifact.title}`];
    } catch {
      return [`Artifact JSON 解析失败，已跳过 hydration：${artifact.title}`];
    }
  });
}

function selectHydrationArtifactIds(summaries: ApiArtifactSummary[]): string[] {
  const selected = new Set<string>();
  const groups = [
    ["direction_review"],
    ["research_memory_answer"],
    ["gap_board", "idea_validation", "experiment_plan"],
    ["paper_card"],
  ];
  for (const patterns of groups) {
    const hit = summaries.find((artifact) => {
      const title = artifact.title.toLowerCase();
      return patterns.some((pattern) => title.includes(pattern));
    });
    if (hit) {
      selected.add(hit.id);
    }
  }
  return [...selected];
}

export function upsertArtifactDetail(items: ApiArtifact[], artifact: ApiArtifact): ApiArtifact[] {
  return [artifact, ...items.filter((item) => item.id !== artifact.id)];
}

export function upsertArtifactSummary(items: ApiArtifactSummary[], artifact: ApiArtifactSummary): ApiArtifactSummary[] {
  return [artifact, ...items.filter((item) => item.id !== artifact.id)];
}

export function artifactSummaryFromDetail(artifact: ApiArtifact): ApiArtifactSummary {
  return {
    id: artifact.id,
    project_id: artifact.project_id,
    title: artifact.title,
    kind: artifact.kind,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at,
    markdown_bytes: byteLength(artifact.content_markdown),
    json_bytes: byteLength(artifact.content_json),
    markdown_preview: artifact.content_markdown.slice(0, 280),
    json_schema_version: readArtifactSchemaVersion(artifact.content_json),
  };
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

function readArtifactSchemaVersion(contentJson: string): string {
  try {
    const payload = JSON.parse(contentJson) as unknown;
    return isRecord(payload) ? asString(payload.schema_version) : "";
  } catch {
    return "";
  }
}

function defaultEvidencePack(): ApiEvidencePack {
  return {
    evidence_level: "unknown",
    confidence: "low",
    snippets: [],
    missing_evidence: [],
    grounding_summary: "暂无 EvidencePack",
  };
}

function defaultResearchSight(): ApiResearchSight {
  return {
    motivation_sharpness: "",
    solution_elegance: "",
    evaluation_integrity: "",
    paradigm_inspiration: "",
    why_good: "",
    why_not_good: "",
    better_angle: "",
    baseline_comparison: "",
    next_step_proposal: "",
    evidence_pack: defaultEvidencePack(),
    critique_evidence: [],
  };
}

export function normalizeDirectionReading(
  payloadReading: unknown,
  artifactProjectId: string,
  artifactCreatedAt: string,
): ApiDirectionPaperReading {
  const reading: Record<string, unknown> = isRecord(payloadReading) ? payloadReading : {};
  const card: Record<string, unknown> = isRecord(reading.card) ? reading.card : {};
  const sectionPayloads = Array.isArray(reading.sections)
    ? reading.sections
    : Array.isArray(card.sections)
      ? card.sections
      : [];

  return {
    paper: normalizeApiPaper(reading.paper, artifactProjectId, artifactCreatedAt),
    abstract_translation: asString(reading.abstract_translation),
    signals: normalizePaperSignals(reading.signals ?? card.signals),
    sections: sectionPayloads.map(normalizePaperCardSection),
    research_sight: normalizeResearchSight(reading.research_sight),
    weakest_assumption: firstString(reading.weakest_assumption, card.weakest_assumption),
    minimal_reproduction: firstString(reading.minimal_reproduction, card.minimal_reproduction),
    counterexample: firstString(reading.counterexample, card.counterexample),
    follow_up_idea: firstString(reading.follow_up_idea, card.follow_up_idea),
    why_selected: asString(reading.why_selected),
    venue_signal: asString(reading.venue_signal),
    self_read_priority: asBoolean(reading.self_read_priority),
  };
}

export function normalizeMemoryHit(hitPayload: unknown, artifactProjectId: string, artifactCreatedAt: string): ApiPaperMemoryHit {
  const hit: Record<string, unknown> = isRecord(hitPayload) ? hitPayload : {};
  const memory: Record<string, unknown> = isRecord(hit.memory) ? hit.memory : {};
  const score = asNumber(hit.score);
  const selfReadPriority = asBoolean(hit.self_read_priority ?? memory.self_read_priority);
  const paperPayload = isRecord(hit.paper)
    ? hit.paper
    : {
        id: firstString(memory.paper_id, memory.id),
        project_id: firstString(memory.project_id, artifactProjectId),
        title: asString(memory.title),
        authors: asString(memory.authors),
        abstract: "",
        year: asString(memory.year),
        type: "memory",
        venue: asString(memory.venue),
        source: asString(memory.source),
        url: asString(memory.url),
        relation: asString(memory.why_selected),
        priority: selfReadPriority ? "High" : "Medium",
        code: "unknown",
        relevance_score: score,
        created_at: firstString(memory.created_at, artifactCreatedAt),
      };
  const researchSightPayload = isRecord(hit.research_sight)
    ? hit.research_sight
    : parseJsonRecord(memory.research_sight_json);

  return {
    paper: normalizeApiPaper(paperPayload, artifactProjectId, artifactCreatedAt),
    direction: firstString(hit.direction, memory.direction),
    round: asNumber(hit.round, asNumber(memory.round_index)),
    score,
    title_score: asNumber(hit.title_score),
    keyword_score: asNumber(hit.keyword_score),
    section_score: asNumber(hit.section_score),
    priority_score: asNumber(hit.priority_score),
    snippets: asStringArray(hit.snippets),
    abstract_translation: firstString(hit.abstract_translation, memory.abstract_translation),
    weakest_assumption: firstString(hit.weakest_assumption, memory.weakest_assumption),
    minimal_reproduction: firstString(hit.minimal_reproduction, memory.minimal_reproduction),
    counterexample: firstString(hit.counterexample, memory.counterexample),
    follow_up_idea: firstString(hit.follow_up_idea, memory.follow_up_idea),
    why_selected: firstString(hit.why_selected, memory.why_selected),
    research_sight: normalizeResearchSight(researchSightPayload),
    self_read_priority: selfReadPriority,
  };
}

function normalizeApiPaper(payload: unknown, artifactProjectId: string, artifactCreatedAt: string): ApiPaper {
  const paper: Record<string, unknown> = isRecord(payload) ? payload : {};
  return {
    id: asString(paper.id) || `artifact-paper-${stableTextKey(asString(paper.title) || "untitled")}`,
    project_id: asString(paper.project_id) || artifactProjectId,
    title: asString(paper.title) || "Untitled paper",
    authors: asString(paper.authors),
    abstract: asString(paper.abstract),
    year: asString(paper.year),
    type: asString(paper.type) || "unknown",
    venue: asString(paper.venue),
    source: asString(paper.source),
    url: asString(paper.url),
    relation: asString(paper.relation),
    priority: asString(paper.priority) || "Medium",
    code: asString(paper.code) || "unknown",
    relevance_score: asNumber(paper.relevance_score),
    created_at: asString(paper.created_at) || artifactCreatedAt,
  };
}

function normalizePaperSignals(payload: unknown): ApiPaperSignals | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  return {
    task: asString(payload.task),
    method: asString(payload.method),
    dataset: asString(payload.dataset),
    metric: asString(payload.metric),
    claim: asString(payload.claim),
    limitation: asString(payload.limitation),
    contribution_type: asString(payload.contribution_type),
    missing_signals: asStringArray(payload.missing_signals),
  };
}

function normalizePaperCardSection(payload: unknown, index: number): ApiPaperCardSection {
  const section: Record<string, unknown> = isRecord(payload) ? payload : {};
  return {
    id: asString(section.id) || `section_${index + 1}`,
    title: asString(section.title) || `Section ${index + 1}`,
    content: asString(section.content),
  };
}

export function normalizeResearchSight(payload: unknown): ApiResearchSight {
  const sight: Record<string, unknown> = isRecord(payload) ? payload : {};
  return {
    ...defaultResearchSight(),
    motivation_sharpness: asString(sight.motivation_sharpness),
    solution_elegance: asString(sight.solution_elegance),
    evaluation_integrity: asString(sight.evaluation_integrity),
    paradigm_inspiration: asString(sight.paradigm_inspiration),
    why_good: asString(sight.why_good),
    why_not_good: asString(sight.why_not_good),
    better_angle: asString(sight.better_angle),
    baseline_comparison: asString(sight.baseline_comparison),
    next_step_proposal: asString(sight.next_step_proposal),
    evidence_pack: normalizeEvidencePack(sight.evidence_pack),
    critique_evidence: Array.isArray(sight.critique_evidence)
      ? sight.critique_evidence.map((item) => {
          const judgment: Record<string, unknown> = isRecord(item) ? item : {};
          return {
            field: asString(judgment.field),
            evidence_snippet_id: asString(judgment.evidence_snippet_id),
            confidence: asString(judgment.confidence) || "low",
            rationale: asString(judgment.rationale),
          };
        })
      : [],
  };
}

export function normalizeEvidencePack(payload: unknown): ApiEvidencePack {
  const pack: Record<string, unknown> = isRecord(payload) ? payload : {};
  return {
    evidence_level: asString(pack.evidence_level) || "unknown",
    confidence: asString(pack.confidence) || "low",
    snippets: Array.isArray(pack.snippets)
      ? pack.snippets.map((item, index) => {
          const snippet: Record<string, unknown> = isRecord(item) ? item : {};
          return {
            id: asString(snippet.id) || `snippet_${index + 1}`,
            source: asString(snippet.source),
            kind: asString(snippet.kind),
            text: asString(snippet.text),
            note: asString(snippet.note),
            confidence: asString(snippet.confidence) || "low",
          };
        })
      : [],
    missing_evidence: asStringArray(pack.missing_evidence),
    grounding_summary: asString(pack.grounding_summary) || "暂无 EvidencePack",
  };
}

function hydrateDirectionReview(items: ApiArtifact[]): ApiDirectionReviewResponse | null {
  const artifact = findArtifactPayload(
    items,
    (title) => title.includes("direction_review"),
    (payload) =>
      Array.isArray(payload.papers) &&
      typeof payload.review_status === "string" &&
      typeof payload.target_paper_count === "number",
  );
  if (!artifact) {
    return null;
  }
  const relatedArtifacts = items.filter((item) => {
    const title = item.title.toLowerCase();
    return title.includes("direction_review") || title.includes("baseline_map") || title.includes("direction_round");
  });
  const payload = artifact.payload;
  const papers = Array.isArray(payload.papers)
    ? payload.papers.map((reading) => normalizeDirectionReading(reading, artifact.artifact.project_id, artifact.artifact.created_at))
    : [];
  const artifactRefs = Array.isArray(payload.artifact_refs)
    ? (payload.artifact_refs as ApiArtifactRef[])
    : relatedArtifacts.map((item) => ({
        id: item.id,
        title: item.title,
        kind: item.kind,
        created_at: item.created_at,
      }));
  return {
    ...(payload as Partial<ApiDirectionReviewResponse>),
    direction: asString(payload.direction),
    round: asNumber(payload.round, 1),
    review_status: asString(payload.review_status) === "partial" ? "partial" : "complete",
    target_paper_count: asNumber(payload.target_paper_count, 10),
    round_read_count: asNumber(payload.round_read_count, papers.length),
    total_read_count: asNumber(payload.total_read_count, papers.length),
    papers,
    recommended_paper_ids: asStringArray(payload.recommended_paper_ids),
    direction_summary: asString(payload.direction_summary),
    artifact_refs: artifactRefs,
    artifacts: relatedArtifacts,
    errors: asStringArray(payload.errors),
  };
}

function hydrateResearchMemory(items: ApiArtifact[]): ApiResearchMemoryQueryResponse | null {
  const artifact = findArtifactPayload(
    items,
    (title) => title.includes("research_memory_answer"),
    (payload) => Array.isArray(payload.hits) && typeof payload.total_memories === "number",
  );
  if (!artifact) {
    return null;
  }
  const payload = artifact.payload;
  const hits = Array.isArray(payload.hits)
    ? payload.hits.map((hit) => normalizeMemoryHit(hit, artifact.artifact.project_id, artifact.artifact.created_at))
    : [];
  return {
    ...(payload as Partial<ApiResearchMemoryQueryResponse>),
    question: asString(payload.question),
    top_k: asNumber(payload.top_k, hits.length),
    answer: asString(payload.answer),
    hits,
    direction_memory: isRecord(payload.direction_memory)
      ? (payload.direction_memory as unknown as ApiResearchMemoryQueryResponse["direction_memory"])
      : null,
    total_memories: asNumber(payload.total_memories, hits.length),
    artifact: artifact.artifact,
    warnings: asStringArray(payload.warnings),
  };
}

function hydrateResearchDecision(items: ApiArtifact[]): ApiResearchDecisionResponse | null {
  const artifact = findArtifactPayload(
    items,
    (title) => title.includes("gap_board") || title.includes("idea_validation") || title.includes("experiment_plan"),
    (payload) => Array.isArray(payload.gaps) && isRecord(payload.validation) && isRecord(payload.experiment),
  );
  if (!artifact) {
    return null;
  }
  const relatedArtifacts = items.filter((item) => {
    const title = item.title.toLowerCase();
    return title.includes("gap_board") || title.includes("idea_validation") || title.includes("experiment_plan");
  });
  return {
    ...(artifact.payload as Omit<ApiResearchDecisionResponse, "artifacts">),
    artifacts: relatedArtifacts,
  };
}

function hydratePaperCard(items: ApiArtifact[]): ApiPaperCard | null {
  const artifact = findArtifactPayload(
    items,
    (title) => title.includes("paper_card"),
    (payload) => isRecord(payload.card) && Array.isArray(payload.card.sections),
  );
  if (!artifact || !isRecord(artifact.payload.card)) {
    return null;
  }
  const card = artifact.payload.card;
  const paper = isRecord(artifact.payload.paper) ? artifact.payload.paper : {};
  return {
    id: artifact.artifact.id,
    project_id: artifact.artifact.project_id,
    paper_id: typeof paper.id === "string" ? paper.id : null,
    artifact_id: artifact.artifact.id,
    signals: isRecord(card.signals) ? (card.signals as unknown as ApiPaperCard["signals"]) : undefined,
    sections: Array.isArray(card.sections) ? (card.sections as ApiPaperCard["sections"]) : [],
    weakest_assumption: typeof card.weakest_assumption === "string" ? card.weakest_assumption : "",
    minimal_reproduction: typeof card.minimal_reproduction === "string" ? card.minimal_reproduction : "",
    created_at: artifact.artifact.created_at,
  };
}

function findArtifactPayload(
  items: ApiArtifact[],
  titleMatches: (title: string) => boolean,
  payloadMatches: (payload: Record<string, unknown>) => boolean,
): { artifact: ApiArtifact; payload: Record<string, unknown> } | null {
  for (const artifact of items) {
    const title = artifact.title.toLowerCase();
    if (!titleMatches(title)) {
      continue;
    }
    const payload = parseArtifactJson(artifact);
    if (payload && payloadMatches(payload)) {
      return { artifact, payload };
    }
  }
  return null;
}

function parseArtifactJson(artifact: ApiArtifact): Record<string, unknown> | null {
  if (!artifact.content_json.trim()) {
    return null;
  }
  try {
    const payload = JSON.parse(artifact.content_json) as unknown;
    return isRecord(payload) ? payload : null;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const text = asString(value).trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function asBoolean(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "yes", "high"].includes(normalized)) {
      return true;
    }
    const numeric = Number(normalized);
    return Number.isFinite(numeric) ? numeric !== 0 : false;
  }
  return false;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => asString(item).trim()).filter(Boolean);
}

function parseJsonRecord(value: unknown): Record<string, unknown> | null {
  if (!asString(value).trim()) {
    return null;
  }
  try {
    const parsed = JSON.parse(asString(value)) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function stableTextKey(value: string): string {
  const normalized = value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "-").replace(/^-|-$/g, "");
  return normalized.slice(0, 48) || "untitled";
}

export function selectArtifactForView<T extends { title: string }>(items: T[], view: ViewId): T | null {
  const wanted = artifactPatternsByView[view] ?? [];
  return (
    items.find((artifact) => {
      const title = artifact.title.toLowerCase();
      return wanted.some((pattern) => title.includes(pattern));
    }) ?? items[0] ?? null
  );
}

const artifactPatternsByView: Record<ViewId, string[]> = {
  dashboard: ["agent_run", "agent_plan"],
  "new-project": [],
  "paper-table": ["paper_table", "literature_search"],
  "direction-review": ["direction_review", "baseline_map"],
  "paper-memory": ["research_memory_answer", "direction_memory"],
  "paper-reader": ["paper_card"],
  "gap-board": ["gap_board", "idea_validation"],
  "experiment-planner": ["experiment_plan"],
};

export function toPaperRow(paper: ApiPaper): PaperRow {
  return {
    id: paper.id,
    title: paper.title,
    authors: paper.authors,
    abstract: paper.abstract,
    year: paper.year,
    type: paper.type,
    venue: paper.venue,
    source: paper.source,
    url: paper.url,
    relation: paper.relation,
    priority: paper.priority === "High" || paper.priority === "Medium" || paper.priority === "Watch" ? paper.priority : "Medium",
    code: paper.code,
    relevanceScore: paper.relevance_score,
  };
}

export function toTimelineEvent(event: ApiToolEvent): TimelineEvent {
  return {
    time: event.time_label,
    tool: event.tool,
    status: event.status,
    summary: event.summary,
  };
}

export function toPlanStep(step: ApiAgentPlanStep): PlanStep {
  return {
    id: step.id,
    title: step.title,
    detail: step.detail,
    status: toPlanStatus(step.status),
  };
}

export function toPlanStatus(status: ApiAgentPlanStep["status"]): PlanStatus {
  if (status === "done") {
    return "done";
  }
  if (status === "running") {
    return "active";
  }
  if (status === "failed") {
    return "blocked";
  }
  return "queued";
}
