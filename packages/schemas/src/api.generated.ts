// This file is generated from FastAPI OpenAPI.
// Do not edit by hand. Run `npm run generate:api-types`.

export interface components {
  schemas: {
    "AgentExecuteRequest": {
        "confirmed"?: boolean;
      };
    "AgentExecuteResponse": {
        "run_id": string;
        "run_kind"?: "research_workflow";
        "agent_label"?: "Bounded Research Agent";
        "execution_mode"?: "bounded_observe_reason_act" | "deterministic_tool_graph";
        "model_call"?: components["schemas"]["ModelCallAuditRecord"] | null;
        "status": "planned" | "running" | "completed" | "completed_with_warnings" | "partial" | "failed" | "cancelled";
        "artifact"?: components["schemas"]["Artifact"] | null;
        "papers"?: Array<{
          [key: string]: unknown;
        }>;
        "paper_count"?: number;
        "summary_metrics"?: {
          [key: string]: unknown;
        };
        "run_status_summary"?: string;
        "warnings"?: Array<string>;
        "artifact_refs"?: Array<components["schemas"]["ArtifactRef"]>;
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
        "steps": Array<components["schemas"]["AgentPlanStep"]>;
        "queued_at"?: string;
        "started_at"?: string;
        "completed_at"?: string | null;
        "current_tool"?: string;
        "last_heartbeat"?: string;
        "updated_at"?: string;
      };
    "AgentPlanRequest": {
        "project_id": string;
        "task": string;
      };
    "AgentPlanResponse": {
        "run_id": string;
        "project_id": string;
        "session_id": string;
        "task": string;
        "provider": string;
        "run_kind"?: "research_workflow";
        "agent_label"?: "Bounded Research Agent";
        "execution_mode"?: "bounded_observe_reason_act" | "deterministic_tool_graph";
        "model_call": components["schemas"]["ModelCallAuditRecord"];
        "status": "planned" | "running" | "completed" | "completed_with_warnings" | "partial" | "failed" | "cancelled";
        "rationale": string;
        "steps": Array<components["schemas"]["AgentPlanStep"]>;
        "artifact": components["schemas"]["Artifact"];
      };
    "AgentPlanStep": {
        "id": string;
        "title": string;
        "detail": string;
        "tool": string;
        "status": "done" | "running" | "queued" | "partial" | "blocked" | "failed" | "cancelled";
        "metrics"?: {
          [key: string]: unknown;
        };
      };
    "AgentRunStatusResponse": {
        "run_id": string;
        "run_kind"?: "research_workflow";
        "agent_label"?: "Bounded Research Agent";
        "execution_mode"?: "bounded_observe_reason_act" | "deterministic_tool_graph";
        "model_call"?: components["schemas"]["ModelCallAuditRecord"] | null;
        "status": "planned" | "running" | "completed" | "completed_with_warnings" | "partial" | "failed" | "cancelled";
        "steps": Array<components["schemas"]["AgentPlanStep"]>;
        "summary_metrics"?: {
          [key: string]: unknown;
        };
        "warnings"?: Array<string>;
        "artifact_refs"?: Array<components["schemas"]["ArtifactRef"]>;
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
        "run_status_summary"?: string;
        "current_tool"?: string;
        "papers"?: Array<{
          [key: string]: unknown;
        }>;
        "paper_count"?: number;
        "artifact"?: components["schemas"]["Artifact"] | null;
        "queued_at"?: string;
        "started_at"?: string;
        "completed_at"?: string | null;
        "last_heartbeat"?: string;
        "updated_at": string;
      };
    "Artifact": {
        "id": string;
        "project_id": string;
        "title": string;
        "kind": string;
        "content_markdown": string;
        "content_json": string;
        "diff": string;
        "created_at": string;
        "updated_at": string;
      };
    "ArtifactCreate": {
        "project_id": string;
        "title": string;
        "kind"?: string;
        "content_markdown"?: string;
        "content_json"?: string;
        "diff"?: string;
      };
    "ArtifactRef": {
        "id": string;
        "title": string;
        "kind": string;
        "created_at": string;
      };
    "ArtifactSummary": {
        "id": string;
        "project_id": string;
        "title": string;
        "kind": string;
        "created_at": string;
        "updated_at": string;
        "markdown_bytes": number;
        "json_bytes": number;
        "markdown_preview": string;
        "json_schema_version": string;
      };
    "ArtifactSummaryPage": {
        "items": Array<components["schemas"]["ArtifactSummary"]>;
        "total": number;
        "limit": number;
        "offset": number;
        "next_offset"?: number | null;
      };
    "BaselineMap": {
        "direction": string;
        "task_definition": string;
        "classic_baselines": Array<components["schemas"]["BaselineReference"]>;
        "recent_strong_baselines": Array<components["schemas"]["BaselineReference"]>;
        "alternative_paradigms": Array<components["schemas"]["BaselineReference"]>;
        "common_benchmarks": Array<string>;
        "evaluation_risks": Array<string>;
        "open_questions": Array<string>;
        "action_plan"?: Array<string>;
        "generated_from": Array<string>;
        "evidence_summary"?: string;
        "curator_notes": string;
      };
    "BaselineReference": {
        "title": string;
        "year": string;
        "venue": string;
        "source": string;
        "url": string;
        "category": string;
        "method_family"?: string;
        "reason": string;
        "strengths": string;
        "risks": string;
        "evidence_snippets"?: Array<components["schemas"]["EvidenceSnippet"]>;
        "confidence"?: string;
        "evidence_gap"?: string;
        "comparison_role"?: string;
        "actionability_status"?: string;
        "next_action"?: string;
        "experiment_anchor"?: {
          [key: string]: string;
        };
        "verification"?: components["schemas"]["BaselineVerification"];
      };
    "BaselineVerification": {
        "evidence_level"?: string;
        "selection_basis"?: string;
        "citation_status"?: string;
        "citation_note"?: string;
        "code_status"?: string;
        "code_url"?: string;
        "code_source"?: string;
        "reproduction_status"?: string;
        "checks"?: {
          [key: string]: string;
        };
        "missing_evidence"?: Array<string>;
        "summary"?: string;
      };
    "DecisionIntent": {
        "raw_goal"?: string;
        "focus"?: string;
        "required_terms"?: Array<string>;
        "contrast_terms"?: Array<string>;
        "excluded_terms"?: Array<string>;
        "contribution_type"?: string;
        "time_budget_days"?: number | null;
      };
    "DirectionMemory": {
        "direction": string;
        "total_papers": number;
        "round_count": number;
        "summary": string;
        "paper_ids": Array<string>;
        "baseline_map"?: components["schemas"]["BaselineMap"] | null;
        "updated_at": string;
      };
    "DirectionReviewRequest": {
        "direction": string;
        "round"?: number;
      };
    "DirectionReviewResponse": {
        "direction": string;
        "round": number;
        "review_status"?: "complete" | "partial" | "blocked";
        "target_paper_count"?: number;
        "round_read_count": number;
        "relevant_read_count"?: number;
        "low_relevance_count"?: number;
        "off_topic_count"?: number;
        "relevance_coverage"?: {
          [key: string]: number;
        };
        "total_read_count": number;
        "recommended_paper_ids": Array<string>;
        "direction_summary": string;
        "artifact_refs": Array<components["schemas"]["ArtifactRef"]>;
        "errors": Array<string>;
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
      };
    "DirectionReviewRunStatusResponse": {
        "run_id": string;
        "project_id": string;
        "direction": string;
        "round": number;
        "status": "queued" | "running" | "complete" | "partial" | "blocked" | "failed" | "cancelled";
        "stage": "queued" | "scoping" | "retrieving" | "reading" | "curating" | "persisting" | "completed" | "failed" | "cancelled";
        "progress": number;
        "message": string;
        "notices"?: Array<components["schemas"]["WorkflowNoticeMessage"]>;
        "result"?: components["schemas"]["DirectionReviewResponse"] | null;
        "queued_at"?: string;
        "started_at"?: string;
        "current_tool"?: string;
        "last_heartbeat"?: string;
        "created_at": string;
        "updated_at": string;
        "completed_at"?: string | null;
      };
    "EvidencePack": {
        "evidence_level"?: string;
        "confidence"?: string;
        "source_confidence"?: string;
        "extraction_confidence"?: string;
        "snippets"?: Array<components["schemas"]["EvidenceSnippet"]>;
        "missing_evidence"?: Array<string>;
        "grounding_summary"?: string;
      };
    "EvidenceQualification": {
        "level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "verified"?: boolean;
        "source_origin"?: string;
        "character_count"?: number;
        "page_count"?: number;
        "section_names"?: Array<string>;
        "reason"?: string;
      };
    "EvidenceSnippet": {
        "id"?: string;
        "source"?: string;
        "kind"?: string;
        "text"?: string;
        "note"?: string;
        "confidence"?: string;
        "section"?: string;
        "page"?: number | null;
      };
    "ExperimentPlan": {
        "status"?: "ready" | "partial" | "blocked";
        "anchor_paper_id"?: string;
        "anchor_paper_title"?: string;
        "claim": string;
        "dataset": string;
        "baseline": string;
        "metrics": Array<string>;
        "ablations": Array<string>;
        "resources": string;
        "timeline": Array<string>;
        "success_criterion": string;
        "failure_criterion": string;
        "unblock_suggestions"?: Array<string>;
        "goal_alignment"?: {
          [key: string]: unknown;
        };
        "readiness_checks"?: {
          [key: string]: string;
        };
        "assumptions"?: Array<string>;
      };
    "FullTextProvenance": {
        "status"?: "extracted" | "supplemental_text" | "not_available" | "download_failed" | "parse_failed" | "disabled";
        "pdf_url"?: string;
        "source"?: string;
        "page_count"?: number;
        "character_count"?: number;
        "error"?: string;
        "failure_stage"?: string;
        "recovery_hint"?: string;
        "page_numbers"?: Array<number>;
        "section_names"?: Array<string>;
        "evidence_qualification"?: components["schemas"]["EvidenceQualification"];
      };
    "GapDecision": {
        "id": string;
        "title": string;
        "kind": "true_gap" | "engineering_gap" | "pseudo_gap";
        "evidence": string;
        "weakness": string;
        "opportunity": string;
        "novelty_risk": "low" | "medium" | "high";
        "feasibility": "one-week" | "one-month" | "thesis-scale";
        "support_status"?: "insufficient" | "single_source" | "corroborated" | "conflicted";
        "confidence"?: "low" | "medium" | "high";
        "paper_ids"?: Array<string>;
        "evidence_refs"?: Array<{
          [key: string]: string;
        }>;
        "validation_requirements"?: Array<string>;
        "gap_signature"?: {
          [key: string]: string;
        };
        "consistency_score"?: number;
        "conflict_detected"?: boolean;
      };
    "HTTPValidationError": {
        "detail"?: Array<components["schemas"]["ValidationError"]>;
      };
    "HealthResponse": {
        "status": string;
        "service": string;
        "version": string;
      };
    "IdeaValidation": {
        "idea": string;
        "why_not_incremental": string;
        "difference_from_existing_work": string;
        "novelty_risk": "low" | "medium" | "high";
        "feasibility": "one-week" | "one-month" | "thesis-scale";
        "key_risks": Array<string>;
      };
    "LiteratureSearchRequest": {
        "query": string;
        "max_results"?: number;
        "sources"?: Array<"arxiv" | "openalex">;
      };
    "LiteratureSearchResponse": {
        "query": string;
        "expanded_queries": Array<string>;
        "papers": Array<components["schemas"]["Paper"]>;
        "artifact": components["schemas"]["Artifact"];
        "errors": Array<string>;
        "relevance_coverage"?: {
          [key: string]: number;
        };
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
      };
    "ModelCallAuditRecord": {
        "provider": string;
        "model": string;
        "purpose": string;
        "prompt_version": string;
        "request_timestamp": string;
        "latency_ms"?: number;
        "response_status": string;
        "fallback_reason"?: string;
        "requested_provider"?: string;
        "requested_model"?: string;
        "external_data_sent"?: boolean;
        "estimated_cost_usd"?: number | null;
      };
    "Paper": {
        "id": string;
        "project_id": string;
        "title": string;
        "authors": string;
        "abstract": string;
        "year": string;
        "type": string;
        "venue": string;
        "source": string;
        "url": string;
        "pdf_url"?: string;
        "doi"?: string;
        "arxiv_id"?: string;
        "openalex_id"?: string;
        "canonical_work_id"?: string;
        "relation": string;
        "priority": string;
        "code": string;
        "relevance_score": number;
        "relevance_quality"?: "strong" | "medium" | "weak" | "off_topic";
        "matched_terms"?: Array<string>;
        "matched_terms_json"?: string;
        "review_required"?: boolean;
        "created_at": string;
      };
    "PaperCard": {
        "id": string;
        "project_id": string;
        "paper_id": string | null;
        "paper_title"?: string;
        "artifact_id": string | null;
        "source_artifact_title"?: string;
        "card_source"?: "paper_table" | "direction_review_artifact" | "manual_unbound";
        "evidence_level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_qualification"?: components["schemas"]["EvidenceQualification"];
        "full_text"?: components["schemas"]["FullTextProvenance"];
        "signals"?: components["schemas"]["PaperSignals"];
        "sections": Array<components["schemas"]["PaperCardSection"]>;
        "weakest_assumption": string;
        "minimal_reproduction": string;
        "created_at": string;
        "updated_at"?: string;
      };
    "PaperCardCreateRequest": {
        "paper_id"?: string | null;
        "title"?: string;
        "abstract"?: string;
        "paper_text"?: string;
      };
    "PaperCardResponse": {
        "card": components["schemas"]["PaperCard"];
        "artifact": components["schemas"]["Artifact"];
      };
    "PaperCardSection": {
        "id": string;
        "title": string;
        "content": string;
      };
    "PaperChunk": {
        "id": string;
        "project_id": string;
        "paper_id": string;
        "chunk_index": number;
        "source": string;
        "source_origin"?: string;
        "evidence_level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_verified"?: boolean;
        "doi"?: string;
        "arxiv_id"?: string;
        "openalex_id"?: string;
        "title"?: string;
        "section"?: string;
        "page_start"?: number | null;
        "page_end"?: number | null;
        "chunk_text": string;
        "char_count": number;
        "token_count": number;
        "chunk_hash": string;
        "index_version": string;
        "parser_version"?: string;
        "canonical_work_id"?: string;
        "embedding_model"?: string;
        "embedding_dimensions"?: number;
        "created_at": string;
        "updated_at": string;
      };
    "PaperChunkIndexRequest": {
        "paper_text"?: string;
      };
    "PaperChunkIndexStatus": {
        "paper_id": string;
        "status": "indexed" | "not_indexed" | "failed";
        "chunk_count"?: number;
        "evidence_level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "source"?: string;
        "source_origin"?: string;
        "sections"?: Array<string>;
        "page_numbers"?: Array<number>;
        "indexed_at"?: string;
        "index_version"?: string;
        "embedding_status"?: "not_started" | "partial" | "ready";
        "embedded_chunks"?: number;
        "embedding_model"?: string;
        "embedding_dimensions"?: number;
        "message"?: string;
      };
    "PaperFullTextExtractResponse": {
        "paper_id": string;
        "text"?: string;
        "evidence_level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_quality"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_qualification"?: components["schemas"]["EvidenceQualification"];
        "source"?: string;
        "page_count"?: number;
        "char_count"?: number;
        "updated_at"?: string;
        "full_text"?: components["schemas"]["FullTextProvenance"];
        "card"?: components["schemas"]["PaperCard"] | null;
        "artifact"?: components["schemas"]["Artifact"] | null;
      };
    "PaperMemoryHit": {
        "paper": components["schemas"]["Paper"];
        "direction": string;
        "round": number;
        "score": number;
        "title_score"?: number;
        "keyword_score"?: number;
        "section_score"?: number;
        "priority_score"?: number;
        "snippets": Array<string>;
        "matched_query_terms"?: Array<string>;
        "query_coverage"?: number;
        "evidence_quality"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_refs"?: Array<{
          [key: string]: string;
        }>;
        "abstract_translation": string;
        "weakest_assumption": string;
        "minimal_reproduction": string;
        "counterexample": string;
        "follow_up_idea": string;
        "why_selected": string;
        "research_sight": components["schemas"]["ResearchSight"];
        "self_read_priority": boolean;
      };
    "PaperSignals": {
        "task"?: string;
        "method"?: string;
        "dataset"?: string;
        "metric"?: string;
        "baseline"?: string;
        "claim"?: string;
        "limitation"?: string;
        "prior_work_limitation"?: string;
        "contribution_type"?: string;
        "contribution_evidence"?: string;
        "missing_signals"?: Array<string>;
        "signal_evidence"?: {
          [key: string]: components["schemas"]["SignalEvidence"];
        };
      };
    "Project": {
        "id": string;
        "title": string;
        "description": string;
        "keyword": string;
        "field": string;
        "language": string;
        "workflow": string;
        "stage": string;
        "active_session_id": string | null;
        "created_at": string;
        "updated_at": string;
        "is_demo"?: boolean;
      };
    "ProjectCreate": {
        "title": string;
        "description"?: string;
        "keyword"?: string;
        "field"?: string;
        "language"?: string;
        "workflow"?: string;
      };
    "ProjectRagIndexStatus": {
        "project_id": string;
        "total_papers"?: number;
        "indexed_papers"?: number;
        "total_chunks"?: number;
        "full_text_chunks"?: number;
        "abstract_chunks"?: number;
        "unindexed_paper_ids"?: Array<string>;
        "latest_indexed_at"?: string;
        "index_version"?: string;
        "embedding_status"?: "not_started" | "partial" | "ready";
        "embedded_chunks"?: number;
        "embedding_model"?: string;
        "embedding_dimensions"?: number;
      };
    "RagAnswerClaim": {
        "id": string;
        "statement": string;
        "citation_ids"?: Array<string>;
        "confidence"?: "low" | "medium" | "high";
        "evidence_level"?: "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "verification": components["schemas"]["RagClaimVerification"];
      };
    "RagAnswerRequest": {
        "query": string;
        "top_k"?: number;
        "paper_ids"?: Array<string>;
        "evidence_levels"?: Array<"metadata_only" | "abstract_only" | "supplemental_text" | "full_text">;
        "sections"?: Array<string>;
        "min_score"?: number;
        "max_chunks_per_paper"?: number;
        "refresh_embeddings"?: boolean;
        "language"?: "zh-CN" | "en";
      };
    "RagAnswerResponse": {
        "question": string;
        "status": "complete" | "partial" | "no_reliable_hit" | "failed";
        "answer_kind": "grounded_synthesis" | "extractive_evidence" | "no_answer";
        "answer"?: string;
        "claims"?: Array<components["schemas"]["RagAnswerClaim"]>;
        "unanswered_parts"?: Array<string>;
        "limitations"?: Array<string>;
        "retrieval": components["schemas"]["RagSearchResponse"];
        "citations"?: Array<components["schemas"]["RagSearchHit"]>;
        "citation_validation"?: components["schemas"]["RagCitationValidation"];
        "generation_provider"?: string;
        "generation_model"?: string;
        "external_data_transfer"?: boolean;
        "quality_assessment"?: components["schemas"]["RagQualityAssessment"] | null;
        "artifact"?: components["schemas"]["Artifact"] | null;
        "warnings"?: Array<string>;
      };
    "RagCitationValidation": {
        "available_citation_ids"?: Array<string>;
        "used_citation_ids"?: Array<string>;
        "rejected_citation_ids"?: Array<string>;
        "rejected_claim_count"?: number;
      };
    "RagClaimVerification": {
        "status": "supported" | "contradicted" | "insufficient" | "not_checked";
        "method": "exact_quote" | "numeric_lexical" | "rule_based" | "model_checked" | "human";
        "reasons"?: Array<string>;
        "citation_ids"?: Array<string>;
        "provider"?: string;
        "model"?: string;
        "prompt_version"?: string;
      };
    "RagEmbeddingRequest": {
        "force"?: boolean;
      };
    "RagEmbeddingStatus": {
        "scope": "project" | "paper";
        "project_id": string;
        "paper_id"?: string | null;
        "provider"?: string;
        "model"?: string;
        "dimensions"?: number;
        "requested_chunks"?: number;
        "embedded_chunks"?: number;
        "skipped_chunks"?: number;
        "failed_chunks"?: number;
        "status"?: "not_started" | "ready" | "partial" | "failed";
        "external_data_transfer"?: boolean;
        "warnings"?: Array<string>;
      };
    "RagEvaluationListResponse": {
        "project_id": string;
        "total": number;
        "evaluations"?: Array<components["schemas"]["RagEvaluationRecord"]>;
      };
    "RagEvaluationRecord": {
        "id": string;
        "project_id": string;
        "answer_artifact_id"?: string | null;
        "question": string;
        "answer_status": "complete" | "partial" | "no_reliable_hit" | "failed";
        "answer_kind": "grounded_synthesis" | "extractive_evidence" | "no_answer";
        "quality_status": "strong_evidence" | "review_required" | "safe_refusal" | "insufficient_evidence";
        "score"?: number | null;
        "generation_provider"?: string;
        "generation_model"?: string;
        "assessment": components["schemas"]["RagQualityAssessment"];
        "created_at": string;
      };
    "RagQualityAssessment": {
        "evaluation_id": string;
        "quality_status": "strong_evidence" | "review_required" | "safe_refusal" | "insufficient_evidence";
        "score"?: number | null;
        "metrics"?: {
          [key: string]: number;
        };
        "checks"?: Array<components["schemas"]["RagQualityCheck"]>;
        "strengths"?: Array<string>;
        "risk_flags"?: Array<string>;
        "human_review_required"?: boolean;
        "disclaimer": string;
        "evaluated_at": string;
      };
    "RagQualityCheck": {
        "id": string;
        "label": string;
        "status": "pass" | "warn" | "fail" | "not_applicable";
        "detail": string;
        "remediation"?: string;
      };
    "RagSearchHit": {
        "rank": number;
        "citation_id": string;
        "project_id"?: string;
        "paper_id": string;
        "paper_title": string;
        "paper_authors"?: string;
        "paper_year"?: string;
        "paper_venue"?: string;
        "paper_url"?: string;
        "chunk_id": string;
        "chunk_index": number;
        "chunk_hash": string;
        "doi"?: string;
        "arxiv_id"?: string;
        "openalex_id"?: string;
        "canonical_work_id"?: string;
        "duplicate_paper_ids"?: Array<string>;
        "source": string;
        "source_origin"?: string;
        "evidence_level": "metadata_only" | "abstract_only" | "supplemental_text" | "full_text";
        "evidence_verified"?: boolean;
        "parser_version"?: string;
        "section": string;
        "page_start"?: number | null;
        "page_end"?: number | null;
        "text": string;
        "bm25_score"?: number;
        "lexical_score": number;
        "vector_score": number;
        "hybrid_score": number;
        "anchor_coverage"?: number;
        "matched_query_terms"?: Array<string>;
        "stance"?: "support_candidate" | "counterevidence" | "context";
        "candidate_source"?: "fts5_bm25" | "bounded_embedding_pool";
        "match_strength"?: "strong" | "moderate" | "borderline";
        "match_explanation"?: string;
      };
    "RagSearchRequest": {
        "query": string;
        "top_k"?: number;
        "paper_ids"?: Array<string>;
        "evidence_levels"?: Array<"metadata_only" | "abstract_only" | "supplemental_text" | "full_text">;
        "sections"?: Array<string>;
        "min_score"?: number;
        "max_chunks_per_paper"?: number;
        "refresh_embeddings"?: boolean;
      };
    "RagSearchResponse": {
        "query": string;
        "scientific_query"?: string;
        "answer_constraints"?: Array<string>;
        "requested_facets"?: Array<string>;
        "status": "complete" | "partial" | "no_reliable_hit" | "failed";
        "retrieval_mode": "hybrid" | "lexical_only";
        "provider"?: string;
        "embedding_model"?: string;
        "embedding_dimensions"?: number;
        "external_data_transfer"?: boolean;
        "candidate_chunks"?: number;
        "fts_candidate_chunks"?: number;
        "vector_ready_chunks"?: number;
        "returned_hits"?: number;
        "top_k": number;
        "min_score": number;
        "query_anchor_terms"?: Array<string>;
        "rejected_by_relevance_gate"?: number;
        "rejected_by_evidence_gate"?: number;
        "supporting_hits"?: number;
        "counterevidence_hits"?: number;
        "lexical_backend"?: string;
        "embedding_channel"?: "lexical_hash" | "semantic_external" | "disabled";
        "pipeline_stages"?: Array<string>;
        "score_explanation"?: string;
        "hits"?: Array<components["schemas"]["RagSearchHit"]>;
        "warnings"?: Array<string>;
      };
    "ResearchDecisionRequest": {
        "goal"?: string;
      };
    "ResearchDecisionResponse": {
        "gaps": Array<components["schemas"]["GapDecision"]>;
        "validation": components["schemas"]["IdeaValidation"];
        "experiment": components["schemas"]["ExperimentPlan"];
        "artifacts": Array<components["schemas"]["Artifact"]>;
        "decision_status"?: "complete" | "partial" | "blocked";
        "evidence_quality"?: {
          [key: string]: unknown;
        };
        "warnings"?: Array<string>;
        "decision_intent"?: components["schemas"]["DecisionIntent"] | null;
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
      };
    "ResearchMemoryClaim": {
        "id": string;
        "facet"?: string;
        "statement": string;
        "support_status": "corroborated" | "single_source" | "conflicted";
        "confidence": "low" | "medium" | "high";
        "paper_ids": Array<string>;
        "evidence_refs"?: Array<{
          [key: string]: string;
        }>;
      };
    "ResearchMemoryQueryRequest": {
        "question": string;
        "direction"?: string;
        "top_k"?: number;
      };
    "ResearchMemoryQueryResponse": {
        "question": string;
        "top_k": number;
        "answer": string;
        "hits": Array<components["schemas"]["PaperMemoryHit"]>;
        "direction_memory": components["schemas"]["DirectionMemory"] | null;
        "total_memories": number;
        "reliability_status"?: string;
        "reliability_reason"?: string;
        "answer_summary"?: string;
        "claims"?: Array<components["schemas"]["ResearchMemoryClaim"]>;
        "unanswered_parts"?: Array<string>;
        "query_coverage"?: {
          [key: string]: unknown;
        };
        "source_chunks"?: Array<components["schemas"]["RagSearchHit"]>;
        "artifact": components["schemas"]["Artifact"];
        "warnings": Array<string>;
        "workflow_steps"?: Array<components["schemas"]["WorkflowStepState"]>;
      };
    "ResearchSight": {
        "motivation_sharpness": string;
        "solution_elegance": string;
        "evaluation_integrity": string;
        "paradigm_inspiration": string;
        "why_good": string;
        "why_not_good": string;
        "better_angle": string;
        "baseline_comparison": string;
        "next_step_proposal": string;
        "evidence_pack"?: components["schemas"]["EvidencePack"];
        "critique_evidence"?: Array<components["schemas"]["ResearchSightJudgment"]>;
      };
    "ResearchSightJudgment": {
        "field"?: string;
        "evidence_snippet_id"?: string;
        "confidence"?: string;
        "rationale"?: string;
      };
    "Session": {
        "id": string;
        "project_id": string;
        "title": string;
        "status": string;
        "created_at": string;
        "updated_at": string;
      };
    "SignalEvidence": {
        "field"?: string;
        "canonical_value"?: string;
        "raw_value"?: string;
        "source"?: string;
        "section"?: string;
        "page"?: number | null;
        "quote"?: string;
        "confidence"?: string;
        "validation_errors"?: Array<string>;
        "evidence_refs"?: Array<components["schemas"]["SignalEvidenceRef"]>;
        "availability"?: "verified" | "partial" | "missing" | "invalid";
      };
    "SignalEvidenceRef": {
        "canonical_value"?: string;
        "raw_value"?: string;
        "source"?: string;
        "section"?: string;
        "page"?: number | null;
        "quote"?: string;
        "confidence"?: string;
        "validation_errors"?: Array<string>;
      };
    "ToolEvent": {
        "id": string;
        "session_id": string;
        "time_label": string;
        "tool": string;
        "status": "done" | "running" | "queued" | "partial" | "blocked" | "failed" | "cancelled";
        "summary": string;
        "created_at": string;
      };
    "ValidationError": {
        "loc": Array<string | number>;
        "msg": string;
        "type": string;
        "input"?: unknown;
        "ctx"?: Record<string, never>;
      };
    "WorkflowNoticeMessage": {
        "severity": "info" | "warning" | "error";
        "code": string;
        "stage": string;
        "message": string;
        "occurred_at": string;
      };
    "WorkflowStepState": {
        "step_id": string;
        "status": "idle" | "ready" | "running" | "partial" | "complete" | "blocked" | "error";
        "label": string;
        "summary": string;
        "warnings"?: Array<string>;
        "errors"?: Array<string>;
        "artifact_refs"?: Array<components["schemas"]["ArtifactRef"]>;
        "updated_at": string;
      };
  };
}

export interface paths {
  "/agent/plan": {
    post: { operationId: "create_agent_plan_agent_plan_post" };
  };
  "/agent/runs/{run_id}": {
    get: { operationId: "get_agent_run_status_agent_runs__run_id__get" };
  };
  "/agent/runs/{run_id}/cancel": {
    post: { operationId: "cancel_agent_run_agent_runs__run_id__cancel_post" };
  };
  "/agent/runs/{run_id}/execute": {
    post: { operationId: "execute_agent_run_agent_runs__run_id__execute_post" };
  };
  "/artifacts": {
    post: { operationId: "save_artifact_artifacts_post" };
  };
  "/artifacts/{artifact_id}": {
    get: { operationId: "get_artifact_artifacts__artifact_id__get" };
  };
  "/health": {
    get: { operationId: "health_health_get" };
  };
  "/health/jobs": {
    get: { operationId: "jobs_health_health_jobs_get" };
  };
  "/projects": {
    get: { operationId: "list_projects_projects_get" };
    post: { operationId: "create_project_projects_post" };
  };
  "/projects/{project_id}": {
    get: { operationId: "get_project_projects__project_id__get" };
  };
  "/projects/{project_id}/artifacts": {
    get: { operationId: "list_project_artifact_summaries_projects__project_id__artifacts_get" };
  };
  "/projects/{project_id}/artifacts/summary": {
    get: { operationId: "list_project_artifact_summaries_projects__project_id__artifacts_summary_get" };
  };
  "/projects/{project_id}/direction-review-runs": {
    post: { operationId: "start_project_direction_review_run_projects__project_id__direction_review_runs_post" };
  };
  "/projects/{project_id}/direction-review-runs/latest": {
    get: { operationId: "get_latest_project_direction_review_run_projects__project_id__direction_review_runs_latest_get" };
  };
  "/projects/{project_id}/direction-review-runs/{run_id}": {
    get: { operationId: "get_project_direction_review_run_projects__project_id__direction_review_runs__run_id__get" };
  };
  "/projects/{project_id}/direction-review-runs/{run_id}/cancel": {
    post: { operationId: "cancel_project_direction_review_run_projects__project_id__direction_review_runs__run_id__cancel_post" };
  };
  "/projects/{project_id}/direction-reviews": {
    post: { operationId: "create_project_direction_review_projects__project_id__direction_reviews_post" };
  };
  "/projects/{project_id}/literature/search": {
    post: { operationId: "search_project_literature_projects__project_id__literature_search_post" };
  };
  "/projects/{project_id}/paper-cards": {
    get: { operationId: "list_project_paper_cards_projects__project_id__paper_cards_get" };
    post: { operationId: "create_project_paper_card_projects__project_id__paper_cards_post" };
  };
  "/projects/{project_id}/papers": {
    get: { operationId: "list_project_papers_projects__project_id__papers_get" };
  };
  "/projects/{project_id}/papers/{paper_id}/chunks": {
    get: { operationId: "list_project_paper_chunks_projects__project_id__papers__paper_id__chunks_get" };
  };
  "/projects/{project_id}/papers/{paper_id}/full-text": {
    post: { operationId: "extract_project_paper_full_text_projects__project_id__papers__paper_id__full_text_post" };
  };
  "/projects/{project_id}/papers/{paper_id}/rag-index": {
    get: { operationId: "get_paper_rag_index_status_projects__project_id__papers__paper_id__rag_index_get" };
    post: { operationId: "rebuild_project_paper_rag_index_projects__project_id__papers__paper_id__rag_index_post" };
    delete: { operationId: "delete_project_paper_rag_index_projects__project_id__papers__paper_id__rag_index_delete" };
  };
  "/projects/{project_id}/papers/{paper_id}/rag-index/embeddings": {
    post: { operationId: "embed_project_paper_rag_index_projects__project_id__papers__paper_id__rag_index_embeddings_post" };
  };
  "/projects/{project_id}/rag-answer": {
    post: { operationId: "create_project_rag_answer_projects__project_id__rag_answer_post" };
  };
  "/projects/{project_id}/rag-evaluations": {
    get: { operationId: "get_project_rag_evaluations_projects__project_id__rag_evaluations_get" };
  };
  "/projects/{project_id}/rag-index": {
    get: { operationId: "get_project_rag_index_status_projects__project_id__rag_index_get" };
  };
  "/projects/{project_id}/rag-index/embeddings": {
    post: { operationId: "embed_project_rag_index_projects__project_id__rag_index_embeddings_post" };
  };
  "/projects/{project_id}/rag-search": {
    post: { operationId: "search_project_rag_projects__project_id__rag_search_post" };
  };
  "/projects/{project_id}/research-decisions": {
    post: { operationId: "create_project_research_decisions_projects__project_id__research_decisions_post" };
  };
  "/projects/{project_id}/research-memory/query": {
    post: { operationId: "query_project_research_memory_projects__project_id__research_memory_query_post" };
  };
  "/projects/{project_id}/sessions": {
    get: { operationId: "list_project_sessions_projects__project_id__sessions_get" };
  };
  "/projects/{project_id}/timeline": {
    get: { operationId: "get_project_timeline_projects__project_id__timeline_get" };
  };
  "/sessions/{session_id}/timeline": {
    get: { operationId: "get_session_timeline_sessions__session_id__timeline_get" };
  };
}

export type ApiSchema<Name extends keyof components["schemas"]> =
  components["schemas"][Name];
