import type {
  ApiAgentPlanStep,
  ApiArtifact,
  ApiArtifactRef,
  ApiArtifactSummary,
  ApiDirectionPaperReading,
  ApiDirectionReviewResponse,
  ApiEvidencePack,
  ApiFullTextProvenance,
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
  literatureCoverage: Record<string, number>;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  paperCard: ApiPaperCard | null;
  researchDecision: ApiResearchDecisionResponse | null;
};

export type PaperCardMatchSource = "paper_table" | "direction_review_artifact" | "manual_unbound";

export type PaperCardMatch = {
  card: ApiPaperCard;
  matchedBy: "paper_id" | "title" | "artifact_slug" | "manual_unbound";
  source: PaperCardMatchSource;
};

export function hydrateWorkflowStateFromArtifacts(items: ApiArtifact[]): HydratedWorkflowState {
  return {
    directionReview: hydrateDirectionReview(items),
    literatureCoverage: hydrateLiteratureCoverage(items),
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
  const newestFirst = [...summaries].sort((left, right) =>
    (right.updated_at || right.created_at).localeCompare(left.updated_at || left.created_at),
  );
  const groups = [
    ["direction_review"],
    ["paper_table", "literature_search"],
    ["research_memory_answer"],
    ["gap_board", "idea_validation", "experiment_plan"],
    ["paper_card"],
  ];
  for (const patterns of groups) {
    const hit = newestFirst.find((artifact) => {
      const title = artifact.title.toLowerCase();
      return patterns.some((pattern) => title.includes(pattern));
    });
    if (hit) {
      selected.add(hit.id);
    }
  }
  newestFirst
    .filter((artifact) => isDirectionPaperCardTitle(artifact.title))
    .slice(0, 15)
    .forEach((artifact) => selected.add(artifact.id));
  return [...selected];
}

function hydrateLiteratureCoverage(items: ApiArtifact[]): Record<string, number> {
  const artifact = findArtifactPayload(
    items,
    (title) => title.includes("paper_table") || title.includes("literature_search"),
    (payload) => isRecord(payload.relevance_coverage),
  );
  if (!artifact || !isRecord(artifact.payload.relevance_coverage)) {
    return {};
  }
  return normalizeCoverageRecord(artifact.payload.relevance_coverage);
}

function normalizeCoverageRecord(payload: Record<string, unknown>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(payload)
      .filter(([, value]) => typeof value === "number")
      .map(([key, value]) => [key, Number(value)]),
  );
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
  artifactId = "",
  artifactTitle = "",
): ApiDirectionPaperReading {
  const reading: Record<string, unknown> = isRecord(payloadReading) ? payloadReading : {};
  const card: Record<string, unknown> = isRecord(reading.card) ? reading.card : {};
  const rawPaper: Record<string, unknown> = isRecord(reading.paper) ? { ...reading.paper } : {};
  const explicitPaperId = firstString(reading.paper_id, rawPaper.id, card.paper_id);
  const explicitPaperTitle = firstString(reading.paper_title, rawPaper.title, card.paper_title, reading.title);
  if (!asString(rawPaper.id) && explicitPaperId) {
    rawPaper.id = explicitPaperId;
  }
  if (!asString(rawPaper.title) && explicitPaperTitle) {
    rawPaper.title = explicitPaperTitle;
  }
  const sectionPayloads = Array.isArray(reading.sections)
    ? reading.sections
    : Array.isArray(card.sections)
      ? card.sections
      : [];
  const paper = normalizeApiPaper(rawPaper, artifactProjectId, artifactCreatedAt);

  return {
    paper,
    paper_id: explicitPaperId || paper.id,
    paper_title: explicitPaperTitle || paper.title,
    artifact_id: artifactId || null,
    artifact_title: artifactTitle,
    abstract_translation: asString(reading.abstract_translation),
    evidence_level: (normalizeEvidenceLevel(firstString(reading.evidence_level, card.evidence_level)) || "metadata_only") as ApiDirectionPaperReading["evidence_level"],
    full_text: normalizeFullTextProvenance(reading.full_text ?? card.full_text),
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
    pdf_url: asString(paper.pdf_url),
    relation: asString(paper.relation),
    priority: asString(paper.priority) || "Medium",
    code: asString(paper.code) || "unknown",
    relevance_score: asNumber(paper.relevance_score),
    relevance_quality: normalizeRelevanceQuality(paper.relevance_quality),
    matched_terms: asStringArray(paper.matched_terms).length
      ? asStringArray(paper.matched_terms)
      : parseMatchedTerms(asString(paper.matched_terms_json)),
    matched_terms_json: asString(paper.matched_terms_json),
    review_required: asBoolean(paper.review_required),
    created_at: asString(paper.created_at) || artifactCreatedAt,
  };
}

function normalizeRelevanceQuality(value: unknown): ApiPaper["relevance_quality"] {
  const quality = asString(value);
  if (quality === "strong" || quality === "medium" || quality === "weak" || quality === "off_topic") {
    return quality;
  }
  return "medium";
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
    baseline: asString(payload.baseline),
    claim: asString(payload.claim),
    limitation: asString(payload.limitation),
    contribution_type: asString(payload.contribution_type),
    contribution_evidence: asString(payload.contribution_evidence),
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
    evidence_level: normalizeEvidenceLevel(asString(pack.evidence_level)) || "unknown",
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

function normalizeFullTextProvenance(payload: unknown): ApiFullTextProvenance | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  const rawStatus = asString(payload.status);
  const status: ApiFullTextProvenance["status"] = [
    "extracted",
    "not_available",
    "download_failed",
    "parse_failed",
    "disabled",
  ].includes(rawStatus)
    ? (rawStatus as ApiFullTextProvenance["status"])
    : "not_available";
  return {
    status,
    pdf_url: asString(payload.pdf_url),
    source: asString(payload.source),
    page_count: asNumber(payload.page_count),
    character_count: asNumber(payload.character_count),
    error: asString(payload.error),
  };
}

function normalizeEvidenceLevel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[-+]/g, "_");
  if (["metadata_only", "abstract_only", "full_text"].includes(normalized)) {
    return normalized;
  }
  if (normalized === "metadata_abstract" || normalized === "metadata_abstract_paper_card") {
    return "abstract_only";
  }
  if (normalized === "metadata" || normalized === "metadataonly") {
    return "metadata_only";
  }
  return "";
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
  const reviewReadings = Array.isArray(payload.papers)
    ? payload.papers.map((reading) =>
        normalizeDirectionReading(
          reading,
          artifact.artifact.project_id,
          artifact.artifact.created_at,
          artifact.artifact.id,
          artifact.artifact.title,
        ),
      )
    : [];
  const cardReadings = relatedArtifacts
    .filter((item) => item.id !== artifact.artifact.id && isDirectionPaperCardTitle(item.title))
    .flatMap((item) => {
      const payload = parseArtifactJson(item);
      return payload ? [normalizeDirectionReading(payload, item.project_id, item.created_at, item.id, item.title)] : [];
    });
  const papers = mergeDirectionReadings(reviewReadings, cardReadings);
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
    review_status: normalizeReviewStatus(payload.review_status),
    target_paper_count: asNumber(payload.target_paper_count, 10),
    round_read_count: asNumber(payload.round_read_count, papers.length),
    relevant_read_count: asNumber(payload.relevant_read_count, asNumber(payload.round_read_count, papers.length)),
    low_relevance_count: asNumber(payload.low_relevance_count),
    off_topic_count: asNumber(payload.off_topic_count),
    relevance_coverage: isRecord(payload.relevance_coverage)
      ? (payload.relevance_coverage as Record<string, number>)
      : {},
    total_read_count: asNumber(payload.total_read_count, papers.length),
    papers,
    recommended_paper_ids: asStringArray(payload.recommended_paper_ids),
    direction_summary: asString(payload.direction_summary),
    artifact_refs: artifactRefs,
    artifacts: relatedArtifacts,
    errors: asStringArray(payload.errors),
  };
}

function normalizeReviewStatus(value: unknown): ApiDirectionReviewResponse["review_status"] {
  const status = asString(value);
  if (status === "partial" || status === "blocked" || status === "complete") {
    return status;
  }
  return "complete";
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
  const candidates = items.flatMap((artifact) => {
    if (!artifact.title.toLowerCase().includes("paper_card")) {
      return [];
    }
    const payload = parseArtifactJson(artifact);
    if (!payload) {
      return [];
    }
    const card = isRecord(payload.card) ? payload.card : payload;
    if (!Array.isArray(card.sections)) {
      return [];
    }
    return [hydratePaperCardArtifact(artifact, payload)];
  });
  return candidates.reduce<ApiPaperCard | null>((best, candidate) => preferPaperCard(best, candidate), null);
}

function hydratePaperCardArtifact(artifactDetail: ApiArtifact, payload: Record<string, unknown>): ApiPaperCard {
  const artifact = { artifact: artifactDetail, payload };
  const card = isRecord(artifact.payload.card) ? artifact.payload.card : artifact.payload;
  const paper = isRecord(artifact.payload.paper) ? artifact.payload.paper : {};
  const sections = Array.isArray(card.sections) ? card.sections.map(normalizePaperCardSection) : [];
  const paperId = firstString(paper.id, card.paper_id);
  const paperTitle = firstString(paper.title, card.paper_title);
  return {
    id: artifact.artifact.id,
    project_id: artifact.artifact.project_id,
    paper_id: paperId || null,
    paper_title: paperTitle,
    artifact_id: artifact.artifact.id,
    source_artifact_title: artifact.artifact.title,
    card_source: isDirectionPaperCardTitle(artifact.artifact.title)
      ? "direction_review_artifact"
      : paperId
        ? "paper_table"
        : "manual_unbound",
    evidence_level: (normalizeEvidenceLevel(firstString(card.evidence_level, artifact.payload.evidence_level)) || "metadata_only") as ApiPaperCard["evidence_level"],
    full_text: normalizeFullTextProvenance(artifact.payload.full_text ?? card.full_text),
    signals: normalizePaperSignals(card.signals),
    sections,
    weakest_assumption: typeof card.weakest_assumption === "string" ? card.weakest_assumption : "",
    minimal_reproduction: typeof card.minimal_reproduction === "string" ? card.minimal_reproduction : "",
    created_at: artifact.artifact.created_at,
  };
}

export function preferPaperCard(current: ApiPaperCard | null, incoming: ApiPaperCard | null): ApiPaperCard | null {
  if (!current) {
    return incoming;
  }
  if (!incoming) {
    return current;
  }
  const currentRank = paperCardEvidenceRank(current);
  const incomingRank = paperCardEvidenceRank(incoming);
  if (incomingRank !== currentRank) {
    return incomingRank > currentRank ? incoming : current;
  }
  return compareIsoTimestamp(incoming.created_at, current.created_at) >= 0 ? incoming : current;
}

function paperCardEvidenceRank(card: ApiPaperCard): number {
  if (card.evidence_level === "full_text" && card.full_text?.status === "extracted") {
    return 3;
  }
  if (card.evidence_level === "full_text") {
    return 2;
  }
  if (card.evidence_level === "abstract_only") {
    return 1;
  }
  return 0;
}

function compareIsoTimestamp(left: string, right: string): number {
  return left.localeCompare(right);
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

export function normalizePaperTitleKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/gi, "");
}

function artifactPaperSlugKey(value: string): string {
  const withoutExtension = value.toLowerCase().replace(/\.[a-z0-9]+$/i, "");
  const slug = withoutExtension
    .replace(/^agent_direction_round_\d+_paper_card_/, "")
    .replace(/^direction_round_\d+_paper_card_/, "")
    .replace(/^paper_card_/, "");
  return normalizePaperTitleKey(slug);
}

function isDirectionPaperCardTitle(title: string): boolean {
  const normalized = title.toLowerCase();
  return normalized.includes("paper_card") && (normalized.includes("direction_round") || normalized.includes("agent_direction_round"));
}

function mergeDirectionReadings(
  baseReadings: ApiDirectionPaperReading[],
  cardReadings: ApiDirectionPaperReading[],
): ApiDirectionPaperReading[] {
  const merged = [...baseReadings];
  for (const reading of cardReadings) {
    const existingIndex = merged.findIndex((item) => directionReadingsReferToSamePaper(item, reading));
    if (existingIndex >= 0) {
      merged[existingIndex] = preferRicherDirectionReading(merged[existingIndex], reading);
    } else {
      merged.push(reading);
    }
  }
  return merged;
}

function directionReadingsReferToSamePaper(left: ApiDirectionPaperReading, right: ApiDirectionPaperReading): boolean {
  const leftId = left.paper_id || left.paper.id;
  const rightId = right.paper_id || right.paper.id;
  if (leftId && rightId && leftId === rightId) {
    return true;
  }
  const leftTitle = normalizePaperTitleKey(left.paper_title || left.paper.title);
  const rightTitle = normalizePaperTitleKey(right.paper_title || right.paper.title);
  return Boolean(leftTitle && rightTitle && leftTitle === rightTitle);
}

function preferRicherDirectionReading(
  current: ApiDirectionPaperReading,
  incoming: ApiDirectionPaperReading,
): ApiDirectionPaperReading {
  const incomingEvidenceRank = directionReadingEvidenceRank(incoming);
  const currentEvidenceRank = directionReadingEvidenceRank(current);
  if (incomingEvidenceRank !== currentEvidenceRank) {
    return incomingEvidenceRank > currentEvidenceRank ? incoming : current;
  }
  if ((incoming.sections?.length ?? 0) > (current.sections?.length ?? 0)) {
    return incoming;
  }
  if (compareIsoTimestamp(incoming.paper.created_at, current.paper.created_at) > 0) {
    return incoming;
  }
  if (incoming.artifact_id && !current.artifact_id) {
    return { ...current, artifact_id: incoming.artifact_id, artifact_title: incoming.artifact_title };
  }
  return current;
}

function directionReadingEvidenceRank(reading: ApiDirectionPaperReading): number {
  if (reading.evidence_level === "full_text" && reading.full_text?.status === "extracted") {
    return 3;
  }
  if (reading.evidence_level === "full_text") {
    return 2;
  }
  if (reading.evidence_level === "abstract_only") {
    return 1;
  }
  return 0;
}

export function resolvePaperCardForPaper(
  latestPaperCard: ApiPaperCard | null,
  directionReview: ApiDirectionReviewResponse | null,
  paper: PaperRow | undefined,
): PaperCardMatch | null {
  if (!paper) {
    if (!latestPaperCard) {
      return null;
    }
    return {
      card: latestPaperCard,
      matchedBy: "manual_unbound",
      source: latestPaperCard.card_source ?? "manual_unbound",
    };
  }
  const directMatch = matchStandalonePaperCard(latestPaperCard, paper);
  if (directMatch) {
    return directMatch;
  }
  const directionMatch = findDirectionPaperCardMatch(directionReview, paper);
  if (directionMatch) {
    return directionMatch;
  }
  return null;
}

function matchStandalonePaperCard(card: ApiPaperCard | null, paper: PaperRow): PaperCardMatch | null {
  if (!card) {
    return null;
  }
  if (card.paper_id && card.paper_id === paper.id) {
    return {
      card,
      matchedBy: "paper_id",
      source: card.card_source ?? "paper_table",
    };
  }
  if (card.card_source === "direction_review_artifact" && card.paper_title) {
    const paperTitle = normalizePaperTitleKey(paper.title);
    const cardTitle = normalizePaperTitleKey(card.paper_title);
    if (paperTitle && cardTitle && paperTitle === cardTitle) {
      return { card, matchedBy: "title", source: "direction_review_artifact" };
    }
    const artifactSlug = artifactPaperSlugKey(card.source_artifact_title ?? "");
    if (isSafeArtifactSlugMatch(artifactSlug, paperTitle)) {
      return { card, matchedBy: "artifact_slug", source: "direction_review_artifact" };
    }
  }
  return null;
}

function findDirectionPaperCardMatch(
  directionReview: ApiDirectionReviewResponse | null,
  paper: PaperRow,
): PaperCardMatch | null {
  const readings = directionReview?.papers ?? [];
  const byPaperId = readings.find((reading) => {
    const readingPaperId = reading.paper_id || reading.paper.id;
    return Boolean(readingPaperId && readingPaperId === paper.id);
  });
  if (byPaperId) {
    return { card: directionReadingToPaperCard(byPaperId), matchedBy: "paper_id", source: "direction_review_artifact" };
  }

  const paperTitle = normalizePaperTitleKey(paper.title);
  const byTitle = readings.find((reading) => {
    const readingTitle = normalizePaperTitleKey(reading.paper_title || reading.paper.title);
    return Boolean(paperTitle && readingTitle && paperTitle === readingTitle);
  });
  if (byTitle) {
    return { card: directionReadingToPaperCard(byTitle), matchedBy: "title", source: "direction_review_artifact" };
  }

  const byArtifactSlug = readings.find((reading) => {
    const slug = artifactPaperSlugKey(reading.artifact_title ?? "");
    return isSafeArtifactSlugMatch(slug, paperTitle);
  });
  return byArtifactSlug
    ? { card: directionReadingToPaperCard(byArtifactSlug), matchedBy: "artifact_slug", source: "direction_review_artifact" }
    : null;
}

function directionReadingToPaperCard(reading: ApiDirectionPaperReading): ApiPaperCard {
  return {
    id: `direction-card-${reading.paper_id || reading.paper.id || normalizePaperTitleKey(reading.paper_title || reading.paper.title)}`,
    project_id: reading.paper.project_id,
    paper_id: reading.paper_id || reading.paper.id || null,
    paper_title: reading.paper_title || reading.paper.title,
    artifact_id: reading.artifact_id ?? null,
    source_artifact_title: reading.artifact_title,
    card_source: "direction_review_artifact",
    evidence_level: reading.evidence_level,
    full_text: reading.full_text,
    signals: reading.signals,
    sections: reading.sections,
    weakest_assumption: reading.weakest_assumption,
    minimal_reproduction: reading.minimal_reproduction,
    created_at: reading.paper.created_at,
  };
}

function isSafeArtifactSlugMatch(artifactSlug: string, paperTitle: string): boolean {
  return Boolean(artifactSlug.length >= 16 && paperTitle.length >= 16 && paperTitle.startsWith(artifactSlug));
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
    relevanceQuality: paper.relevance_quality ?? "medium",
    matchedTerms: paper.matched_terms ?? parseMatchedTerms(paper.matched_terms_json),
    reviewRequired: Boolean(paper.review_required),
  };
}

function parseMatchedTerms(value: string | undefined): string[] {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
  } catch {
    return [];
  }
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
  if (status === "failed" || status === "cancelled") {
    return "blocked";
  }
  return "queued";
}
