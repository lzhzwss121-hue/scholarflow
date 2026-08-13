from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from scholarflow_api.rag_answer import semantic_conflict_reasons
from scholarflow_api.real_paper_dataset import (
    EvidenceLevel,
    EvidenceLocator,
    MachineLocator,
    RealPaperDataset,
    RealPaperEvaluationCase,
    StrictModel,
    AnswerComparisonResult,
    compare_answer_expectation,
    evaluation_cases,
    load_real_paper_dataset as load_audited_real_paper_dataset,
    real_paper_dataset_json_schema,
    validate_dataset_for_evaluation,
)


PREDICTION_SCHEMA_VERSION = "real_paper_predictions.v1"
EVALUATION_REPORT_VERSION = "real_paper_report.v1"

_EVIDENCE_RANK = {
    "metadata_only": 0,
    "abstract_only": 1,
    "supplemental_text": 2,
    "full_text": 3,
}
_TRUSTED_SUPPORT_METHODS = {"exact_quote", "model_checked", "human"}


class PredictedCitation(StrictModel):
    citation_id: str = Field(min_length=1, max_length=500)
    project_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    page: int | None = Field(default=None, ge=1)
    section: str = Field(default="", max_length=300)
    machine_locator: MachineLocator | None = None
    semantic_locator: EvidenceLocator | None = None
    # Deprecated compatibility field for older prediction fixtures.  It is not
    # treated as a machine anchor and citation_id is not compared with gold.
    locator: EvidenceLocator | None = None
    evidence_level: EvidenceLevel
    evidence_verified: bool


class PredictedClaim(StrictModel):
    statement: str = Field(min_length=1, max_length=5000)
    status: Literal["supported", "contradicted", "insufficient", "not_checked"]
    method: Literal[
        "exact_quote",
        "numeric_lexical",
        "rule_based",
        "model_checked",
        "human",
    ]
    citation_ids: list[str]
    evidence_level: EvidenceLevel


class PredictionSourceIdentity(StrictModel):
    paper_id: str = Field(min_length=1, max_length=200)
    doi: str = Field(default="", max_length=300)
    arxiv_id: str = Field(default="", max_length=200)
    openalex_id: str = Field(default="", max_length=300)
    version: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    resource_identifier: str = Field(min_length=1, max_length=500)


class PredictionRuntimeMetadata(StrictModel):
    runner_version: str = Field(min_length=1, max_length=200)
    rag_service: str = Field(min_length=1, max_length=300)
    database_isolation_id: str = Field(min_length=1, max_length=200)
    ingestion_status: str = Field(min_length=1, max_length=100)
    retrieval_status: str = Field(default="", max_length=100)
    answer_status: str = Field(default="", max_length=100)
    embedding_provider: str = Field(default="", max_length=200)
    embedding_model: str = Field(default="", max_length=300)
    generation_provider: str = Field(default="", max_length=200)
    generation_model: str = Field(default="", max_length=300)
    parser_version: str = Field(default="", max_length=200)
    external_data_transfer: bool = False


class RealPaperCasePrediction(StrictModel):
    case_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    refused: bool
    answer_kind: Literal["answer", "no_answer"] | None = None
    answer: str = Field(default="", max_length=50000)
    execution_status: Literal["complete", "partial", "blocked", "error"] = "complete"
    error: str = Field(default="", max_length=5000)
    retrieved_citations: list[PredictedCitation]
    used_citations: list[PredictedCitation]
    claims: list[PredictedClaim]
    source_identity: PredictionSourceIdentity | None = None
    runtime_metadata: PredictionRuntimeMetadata | None = None

    @model_validator(mode="after")
    def validate_refusal_shape(self) -> "RealPaperCasePrediction":
        if self.refused and self.claims:
            raise ValueError("refused predictions must not contain generated claims")
        if self.execution_status in {"blocked", "error"} and not self.error.strip():
            raise ValueError("blocked/error predictions require an explicit error")
        return self


class RealPaperPredictionSet(StrictModel):
    schema_version: Literal["real_paper_predictions.v1"]
    prediction_set_id: str = Field(min_length=1, max_length=300)
    system_version: str = Field(min_length=1, max_length=300)
    prediction_source: Literal[
        "offline_system_run",
        "offline_test_fixture",
        "human_baseline",
    ]
    cases: list[RealPaperCasePrediction]

    @model_validator(mode="after")
    def validate_unique_cases(self) -> "RealPaperPredictionSet":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("prediction case_id values must be unique")
        if self.prediction_source == "offline_system_run":
            invalid = [
                case.case_id
                for case in self.cases
                if case.execution_status in {"complete", "partial"}
                and (case.source_identity is None or case.runtime_metadata is None)
            ]
            if invalid:
                raise ValueError(
                    "successful offline_system_run predictions require source identity and "
                    "runtime metadata: " + ", ".join(invalid)
                )
        return self


def load_real_paper_dataset(
    path: Path,
    *,
    allow_unreviewed: bool = False,
) -> RealPaperDataset:
    return load_audited_real_paper_dataset(
        path,
        allow_unreviewed=allow_unreviewed,
    )


def load_real_paper_predictions(path: Path) -> RealPaperPredictionSet:
    return RealPaperPredictionSet.model_validate_json(path.read_text(encoding="utf-8"))


def real_paper_json_schema() -> dict[str, Any]:
    return real_paper_dataset_json_schema()


def real_paper_prediction_json_schema() -> dict[str, Any]:
    return RealPaperPredictionSet.model_json_schema()


def evaluate_real_paper_predictions(
    dataset: RealPaperDataset,
    predictions: RealPaperPredictionSet,
    *,
    recall_k: int = 5,
    allow_unreviewed: bool = False,
) -> dict[str, Any]:
    if dataset.evaluation_tier not in {"development_benchmark", "expert_labelled"} and not allow_unreviewed:
        raise ValueError(
            "default evaluator accepts development_benchmark or expert_labelled datasets; "
            "legacy unreviewed evaluation requires an explicit contract-only opt-in"
        )
    if dataset.evaluation_tier == "expert_labelled":
        readiness_errors = validate_dataset_for_evaluation(dataset)
        if readiness_errors:
            raise ValueError(
                "expert dataset is not ready for formal evaluation: "
                + "; ".join(readiness_errors)
            )
    if recall_k < 1:
        raise ValueError("recall_k must be at least 1")
    selected_cases = (
        evaluation_cases(dataset)
        if dataset.evaluation_tier in {"development_benchmark", "expert_labelled"}
        else list(dataset.cases)
    )
    if dataset.evaluation_tier == "development_benchmark" and not selected_cases:
        raise ValueError("development benchmark has no validated cases")
    prediction_map = {item.case_id: item for item in predictions.cases}
    known_case_ids = {case.case_id for case in dataset.cases}
    unknown_prediction_ids = sorted(set(prediction_map) - known_case_ids)
    if unknown_prediction_ids:
        raise ValueError(
            "predictions contain unknown case_id values: "
            + ", ".join(unknown_prediction_ids)
        )

    trusted_system_run = predictions.prediction_source == "offline_system_run"
    aggregate = _evaluate_cases(
        selected_cases,
        prediction_map,
        recall_k=recall_k,
        trusted_system_run=trusted_system_run,
    )
    groups = {
        "by_domain": _grouped_metrics(
            selected_cases,
            prediction_map,
            key=lambda case: case.domain,
            recall_k=recall_k,
            trusted_system_run=trusted_system_run,
        ),
        "by_paper": _grouped_metrics(
            selected_cases,
            prediction_map,
            key=lambda case: case.paper_id,
            recall_k=recall_k,
            trusted_system_run=trusted_system_run,
        ),
        "by_evidence_level": _grouped_metrics(
            selected_cases,
            prediction_map,
            key=lambda case: case.evidence_level,
            recall_k=recall_k,
            trusted_system_run=trusted_system_run,
        ),
    }
    is_expert = dataset.evaluation_tier == "expert_labelled"
    interpretation = (
        "这些指标来自已经人工裁决的 expert_labelled 数据，但仍只衡量给定问题与定位证据上的系统表现，"
        "不自动证明论文结论或科研事实真实。"
        if is_expert
        else (
            "这些指标来自经过固定来源、版本、页码、证据片段和机器锚点确定性校验的开发案例；"
            "用于衡量系统回归表现，不代表真实科研准确率。"
            if dataset.evaluation_tier == "development_benchmark"
            else
            "这些指标来自 legacy unreviewed 数据，只用于兼容性测试；不代表真实科研准确率。"
        )
    )
    return {
        "report_schema_version": EVALUATION_REPORT_VERSION,
        "dataset_id": dataset.dataset_id,
        "prediction_set_id": predictions.prediction_set_id,
        "prediction_source": predictions.prediction_source,
        "system_version": predictions.system_version,
        "evaluation_tier": dataset.evaluation_tier,
        "review_status": (
            "adjudicated"
            if is_expert
            else "development_validated"
            if dataset.evaluation_tier == "development_benchmark"
            else "unreviewed"
        ),
        "human_review_required": dataset.evaluation_tier == "real_paper_unreviewed",
        "expert_review_available": is_expert,
        "interpretation": interpretation,
        "recall_k": recall_k,
        "case_count": len(selected_cases),
        "excluded_case_count": len(dataset.cases) - len(selected_cases),
        "metrics": aggregate["metrics"],
        "counts": aggregate["counts"],
        "groups": groups,
        "cases": aggregate["cases"],
    }


def _evaluate_cases(
    cases: list[RealPaperEvaluationCase],
    prediction_map: dict[str, RealPaperCasePrediction],
    *,
    recall_k: int,
    trusted_system_run: bool,
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    case_results: list[dict[str, Any]] = []

    for case in cases:
        prediction = prediction_map.get(case.case_id)
        errors: list[str] = []
        counts["cases"] += 1
        counts["answerable_cases" if case.answerable else "refusal_cases"] += 1
        if prediction is None:
            errors.append("missing_prediction: no system output was supplied for this case")
            prediction = RealPaperCasePrediction(
                case_id=case.case_id,
                project_id=case.project_id,
                refused=True,
                execution_status="blocked",
                error="No system prediction was supplied.",
                retrieved_citations=[],
                used_citations=[],
                claims=[],
            )
        execution_completed = prediction.execution_status in {"complete", "partial"}
        if not execution_completed:
            counts[f"{prediction.execution_status}_predictions"] += 1
            errors.append(
                f"prediction_{prediction.execution_status}: {prediction.error or 'execution did not complete'}"
            )

        retrieved = prediction.retrieved_citations[:recall_k]
        rank = next(
            (
                index
                for index, citation in enumerate(retrieved, start=1)
                if _citation_is_acceptable(citation, case)
            ),
            0,
        )
        if case.answerable and rank:
            counts["recall_hits"] += 1
            counts["reciprocal_rank_micros"] += round(1_000_000 / rank)

        used_by_id = {item.citation_id: item for item in prediction.used_citations}
        citation_errors: list[str] = []
        for citation in prediction.used_citations:
            counts["used_citations"] += 1
            source_identity_correct = _source_identity_is_correct(citation, case)
            page_correct = _page_is_correct(citation, case)
            machine_anchor_correct = _machine_anchor_is_correct(citation, case)
            if source_identity_correct:
                counts["correct_source_identities"] += 1
            if page_correct:
                counts["correct_page_locators"] += 1
            if machine_anchor_correct:
                counts["correct_machine_anchors"] += 1
            acceptable = _citation_is_acceptable(citation, case)
            if acceptable:
                counts["correct_citations"] += 1
            else:
                citation_errors.extend(_citation_errors(citation, case))
            if _citation_is_locatable(citation):
                counts["locatable_citations"] += 1
            predicted_semantic = citation.semantic_locator
            if case.semantic_locator is not None and predicted_semantic is not None:
                counts["semantic_locator_attempts"] += 1
                counts[f"{case.semantic_locator.kind}_locator_attempts"] += 1
                if _semantic_locator_is_correct(citation, case):
                    counts["correct_semantic_locators"] += 1
                    counts[f"correct_{case.semantic_locator.kind}_locators"] += 1

        errors.extend(dict.fromkeys(citation_errors))
        counts["page_locator_attempts"] += len(prediction.used_citations)
        counts["source_identity_attempts"] += len(prediction.used_citations)
        counts["machine_anchor_attempts"] += len(prediction.used_citations)
        if case.answerable and any(
            _citation_is_acceptable(citation, case)
            for citation in prediction.used_citations
        ):
            counts["citation_recall_hits"] += 1

        prediction_is_refusal = prediction.refused or prediction.answer_kind == "no_answer"
        predicted_answer = execution_completed and not prediction_is_refusal
        if predicted_answer:
            counts["predicted_answers"] += 1
        elif execution_completed:
            counts["predicted_refusals"] += 1

        correct_claims = 0
        claim_evaluations: list[tuple[AnswerComparisonResult, bool]] = []
        for claim in prediction.claims if execution_completed else []:
            counts["claims"] += 1
            claim_citations = [
                used_by_id[citation_id]
                for citation_id in claim.citation_ids
                if citation_id in used_by_id
            ]
            missing_ids = [
                citation_id
                for citation_id in claim.citation_ids
                if citation_id not in used_by_id
            ]
            if missing_ids:
                errors.append(
                    "invalid_citation: claim references unavailable IDs "
                    + ", ".join(missing_ids)
                )
            answer_evaluation = compare_answer_expectation(
                case.answer_expectation,
                claim.statement,
                expected_reference=case.gold_claim,
                refused=False,
                answer_kind="answer",
                has_supported_claim=claim.status == "supported",
            )
            conflict_reasons = (
                semantic_conflict_reasons(claim.statement, case.gold_claim)
                if case.gold_claim
                else []
            )
            if answer_evaluation.correct_without_citation:
                ignored_prefixes: list[str] = []
                if case.answer_expectation.comparator in {
                    "numeric",
                    "numeric_with_unit",
                    "required_fact_slots",
                }:
                    ignored_prefixes.append("数字或单位不一致")
                if case.answer_expectation.accepted_aliases:
                    ignored_prefixes.extend(
                        [
                            "数据集、指标、模型或比较对象不一致",
                            "数字或单位不一致",
                        ]
                    )
                conflict_reasons = [
                    reason
                    for reason in conflict_reasons
                    if not ignored_prefixes
                    or not reason.startswith(tuple(ignored_prefixes))
                ]
            known_contradiction = any(
                _normalize_text(claim.statement) == _normalize_text(item)
                for item in case.contradiction_claims
            )
            if conflict_reasons or known_contradiction:
                counts["contradiction_opportunities"] += 1
                if claim.status == "supported":
                    counts["contradiction_escapes"] += 1
                errors.extend(conflict_reasons)
                if known_contradiction:
                    errors.append("known_contradiction: claim matches an annotated contradiction trap")

            citation_binding_ok = bool(claim_citations) and all(
                _citation_is_acceptable(citation, case)
                for citation in claim_citations
            )
            claim_evaluations.append((answer_evaluation, citation_binding_ok))
            claim_matches_gold = answer_evaluation.correct_without_citation
            support_method_ok = claim.method in _TRUSTED_SUPPORT_METHODS
            claim_correct = (
                claim.status == "supported"
                and support_method_ok
                and claim_matches_gold
                and citation_binding_ok
                and not conflict_reasons
                and not known_contradiction
            )
            if claim_correct:
                correct_claims += 1
                counts["correct_claims"] += 1
            else:
                counts["unsupported_claims"] += 1
                if claim.status == "supported" and not support_method_ok:
                    errors.append(
                        "unsupported_claim: lexical/rule status was presented as direct support"
                    )
                elif not claim_matches_gold:
                    errors.append("unsupported_claim: statement fails the deterministic answer expectation")
                    errors.extend(answer_evaluation.reasons)

            counts["evidence_assertions"] += 1
            if _evidence_false_positive(
                predicted_level=claim.evidence_level,
                evidence_verified=(
                    bool(claim_citations)
                    and all(item.evidence_verified for item in claim_citations)
                    and (trusted_system_run or citation_binding_ok)
                ),
                gold_level=case.evidence_level,
            ):
                counts["evidence_false_positives"] += 1
                errors.append("evidence_level_false_positive: predicted evidence exceeds the annotated level")

        if case.answerable:
            fallback_evaluation = compare_answer_expectation(
                case.answer_expectation,
                prediction.answer,
                expected_reference=case.gold_claim,
                refused=prediction_is_refusal,
                answer_kind=prediction.answer_kind or "",
                has_supported_claim=any(
                    claim.status == "supported" for claim in prediction.claims
                ),
            )
            if claim_evaluations:
                answer_evaluation, citation_binding_correct = max(
                    claim_evaluations,
                    key=lambda item: (
                        int(item[0].correct_without_citation),
                        int(item[0].answer_value_correct),
                        int(item[0].answer_unit_correct),
                        int(item[0].required_conditions_correct),
                        int(item[1]),
                    ),
                )
            else:
                answer_evaluation = fallback_evaluation
                citation_binding_correct = False
            counts["citation_binding_attempts"] += 1
            if citation_binding_correct:
                counts["correct_citation_bindings"] += 1
            final_answer_correct = (
                execution_completed
                and predicted_answer
                and correct_claims > 0
                and citation_binding_correct
            )
        else:
            answer_evaluation = compare_answer_expectation(
                case.answer_expectation,
                prediction.answer,
                expected_reference=case.gold_claim,
                refused=prediction.refused,
                answer_kind=prediction.answer_kind or "",
                has_supported_claim=any(
                    claim.status == "supported" for claim in prediction.claims
                ),
            )
            citation_binding_correct = None
            final_answer_correct = (
                execution_completed and answer_evaluation.correct_without_citation
            )
            if final_answer_correct:
                counts["correct_refusals"] += 1

        counts["answer_dimension_attempts"] += 1
        if answer_evaluation.answer_format_valid:
            counts["valid_answer_formats"] += 1
        if answer_evaluation.answer_value_correct:
            counts["correct_answer_values"] += 1
        if answer_evaluation.answer_unit_correct:
            counts["correct_answer_units"] += 1
        if answer_evaluation.required_conditions_correct:
            counts["correct_required_conditions"] += 1
        if final_answer_correct:
            counts["correct_final_answers"] += 1

        answer_correct = final_answer_correct
        if final_answer_correct and case.answerable:
            counts["correct_answers"] += 1
        elif predicted_answer and not prediction.claims:
            errors.append("unsupported_answer: non-refusal output has no evaluable claims")
        if not answer_evaluation.correct_without_citation:
            errors.extend(answer_evaluation.reasons)

        case_results.append(
            {
                "case_id": case.case_id,
                "paper_id": case.paper_id,
                "domain": case.domain,
                "evidence_level": case.evidence_level,
                "answerable": case.answerable,
                "predicted_refusal": prediction.refused,
                "execution_status": prediction.execution_status,
                "gold_rank": rank,
                "answer_comparator": answer_evaluation.comparator,
                "answer_format_valid": answer_evaluation.answer_format_valid,
                "answer_value_correct": answer_evaluation.answer_value_correct,
                "answer_unit_correct": answer_evaluation.answer_unit_correct,
                "required_conditions_correct": answer_evaluation.required_conditions_correct,
                "citation_binding_correct": citation_binding_correct,
                "final_answer_correct": final_answer_correct,
                "answer_correct": answer_correct,
                "errors": list(dict.fromkeys(errors)),
            }
        )

    answerable = counts["answerable_cases"]
    predicted_answers = counts["predicted_answers"]
    predicted_refusals = counts["predicted_refusals"]
    metrics = {
        f"recall_at_{recall_k}": _ratio(counts["recall_hits"], answerable),
        "mrr": _ratio(counts["reciprocal_rank_micros"], answerable * 1_000_000),
        "source_identity_accuracy": _optional_ratio(
            counts["correct_source_identities"],
            counts["source_identity_attempts"],
        ),
        "page_locator_accuracy": _optional_ratio(
            counts["correct_page_locators"],
            counts["page_locator_attempts"],
        ),
        "machine_anchor_accuracy": _optional_ratio(
            counts["correct_machine_anchors"],
            counts["machine_anchor_attempts"],
        ),
        "semantic_locator_accuracy": _optional_ratio(
            counts["correct_semantic_locators"],
            counts["semantic_locator_attempts"],
        ),
        "citation_precision": _ratio(counts["correct_citations"], counts["used_citations"]),
        "citation_recall": _ratio(counts["citation_recall_hits"], answerable),
        "citation_locatability": _ratio(counts["locatable_citations"], counts["used_citations"]),
        "answer_format_valid": _ratio(
            counts["valid_answer_formats"],
            counts["answer_dimension_attempts"],
        ),
        "answer_value_correct": _ratio(
            counts["correct_answer_values"],
            counts["answer_dimension_attempts"],
        ),
        "answer_unit_correct": _ratio(
            counts["correct_answer_units"],
            counts["answer_dimension_attempts"],
        ),
        "required_conditions_correct": _ratio(
            counts["correct_required_conditions"],
            counts["answer_dimension_attempts"],
        ),
        "citation_binding_correct": _optional_ratio(
            counts["correct_citation_bindings"],
            counts["citation_binding_attempts"],
        ),
        "final_answer_correct": _ratio(
            counts["correct_final_answers"],
            counts["answer_dimension_attempts"],
        ),
        "answer_precision": _ratio(counts["correct_answers"], predicted_answers),
        "answer_recall": _ratio(counts["correct_answers"], answerable),
        "refusal_precision": _ratio(counts["correct_refusals"], predicted_refusals),
        "refusal_recall": _ratio(counts["correct_refusals"], counts["refusal_cases"]),
        "contradiction_escape_rate": _ratio(
            counts["contradiction_escapes"],
            counts["contradiction_opportunities"],
        ),
        "evidence_level_false_positive_rate": _ratio(
            counts["evidence_false_positives"],
            counts["evidence_assertions"],
        ),
        "unsupported_claim_rate": _ratio(counts["unsupported_claims"], counts["claims"]),
        "paragraph_locator_accuracy": _optional_ratio(
            counts["correct_paragraph_locators"],
            counts["paragraph_locator_attempts"],
        ),
        "table_locator_accuracy": _optional_ratio(
            counts["correct_table_locators"],
            counts["table_locator_attempts"],
        ),
        "figure_locator_accuracy": _optional_ratio(
            counts["correct_figure_locators"],
            counts["figure_locator_attempts"],
        ),
    }
    return {
        "metrics": metrics,
        "counts": dict(sorted(counts.items())),
        "cases": case_results,
    }


def _grouped_metrics(
    cases: list[RealPaperEvaluationCase],
    prediction_map: dict[str, RealPaperCasePrediction],
    *,
    key,
    recall_k: int,
    trusted_system_run: bool,
) -> dict[str, Any]:
    groups: dict[str, list[RealPaperEvaluationCase]] = {}
    for case in cases:
        groups.setdefault(str(key(case)), []).append(case)
    return {
        group: {
            "case_count": len(group_cases),
            "metrics": _evaluate_cases(
                group_cases,
                prediction_map,
                recall_k=recall_k,
                trusted_system_run=trusted_system_run,
            )["metrics"],
        }
        for group, group_cases in sorted(groups.items())
    }


def _citation_is_acceptable(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> bool:
    return (
        _source_identity_is_correct(citation, case)
        and _page_is_correct(citation, case)
        and _machine_anchor_is_correct(citation, case)
    )


def _citation_errors(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> list[str]:
    errors: list[str] = []
    if citation.project_id != case.project_id:
        errors.append(
            f"cross_project_citation: expected {case.project_id}, got {citation.project_id}"
        )
    if citation.paper_id != case.paper_id:
        errors.append(
            f"wrong_paper: expected {case.paper_id}, got {citation.paper_id}"
        )
    machine = citation.machine_locator
    if machine is None:
        errors.append("missing_machine_locator: runtime citation has no source anchor")
    else:
        if machine.paper_id != case.paper_id:
            errors.append(
                f"wrong_machine_paper: expected {case.paper_id}, got {machine.paper_id}"
            )
        if machine.paper_version != case.paper_version:
            errors.append(
                "wrong_source_version: expected "
                f"{case.paper_version}, got {machine.paper_version}"
            )
        if machine.source_hash != case.source_hash:
            errors.append(
                f"wrong_source_hash: expected {case.source_hash}, got {machine.source_hash}"
            )
    if citation.page != case.page or (machine and machine.page != case.page):
        errors.append(f"wrong_page: expected {case.page}, got {citation.page}")
    if _normalize_section(citation.section) != case.normalized_section:
        errors.append(
            "wrong_section: expected "
            f"{case.normalized_section}, got {citation.section or '(missing)'}"
        )
    if not _machine_anchor_is_correct(citation, case):
        if any(anchor.status == "verified" for anchor in case.acceptable_source_anchors):
            errors.append("wrong_machine_anchor: chunk/excerpt hash is not approved")
        else:
            errors.append("machine_anchor_pending: no verified source anchor is labelled")
    if citation.semantic_locator is not None and not _semantic_locator_is_correct(
        citation,
        case,
    ):
        expected = case.semantic_locator
        errors.append(
            "wrong_semantic_locator: expected "
            + (expected.value if expected is not None else "none")
        )
    return errors


def _citation_is_locatable(citation: PredictedCitation) -> bool:
    machine = citation.machine_locator
    return bool(
        machine
        and machine.page
        and machine.normalized_section.strip()
        and (machine.chunk_hash or machine.evidence_excerpt_hash)
    )


def _page_is_correct(citation: PredictedCitation, case: RealPaperEvaluationCase) -> bool:
    return bool(
        citation.page == case.page
        and citation.machine_locator is not None
        and citation.machine_locator.page == case.page
    )


def _source_identity_is_correct(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> bool:
    machine = citation.machine_locator
    return bool(
        citation.project_id == case.project_id
        and citation.paper_id == case.paper_id
        and machine
        and machine.paper_id == case.paper_id
        and machine.paper_version == case.paper_version
        and machine.source_hash == case.source_hash
    )


def _machine_anchor_is_correct(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> bool:
    machine = citation.machine_locator
    if machine is None:
        return False
    for anchor in case.acceptable_source_anchors:
        if anchor.status != "verified":
            continue
        identity_matches = (
            anchor.paper_id == machine.paper_id == case.paper_id
            and anchor.paper_version == machine.paper_version == case.paper_version
            and anchor.source_hash == machine.source_hash == case.source_hash
            and anchor.page == machine.page == case.page
            and (
                not anchor.normalized_section
                or anchor.normalized_section == machine.normalized_section
            )
        )
        chunk_matches = bool(
            anchor.chunk_hash
            and machine.chunk_hash
            and anchor.chunk_hash == machine.chunk_hash
        )
        excerpt_matches = bool(
            anchor.evidence_excerpt_hash
            and machine.evidence_excerpt_hash
            and anchor.evidence_excerpt_hash == machine.evidence_excerpt_hash
        )
        if identity_matches and (chunk_matches or excerpt_matches):
            return True
    return False


def _semantic_locator_is_correct(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> bool:
    predicted = citation.semantic_locator
    expected = case.semantic_locator
    if predicted is None or expected is None:
        return False
    if predicted.kind != expected.kind:
        return False
    if _normalize_text(predicted.value) != _normalize_text(expected.value):
        return False
    for field in ("paragraph", "table", "figure", "equation"):
        expected_value = str(getattr(expected, field) or "")
        if expected_value and _normalize_text(str(getattr(predicted, field) or "")) != _normalize_text(
            expected_value
        ):
            return False
    if expected.page is not None and predicted.page != expected.page:
        return False
    if expected.section and _normalize_section(predicted.section) != _normalize_section(
        expected.section
    ):
        return False
    return True


def _evidence_false_positive(
    *,
    predicted_level: str,
    evidence_verified: bool,
    gold_level: str,
) -> bool:
    if _EVIDENCE_RANK[predicted_level] > _EVIDENCE_RANK[gold_level]:
        return True
    return predicted_level == "full_text" and not evidence_verified


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _normalize_section(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", value.casefold()).strip()


def _ratio(numerator: float, denominator: float) -> float:
    return round(float(numerator) / denominator, 6) if denominator else 0.0


def _optional_ratio(numerator: float, denominator: float) -> float | None:
    return round(float(numerator) / denominator, 6) if denominator else None


def render_real_paper_markdown(report: dict[str, Any]) -> str:
    metrics = report.get("metrics") or {}
    lines = [
        "# ScholarFlow Real-Paper RAG Evaluation",
        "",
        f"- Dataset: `{report.get('dataset_id', '')}`",
        f"- Tier: `{report.get('evaluation_tier', '')}`",
        f"- Review status: `{report.get('review_status', '')}`",
        f"- Prediction source: `{report.get('prediction_source', '')}`",
        f"- Cases: {report.get('case_count', 0)}",
        "",
        "> " + str(report.get("interpretation") or ""),
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in metrics.items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Evaluation boundary",
            "",
            (
                "可选专家数据已通过项目定义的人工审核流程，但指标仍不等于论文结论真实。"
                if report.get("evaluation_tier") == "expert_labelled"
                else "开发案例通过固定来源的确定性校验；指标只用于开发回归，不代表真实科研准确率。"
                if report.get("evaluation_tier") == "development_benchmark"
                else "Legacy 数据只用于兼容性检查，尚未通过开发来源校验。"
            ),
            "",
            "## Case diagnostics",
            "",
        ]
    )
    for case in report.get("cases") or []:
        errors = case.get("errors") or []
        lines.append(
            f"- `{case.get('case_id', '')}`: "
            f"rank={case.get('gold_rank', 0)}, answer_correct={case.get('answer_correct', False)}; "
            + ("; ".join(errors) if errors else "no deterministic contract error")
        )
    return "\n".join(lines).rstrip() + "\n"


def write_real_paper_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    resolved = output_dir.resolve()
    if not str(resolved).startswith("/private/tmp/"):
        raise ValueError("real-paper evaluation reports must be written under /private/tmp")
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "real-paper-evaluation.json"
    markdown_path = resolved / "real-paper-evaluation.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_real_paper_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}
