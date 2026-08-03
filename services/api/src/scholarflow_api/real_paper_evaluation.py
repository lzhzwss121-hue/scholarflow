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
    RealPaperDataset,
    RealPaperEvaluationCase,
    StrictModel,
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
    if dataset.evaluation_tier != "expert_labelled" and not allow_unreviewed:
        raise ValueError(
            "default evaluator accepts only expert_labelled datasets; "
            "unreviewed evaluation requires an explicit contract-only opt-in"
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
    prediction_map = {item.case_id: item for item in predictions.cases}
    unknown_prediction_ids = sorted(set(prediction_map) - {case.case_id for case in dataset.cases})
    if unknown_prediction_ids:
        raise ValueError(
            "predictions contain unknown case_id values: "
            + ", ".join(unknown_prediction_ids)
        )

    trusted_system_run = predictions.prediction_source == "offline_system_run"
    aggregate = _evaluate_cases(
        dataset.cases,
        prediction_map,
        recall_k=recall_k,
        trusted_system_run=trusted_system_run,
    )
    groups = {
        "by_domain": _grouped_metrics(
            dataset.cases,
            prediction_map,
            key=lambda case: case.domain,
            recall_k=recall_k,
            trusted_system_run=trusted_system_run,
        ),
        "by_paper": _grouped_metrics(
            dataset.cases,
            prediction_map,
            key=lambda case: case.paper_id,
            recall_k=recall_k,
            trusted_system_run=trusted_system_run,
        ),
        "by_evidence_level": _grouped_metrics(
            dataset.cases,
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
        else
        "这些指标来自 real_paper_unreviewed 数据，只用于验证评测代码和组织人工审核；"
        "未经专家裁决，不代表真实科研准确率，也不得与 expert_labelled 指标合并。"
    )
    return {
        "report_schema_version": EVALUATION_REPORT_VERSION,
        "dataset_id": dataset.dataset_id,
        "prediction_set_id": predictions.prediction_set_id,
        "prediction_source": predictions.prediction_source,
        "system_version": predictions.system_version,
        "evaluation_tier": dataset.evaluation_tier,
        "review_status": "adjudicated" if is_expert else "unreviewed",
        "human_review_required": not is_expert,
        "interpretation": interpretation,
        "recall_k": recall_k,
        "case_count": len(dataset.cases),
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
            acceptable = _citation_is_acceptable(citation, case)
            if acceptable:
                counts["correct_citations"] += 1
            else:
                citation_errors.extend(_citation_errors(citation, case))
            if _citation_is_locatable(citation):
                counts["locatable_citations"] += 1
            if _page_is_correct(citation, case):
                counts["correct_page_locators"] += 1
            # A missing or wrong-kind locator is still an attempted citation for
            # the gold locator type. Keeping it in the denominator prevents an
            # apparently perfect score produced by silently dropping failures.
            counts[f"{case.locator.kind}_locator_attempts"] += 1
            if _locator_is_correct(citation, case):
                counts[f"correct_{case.locator.kind}_locators"] += 1

        errors.extend(dict.fromkeys(citation_errors))
        counts["page_locator_attempts"] += len(prediction.used_citations)

        predicted_answer = execution_completed and not prediction.refused
        if predicted_answer:
            counts["predicted_answers"] += 1
        elif execution_completed:
            counts["predicted_refusals"] += 1
            if not case.answerable:
                counts["correct_refusals"] += 1

        correct_claims = 0
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
            conflict_reasons = (
                semantic_conflict_reasons(claim.statement, case.gold_claim)
                if case.gold_claim
                else []
            )
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
            claim_matches_gold = (
                case.answerable
                and _normalize_text(claim.statement) == _normalize_text(case.gold_claim)
            )
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
                    errors.append("unsupported_claim: statement does not match the annotated gold claim")

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

        answer_correct = (
            execution_completed
            and case.answerable
            and predicted_answer
            and correct_claims > 0
        )
        if answer_correct:
            counts["correct_answers"] += 1
        elif predicted_answer and not prediction.claims:
            errors.append("unsupported_answer: non-refusal output has no evaluable claims")

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
        "citation_precision": _ratio(counts["correct_citations"], counts["used_citations"]),
        "citation_locatability": _ratio(counts["locatable_citations"], counts["used_citations"]),
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
        "page_locator_accuracy": _optional_ratio(
            counts["correct_page_locators"],
            counts["page_locator_attempts"],
        ),
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
        citation.project_id == case.project_id
        and any(
            citation.citation_id == acceptable.citation_id
            and citation.paper_id == acceptable.paper_id
            and citation.page == acceptable.page
            and _normalize_text(citation.section) == _normalize_text(acceptable.section)
            and citation.locator is not None
            and citation.locator.kind == acceptable.locator.kind
            and _normalize_text(citation.locator.value)
            == _normalize_text(acceptable.locator.value)
            for acceptable in case.acceptable_citations
        )
    )


def _citation_errors(
    citation: PredictedCitation,
    case: RealPaperEvaluationCase,
) -> list[str]:
    errors: list[str] = []
    acceptable_ids = {item.citation_id for item in case.acceptable_citations}
    if citation.citation_id not in acceptable_ids:
        errors.append(f"invalid_citation: {citation.citation_id}")
    if citation.project_id != case.project_id:
        errors.append(
            f"cross_project_citation: expected {case.project_id}, got {citation.project_id}"
        )
    if citation.paper_id != case.paper_id:
        errors.append(
            f"wrong_paper: expected {case.paper_id}, got {citation.paper_id}"
        )
    if citation.page != case.page:
        errors.append(f"wrong_page: expected {case.page}, got {citation.page}")
    if _normalize_text(citation.section) != _normalize_text(case.section):
        errors.append(
            f"wrong_section: expected {case.section}, got {citation.section or '(missing)'}"
        )
    if not _locator_is_correct(citation, case):
        errors.append(
            f"wrong_{case.locator.kind}_locator: expected {case.locator.value}"
        )
    return errors


def _citation_is_locatable(citation: PredictedCitation) -> bool:
    return bool(
        citation.page
        and citation.section.strip()
        and citation.locator
        and citation.locator.value.strip()
    )


def _page_is_correct(citation: PredictedCitation, case: RealPaperEvaluationCase) -> bool:
    return citation.page == case.page


def _locator_is_correct(citation: PredictedCitation, case: RealPaperEvaluationCase) -> bool:
    return bool(
        citation.locator
        and citation.locator.kind == case.locator.kind
        and _normalize_text(citation.locator.value) == _normalize_text(case.locator.value)
    )


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
            "## 人工审核",
            "",
            (
                "该数据已经按 schema 标记为 adjudicated，但指标仍不等于论文结论真实。"
                if report.get("evaluation_tier") == "expert_labelled"
                else "所有 case 仍是 unreviewed；需要领域专家逐条核对 claim、页码、章节、表格/图和拒答标签。"
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
