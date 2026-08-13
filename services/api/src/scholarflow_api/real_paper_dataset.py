from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REAL_PAPER_DATASET_SCHEMA_VERSION = "real_paper_dataset.v3"
MINIMUM_EXPERT_CASES = 50
MINIMUM_DEVELOPMENT_CASES = 50
MAXIMUM_TARGET_CASES = 100

EvaluationTier = Literal[
    "constructed_fixture",
    "development_benchmark",
    "expert_labelled",
    "live_external_smoke",
    "real_paper_unreviewed",  # legacy compatibility only
]
DevelopmentStatus = Literal[
    "generated",
    "validated",
    "invalid",
    "disabled",
    "maintainer_verified",
]
AnswerComparator = Literal[
    "exact_text",
    "normalized_text",
    "numeric_unit",
    "refusal",
]
ExpectationComparator = Literal[
    "exact",
    "normalized_text",
    "numeric",
    "numeric_with_unit",
    "boolean",
    "categorical",
    "unordered_set",
    "required_fact_slots",
    "refusal",
]
ReviewStatus = Literal[
    "draft",
    "independently_reviewed",
    "adjudicated",
    "expert_labelled",
]
Split = Literal["train", "dev", "test"]
Answerability = Literal["answerable", "refusal"]
EvidenceLevel = Literal[
    "metadata_only",
    "abstract_only",
    "supplemental_text",
    "full_text",
]
EvidenceType = Literal[
    "metadata",
    "abstract",
    "main_text",
    "table",
    "figure",
    "equation",
    "supplemental_material",
]
LocatorKind = Literal[
    "metadata",
    "abstract",
    "paragraph",
    "table",
    "figure",
    "equation",
    "chunk",
]
AnchorStatus = Literal["verified", "pending"]
CaseType = Literal[
    "answerable",
    "refusal",
    "metadata_insufficient",
    "abstract_insufficient",
    "table",
    "figure_caption",
    "equation",
    "experiment_setup",
    "dataset_metric",
    "numeric_unit_condition",
    "correlation_causality",
    "supplemental_material",
    "version_conflict",
    "no_reliable_hit",
]

_STATUS_ORDER: tuple[ReviewStatus, ...] = (
    "draft",
    "independently_reviewed",
    "adjudicated",
    "expert_labelled",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerExpectation(StrictModel):
    """Deterministic answer contract; it is gold data and never runner input."""

    comparator: ExpectationComparator
    expected_value: (
        str
        | int
        | float
        | bool
        | list[str]
        | dict[str, str | int | float | bool]
        | None
    ) = None
    expected_unit: str = Field(default="", max_length=100)
    absolute_tolerance: float = Field(default=0.0, ge=0)
    relative_tolerance: float = Field(default=0.0, ge=0)
    accepted_aliases: list[str] = Field(default_factory=list, max_length=100)
    required_terms: list[str] = Field(default_factory=list, max_length=100)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=100)
    expected_refusal: bool = False

    @model_validator(mode="after")
    def validate_comparator_shape(self) -> "AnswerExpectation":
        for field_name in ("accepted_aliases", "required_terms", "forbidden_terms"):
            values = getattr(self, field_name)
            normalized = [_norm(value) for value in values]
            if any(not value for value in normalized):
                raise ValueError(f"{field_name} cannot contain blank values")
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{field_name} must be unique after normalization")

        if self.comparator == "refusal":
            if not self.expected_refusal:
                raise ValueError("refusal comparator requires expected_refusal=true")
            if self.expected_value not in (None, ""):
                raise ValueError("refusal comparator cannot define expected_value")
            return self
        if self.expected_refusal:
            raise ValueError("expected_refusal=true requires the refusal comparator")
        if self.comparator in {"exact", "normalized_text", "categorical"}:
            if not isinstance(self.expected_value, str) or not self.expected_value.strip():
                raise ValueError(f"{self.comparator} requires a non-empty string expected_value")
        elif self.comparator in {"numeric", "numeric_with_unit"}:
            if not _expected_numbers(self.expected_value):
                raise ValueError(f"{self.comparator} requires a numeric expected_value")
            if self.comparator == "numeric_with_unit" and not self.expected_unit.strip():
                raise ValueError("numeric_with_unit requires expected_unit")
        elif self.comparator == "boolean":
            if not isinstance(self.expected_value, (bool, str)):
                raise ValueError("boolean requires a bool or explicit string expected_value")
        elif self.comparator == "unordered_set":
            if not isinstance(self.expected_value, list) or not self.expected_value:
                raise ValueError("unordered_set requires a non-empty string list")
        elif self.comparator == "required_fact_slots":
            if not isinstance(self.expected_value, dict) or not self.expected_value:
                raise ValueError("required_fact_slots requires a non-empty object")
        return self


class AnswerComparisonResult(StrictModel):
    comparator: ExpectationComparator
    answer_format_valid: bool
    answer_value_correct: bool
    answer_unit_correct: bool
    required_conditions_correct: bool
    reasons: list[str] = Field(default_factory=list)

    @property
    def correct_without_citation(self) -> bool:
        return (
            self.answer_format_valid
            and self.answer_value_correct
            and self.answer_unit_correct
            and self.required_conditions_correct
        )


class EvidenceLocator(StrictModel):
    kind: LocatorKind
    value: str = Field(min_length=1, max_length=240)
    page: int | None = Field(default=None, ge=1)
    section: str = Field(default="", max_length=300)
    paragraph: str = Field(default="", max_length=120)
    table: str = Field(default="", max_length=120)
    figure: str = Field(default="", max_length=120)
    equation: str = Field(default="", max_length=120)
    supplementary: bool = False


class MachineLocator(StrictModel):
    """Parser/index-derived identity for a runtime evidence block.

    Empty chunk/excerpt hashes mean that no machine anchor was available.  A
    semantic label is deliberately not inferred from the chunk text here.
    """

    paper_id: str = Field(min_length=1, max_length=200)
    paper_version: str = Field(min_length=1, max_length=200)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1)
    normalized_section: str = Field(default="", max_length=300)
    chunk_index: int | None = Field(default=None, ge=0)
    chunk_hash: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    evidence_excerpt_hash: str = Field(
        default="",
        pattern=r"^(?:[0-9a-f]{64})?$",
    )

    @model_validator(mode="after")
    def normalize_machine_section(self) -> "MachineLocator":
        self.normalized_section = normalize_section(self.normalized_section)
        return self


class AcceptableSourceAnchor(StrictModel):
    """Human-approved machine anchor for one fixed paper version.

    Draft cases may carry a pending anchor with no chunk/excerpt hash.  Such an
    anchor documents the intended source/page but cannot receive machine-anchor
    credit until an actual fixed-PDF run has been reviewed.
    """

    paper_id: str = Field(min_length=1, max_length=200)
    paper_version: str = Field(min_length=1, max_length=200)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    normalized_section: str = Field(default="", max_length=300)
    chunk_hash: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")
    evidence_excerpt_hash: str = Field(
        default="",
        pattern=r"^(?:[0-9a-f]{64})?$",
    )
    status: AnchorStatus = "pending"

    @model_validator(mode="after")
    def validate_anchor_status(self) -> "AcceptableSourceAnchor":
        self.normalized_section = normalize_section(self.normalized_section)
        if self.status == "verified" and not (
            self.chunk_hash or self.evidence_excerpt_hash
        ):
            raise ValueError(
                "verified source anchors require chunk_hash or evidence_excerpt_hash"
            )
        return self

class AcceptableCitation(StrictModel):
    citation_id: str = Field(min_length=1, max_length=500)
    paper_id: str = Field(min_length=1, max_length=200)
    paper_version: str = Field(min_length=1, max_length=200)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    section: str = Field(min_length=1, max_length=300)
    locator: EvidenceLocator


class IndependentAnnotationResult(StrictModel):
    reviewer_id: str = Field(min_length=1, max_length=300)
    completed_at: datetime
    independently_completed: Literal[True]
    answerability: Answerability
    gold_claim: str = Field(max_length=5000)
    evidence_type: EvidenceType
    evidence_level: EvidenceLevel
    evidence_locator: EvidenceLocator
    acceptable_citations: list[AcceptableCitation]
    notes: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_answer_shape(self) -> "IndependentAnnotationResult":
        if self.completed_at.tzinfo is None:
            raise ValueError("independent review completed_at must include a timezone")
        _validate_answer_and_citations(
            answerability=self.answerability,
            gold_claim=self.gold_claim,
            citations=self.acceptable_citations,
            context="independent annotation",
        )
        return self


class AdjudicatorResult(StrictModel):
    adjudicator_id: str = Field(min_length=1, max_length=300)
    completed_at: datetime
    answerability: Answerability
    gold_claim: str = Field(max_length=5000)
    evidence_type: EvidenceType
    evidence_level: EvidenceLevel
    evidence_locator: EvidenceLocator
    acceptable_citations: list[AcceptableCitation]
    resolved_disagreement_fields: list[str]
    rationale: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_answer_shape(self) -> "AdjudicatorResult":
        if self.completed_at.tzinfo is None:
            raise ValueError("adjudicator completed_at must include a timezone")
        _validate_answer_and_citations(
            answerability=self.answerability,
            gold_claim=self.gold_claim,
            citations=self.acceptable_citations,
            context="adjudicator result",
        )
        if len(self.resolved_disagreement_fields) != len(
            set(self.resolved_disagreement_fields)
        ):
            raise ValueError("resolved_disagreement_fields must be unique")
        return self


class RealPaperEvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    paper_version: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_page_count: int = Field(ge=1)
    domain: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=3000)
    development_status: DevelopmentStatus = "generated"
    answer_expectation: AnswerExpectation | None = None
    # Deprecated compatibility fields. New datasets should use
    # answer_expectation; old gold_claim-only cases map to normalized_text.
    expected_answer: str = Field(default="", max_length=5000)
    answer_comparator: AnswerComparator = "normalized_text"
    refusal_probe_terms: list[str] = Field(default_factory=list, max_length=50)
    validation_errors: list[str] = Field(default_factory=list, max_length=100)
    answerability: Answerability
    gold_claim: str = Field(max_length=5000)
    evidence_type: EvidenceType
    evidence_level: EvidenceLevel
    evidence_excerpt: str = Field(default="", max_length=500)
    evidence_locator: EvidenceLocator
    page: int | None = Field(default=None, ge=1)
    normalized_section: str = Field(default="", max_length=300)
    evidence_excerpt_hash: str = Field(
        default="",
        pattern=r"^(?:[0-9a-f]{64})?$",
    )
    semantic_locator: EvidenceLocator | None = None
    acceptable_source_anchors: list[AcceptableSourceAnchor] = Field(
        default_factory=list
    )
    # Deprecated compatibility field.  Runtime evaluation uses
    # acceptable_source_anchors and never requires citation_id equality.
    acceptable_citations: list[AcceptableCitation]
    direct_support_found: bool
    contradiction_notes: list[str]
    contradiction_claims: list[str] = Field(default_factory=list)
    version_notes: str = Field(default="", max_length=3000)
    annotator_a_result: IndependentAnnotationResult | None = None
    annotator_b_result: IndependentAnnotationResult | None = None
    disagreement_fields: list[str] = Field(default_factory=list)
    adjudicator_result: AdjudicatorResult | None = None
    adjudication_date: date | None = None
    review_status: ReviewStatus = "draft"
    label_origin: Literal[
        "generated",
        "human_draft",
        "human_annotation",
        "imported_bibliographic_fixture",
    ] = "generated"
    split: Split
    case_types: list[CaseType] = Field(min_length=1)

    @property
    def answerable(self) -> bool:
        return self.answerability == "answerable"

    @property
    def source(self) -> str:
        return self.source_url

    @property
    def version(self) -> str:
        return self.paper_version

    @property
    def section(self) -> str:
        return self.normalized_section

    @property
    def locator(self) -> EvidenceLocator:
        return self.semantic_locator or self.evidence_locator

    @property
    def adjudication_status(self) -> str:
        if self.review_status in {"adjudicated", "expert_labelled"}:
            return "adjudicated"
        if self.review_status == "independently_reviewed":
            return "pending"
        return "unreviewed"

    @model_validator(mode="after")
    def validate_audit_contract(self) -> "RealPaperEvaluationCase":
        locator_page = self.evidence_locator.page or 1
        if self.page is None:
            self.page = locator_page
        elif self.page != locator_page:
            raise ValueError("case page and evidence_locator page disagree")
        expected_section = normalize_section(self.evidence_locator.section)
        if not self.normalized_section:
            self.normalized_section = expected_section
        elif normalize_section(self.normalized_section) != expected_section:
            raise ValueError(
                "normalized_section must match evidence_locator.section"
            )
        else:
            self.normalized_section = normalize_section(self.normalized_section)
        if self.semantic_locator is None:
            self.semantic_locator = self.evidence_locator
        elif _model_key(self.semantic_locator) != _model_key(self.evidence_locator):
            raise ValueError("semantic_locator must match evidence_locator")

        if self.answer_expectation is None:
            self.answer_expectation = _legacy_answer_expectation(self)

        self._validate_development_contract()

        _validate_answer_and_citations(
            answerability=self.answerability,
            gold_claim=self.gold_claim,
            citations=self.acceptable_citations,
            context="case",
        )
        if self.answerable and not self.direct_support_found:
            raise ValueError("answerable cases require reliable direct support")
        if not self.answerable and self.direct_support_found:
            raise ValueError("refusal cases cannot contain direct support evidence")
        expected_case_type = "answerable" if self.answerable else "refusal"
        if expected_case_type not in self.case_types:
            raise ValueError(f"case_types must include {expected_case_type}")
        if len(self.case_types) != len(set(self.case_types)):
            raise ValueError("case_types must be unique")
        self._validate_citations(self.acceptable_citations, "case")
        self._validate_source_anchors(self.acceptable_source_anchors, "case")
        self._validate_locator(self.evidence_locator, "case")

        reviewers = [
            result
            for result in (self.annotator_a_result, self.annotator_b_result)
            if result is not None
        ]
        if len(reviewers) == 2 and reviewers[0].reviewer_id == reviewers[1].reviewer_id:
            raise ValueError("annotator A and B must be distinct independent reviewers")
        for result in reviewers:
            self._validate_citations(
                result.acceptable_citations,
                f"reviewer {result.reviewer_id}",
            )
            self._validate_locator(result.evidence_locator, f"reviewer {result.reviewer_id}")

        if self.review_status != "draft" and len(reviewers) != 2:
            raise ValueError(
                f"{self.review_status} requires two independent reviewers"
            )
        derived_disagreements = annotation_disagreement_fields(
            self.annotator_a_result,
            self.annotator_b_result,
        )
        if self.review_status != "draft" and sorted(self.disagreement_fields) != sorted(
            derived_disagreements
        ):
            raise ValueError(
                "disagreement_fields must exactly match the two independent reviews"
            )

        if self.review_status in {"adjudicated", "expert_labelled"}:
            if self.adjudicator_result is None or self.adjudication_date is None:
                raise ValueError(
                    f"{self.review_status} requires an adjudicator result and date"
                )
            self._validate_adjudication(derived_disagreements)
        if self.review_status == "expert_labelled":
            if self.label_origin != "human_annotation":
                raise ValueError("expert_labelled requires human_annotation origin")
            reviewer_ids = {result.reviewer_id for result in reviewers}
            if self.adjudicator_result and self.adjudicator_result.adjudicator_id in reviewer_ids:
                raise ValueError("adjudicator must be independent from annotator A and B")
        return self

    def _validate_development_contract(self) -> None:
        if self.development_status == "invalid" and not self.validation_errors:
            raise ValueError("invalid development cases require validation_errors")
        if self.development_status in {"validated", "maintainer_verified"}:
            if self.validation_errors:
                raise ValueError("validated development cases cannot retain validation_errors")
            if self.answerable:
                if self.answer_expectation is None:
                    raise ValueError("validated answerable cases require answer_expectation")
                if self.answer_expectation.comparator == "refusal":
                    raise ValueError("answerable cases cannot use the refusal comparator")
                if not self.evidence_excerpt.strip():
                    raise ValueError("validated answerable cases require evidence_excerpt")
                if self.evidence_excerpt_hash != evidence_excerpt_checksum(
                    self.evidence_excerpt
                ):
                    raise ValueError(
                        "validated answerable cases require a matching evidence_excerpt_hash"
                    )
                if not any(
                    anchor.status == "verified"
                    and (anchor.chunk_hash or anchor.evidence_excerpt_hash)
                    for anchor in self.acceptable_source_anchors
                ):
                    raise ValueError(
                        "validated answerable cases require a verified machine anchor"
                    )
            else:
                if self.answer_expectation is None:
                    raise ValueError("validated refusal cases require answer_expectation")
                if self.answer_expectation.comparator != "refusal":
                    raise ValueError("validated refusal cases require the refusal comparator")
                if not self.refusal_probe_terms:
                    raise ValueError(
                        "validated refusal cases require deterministic refusal_probe_terms"
                    )
            if not expected_answer_matches_gold(self):
                raise ValueError(
                    "answer_expectation does not match gold_claim under its comparator"
                )

    def _validate_source_anchors(
        self,
        anchors: list[AcceptableSourceAnchor],
        context: str,
    ) -> None:
        for anchor in anchors:
            if anchor.paper_id != self.paper_id:
                raise ValueError(f"{context} source anchor points to the wrong paper_id")
            if anchor.paper_version != self.paper_version:
                raise ValueError(
                    f"{context} source anchor points to the wrong paper version"
                )
            if anchor.source_hash != self.source_hash:
                raise ValueError(
                    f"{context} source anchor points to the wrong source hash"
                )
            if anchor.page > self.source_page_count:
                raise ValueError(
                    f"{context} source anchor page exceeds source_page_count "
                    f"({anchor.page}>{self.source_page_count})"
                )

    def _validate_locator(self, locator: EvidenceLocator, context: str) -> None:
        specific = {
            "table": locator.table,
            "figure": locator.figure,
            "equation": locator.equation,
        }.get(locator.kind)
        if specific is not None and not specific.strip():
            raise ValueError(
                f"{context} {locator.kind} locator requires its explicit "
                f"{locator.kind} field"
            )
        if locator.page is not None and locator.page > self.source_page_count:
            raise ValueError(
                f"{context} locator page exceeds source_page_count "
                f"({locator.page}>{self.source_page_count})"
            )

    def _validate_citations(
        self,
        citations: list[AcceptableCitation],
        context: str,
    ) -> None:
        for citation in citations:
            if citation.paper_id != self.paper_id:
                raise ValueError(f"{context} citation points to the wrong paper_id")
            if citation.paper_version != self.paper_version:
                raise ValueError(f"{context} citation points to the wrong paper version")
            if citation.source_hash != self.source_hash:
                raise ValueError(f"{context} citation points to the wrong source hash")
            if citation.page > self.source_page_count:
                raise ValueError(
                    f"{context} citation page exceeds source_page_count "
                    f"({citation.page}>{self.source_page_count})"
                )
            if citation.locator.page not in {None, citation.page}:
                raise ValueError(f"{context} citation page and locator page disagree")
            self._validate_locator(citation.locator, context)

    def _validate_adjudication(self, derived_disagreements: list[str]) -> None:
        assert self.adjudicator_result is not None
        adjudication = self.adjudicator_result
        self._validate_citations(adjudication.acceptable_citations, "adjudicator")
        self._validate_locator(adjudication.evidence_locator, "adjudicator")
        unresolved = sorted(
            set(derived_disagreements) - set(adjudication.resolved_disagreement_fields)
        )
        if unresolved:
            raise ValueError("unresolved disagreement fields: " + ", ".join(unresolved))
        if self.adjudication_date != adjudication.completed_at.date():
            raise ValueError("adjudication_date must match adjudicator completion date")
        final_pairs = (
            ("answerability", self.answerability, adjudication.answerability),
            ("gold_claim", _norm(self.gold_claim), _norm(adjudication.gold_claim)),
            ("evidence_type", self.evidence_type, adjudication.evidence_type),
            ("evidence_level", self.evidence_level, adjudication.evidence_level),
            (
                "evidence_locator",
                _model_key(self.evidence_locator),
                _model_key(adjudication.evidence_locator),
            ),
            (
                "acceptable_citations",
                _citation_keys(self.acceptable_citations),
                _citation_keys(adjudication.acceptable_citations),
            ),
        )
        mismatches = [name for name, current, final in final_pairs if current != final]
        if mismatches:
            raise ValueError(
                "adjudicated top-level gold must match adjudicator result: "
                + ", ".join(mismatches)
            )


class RealPaperDataset(StrictModel):
    schema_version: Literal["real_paper_dataset.v2", "real_paper_dataset.v3"]
    dataset_id: str = Field(min_length=1, max_length=300)
    evaluation_tier: EvaluationTier
    description: str = Field(min_length=1, max_length=3000)
    target_case_count: int = Field(default=50, ge=50, le=100)
    cases: list[RealPaperEvaluationCase]

    @model_validator(mode="after")
    def validate_dataset_contract(self) -> "RealPaperDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        paper_splits: dict[str, str] = {}
        paper_identities: dict[str, tuple[str, str, str, int]] = {}
        for case in self.cases:
            previous = paper_splits.setdefault(case.paper_id, case.split)
            if previous != case.split:
                raise ValueError(
                    f"paper_id cannot appear in multiple splits: {case.paper_id} "
                    f"({previous}, {case.split})"
                )
            identity = (
                case.paper_version,
                case.source_url,
                case.source_hash,
                case.source_page_count,
            )
            previous_identity = paper_identities.setdefault(case.paper_id, identity)
            if previous_identity != identity:
                raise ValueError(
                    f"paper_id has inconsistent source version/hash identity: {case.paper_id}"
                )
        _validate_near_duplicates(self.cases)
        if self.evaluation_tier == "expert_labelled":
            invalid = [
                case.case_id
                for case in self.cases
                if case.review_status != "expert_labelled"
                or case.label_origin != "human_annotation"
            ]
            if invalid:
                raise ValueError(
                    "expert_labelled datasets may contain only fully adjudicated human cases: "
                    + ", ".join(invalid)
                )
        return self


def load_real_paper_dataset(
    path: Path,
    *,
    allow_unreviewed: bool = False,
) -> RealPaperDataset:
    dataset = RealPaperDataset.model_validate_json(path.read_text(encoding="utf-8"))
    if not allow_unreviewed and dataset.evaluation_tier not in {
        "development_benchmark",
        "expert_labelled",
    }:
        raise ValueError(
            "default real-paper evaluation accepts development_benchmark or "
            "expert_labelled datasets; pass allow_unreviewed=True only for legacy tooling"
        )
    return dataset


def evaluation_cases(dataset: RealPaperDataset) -> list[RealPaperEvaluationCase]:
    if dataset.evaluation_tier == "development_benchmark":
        return [
            case
            for case in dataset.cases
            if case.development_status in {"validated", "maintainer_verified"}
        ]
    if dataset.evaluation_tier == "expert_labelled":
        return list(dataset.cases)
    return []


def real_paper_dataset_json_schema() -> dict[str, Any]:
    return RealPaperDataset.model_json_schema()


def annotation_disagreement_fields(
    first: IndependentAnnotationResult | None,
    second: IndependentAnnotationResult | None,
) -> list[str]:
    if first is None or second is None:
        return []
    comparisons = (
        ("answerability", first.answerability, second.answerability),
        ("gold_claim", _norm(first.gold_claim), _norm(second.gold_claim)),
        ("evidence_type", first.evidence_type, second.evidence_type),
        ("evidence_level", first.evidence_level, second.evidence_level),
        (
            "evidence_locator",
            _model_key(first.evidence_locator),
            _model_key(second.evidence_locator),
        ),
        (
            "acceptable_citations",
            _citation_keys(first.acceptable_citations),
            _citation_keys(second.acceptable_citations),
        ),
    )
    return [name for name, left, right in comparisons if left != right]


def promote_case(
    case: RealPaperEvaluationCase,
    *,
    target_status: ReviewStatus | None = None,
) -> RealPaperEvaluationCase:
    validated = RealPaperEvaluationCase.model_validate(case.model_dump())
    current_index = _STATUS_ORDER.index(validated.review_status)
    if current_index == len(_STATUS_ORDER) - 1:
        raise ValueError("case is already expert_labelled")
    expected = _STATUS_ORDER[current_index + 1]
    target = target_status or expected
    if target != expected:
        raise ValueError(
            f"illegal review status transition: {validated.review_status} -> {target}; "
            f"next allowed status is {expected}"
        )

    update: dict[str, Any] = {"review_status": target}
    if target == "independently_reviewed":
        if validated.annotator_a_result is None or validated.annotator_b_result is None:
            raise ValueError("two independent reviewers are required before promotion")
        if (
            validated.annotator_a_result.reviewer_id
            == validated.annotator_b_result.reviewer_id
        ):
            raise ValueError("two independent reviewers must have distinct identities")
        update["disagreement_fields"] = annotation_disagreement_fields(
            validated.annotator_a_result,
            validated.annotator_b_result,
        )
    elif target == "adjudicated":
        if validated.adjudicator_result is None or validated.adjudication_date is None:
            raise ValueError("adjudicator result and adjudication date are required")
        unresolved = sorted(
            set(validated.disagreement_fields)
            - set(validated.adjudicator_result.resolved_disagreement_fields)
        )
        if unresolved:
            raise ValueError("unresolved disagreement fields: " + ", ".join(unresolved))
        update.update(_adjudicated_gold(validated.adjudicator_result))
        update["label_origin"] = "human_annotation"
    elif target == "expert_labelled":
        if validated.adjudicator_result is None:
            raise ValueError("expert_labelled requires a completed adjudication")
        update["label_origin"] = "human_annotation"
    return RealPaperEvaluationCase.model_validate(
        {**validated.model_dump(), **update}
    )


def promote_dataset_case(
    dataset: RealPaperDataset,
    case_id: str,
) -> RealPaperDataset:
    found = False
    cases: list[RealPaperEvaluationCase] = []
    for case in dataset.cases:
        if case.case_id == case_id:
            cases.append(promote_case(case))
            found = True
        else:
            cases.append(case)
    if not found:
        raise ValueError(f"unknown case_id: {case_id}")
    tier: EvaluationTier = (
        "expert_labelled"
        if cases and all(case.review_status == "expert_labelled" for case in cases)
        else dataset.evaluation_tier
    )
    return RealPaperDataset.model_validate(
        {**dataset.model_dump(), "evaluation_tier": tier, "cases": cases}
    )


def coverage_report(dataset: RealPaperDataset) -> dict[str, Any]:
    statuses = Counter(case.review_status for case in dataset.cases)
    development_statuses = Counter(case.development_status for case in dataset.cases)
    answerability = Counter(case.answerability for case in dataset.cases)
    expert_count = statuses.get("expert_labelled", 0)
    validated_count = development_statuses.get(
        "validated", 0
    ) + development_statuses.get("maintainer_verified", 0)
    count = len(dataset.cases)
    return {
        "dataset_id": dataset.dataset_id,
        "evaluation_tier": dataset.evaluation_tier,
        "case_count": count,
        "paper_count": len({case.paper_id for case in dataset.cases}),
        "domain_count": len({case.domain for case in dataset.cases}),
        "answerable_count": answerability.get("answerable", 0),
        "refusal_count": answerability.get("refusal", 0),
        "refusal_ratio": round(answerability.get("refusal", 0) / count, 6)
        if count
        else 0.0,
        "completed_expert_count": expert_count,
        "validated_count": validated_count,
        "minimum_target": MINIMUM_DEVELOPMENT_CASES,
        "configured_target": dataset.target_case_count,
        "gap_to_minimum": max(0, MINIMUM_DEVELOPMENT_CASES - validated_count),
        "gap_to_configured_target": max(0, dataset.target_case_count - validated_count),
        "expert_minimum_target": MINIMUM_EXPERT_CASES,
        "expert_gap_to_minimum": max(0, MINIMUM_EXPERT_CASES - expert_count),
        "by_development_status": dict(sorted(development_statuses.items())),
        "by_review_status": dict(sorted(statuses.items())),
        "by_domain": dict(sorted(Counter(case.domain for case in dataset.cases).items())),
        "by_split": dict(sorted(Counter(case.split for case in dataset.cases).items())),
        "by_evidence_type": dict(
            sorted(Counter(case.evidence_type for case in dataset.cases).items())
        ),
        "by_evidence_level": dict(
            sorted(Counter(case.evidence_level for case in dataset.cases).items())
        ),
        "by_case_type": dict(
            sorted(Counter(tag for case in dataset.cases for tag in case.case_types).items())
        ),
    }


def unresolved_disagreements(dataset: RealPaperDataset) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in dataset.cases:
        if not case.disagreement_fields:
            continue
        resolved = (
            set(case.adjudicator_result.resolved_disagreement_fields)
            if case.adjudicator_result
            else set()
        )
        unresolved = sorted(set(case.disagreement_fields) - resolved)
        if unresolved:
            rows.append(
                {
                    "case_id": case.case_id,
                    "paper_id": case.paper_id,
                    "review_status": case.review_status,
                    "unresolved_fields": unresolved,
                }
            )
    return rows


def validate_dataset_for_evaluation(dataset: RealPaperDataset) -> list[str]:
    coverage = coverage_report(dataset)
    errors: list[str] = []
    if dataset.evaluation_tier == "development_benchmark":
        if coverage["validated_count"] == 0:
            errors.append("development benchmark has no validated cases")
        return errors
    if dataset.evaluation_tier != "expert_labelled":
        errors.append("dataset tier is neither development_benchmark nor expert_labelled")
        return errors
    if coverage["completed_expert_count"] < MINIMUM_EXPERT_CASES:
        errors.append(
            f"{coverage['completed_expert_count']}/{MINIMUM_EXPERT_CASES} cases are "
            "expert_labelled"
        )
    if coverage["paper_count"] < 15:
        errors.append(f"paper coverage is {coverage['paper_count']}/15 minimum")
    if coverage["domain_count"] < 5:
        errors.append(f"domain coverage is {coverage['domain_count']}/5 minimum")
    if unresolved_disagreements(dataset):
        errors.append("dataset contains unresolved disagreements")
    return errors


def expected_answer_matches_gold(case: RealPaperEvaluationCase) -> bool:
    expectation = case.answer_expectation or _legacy_answer_expectation(case)
    comparison = compare_answer_expectation(
        expectation,
        case.gold_claim,
        expected_reference=case.gold_claim,
        refused=not case.answerable,
        answer_kind="no_answer" if not case.answerable else "answer",
        has_supported_claim=False,
    )
    return comparison.correct_without_citation


def answer_matches_expected(
    case: RealPaperEvaluationCase,
    actual_answer: str,
) -> bool:
    """Compatibility boolean over the structured deterministic comparison."""

    expectation = case.answer_expectation or _legacy_answer_expectation(case)
    return compare_answer_expectation(
        expectation,
        actual_answer,
        expected_reference=case.gold_claim,
        refused=False,
        answer_kind="answer",
        has_supported_claim=False,
    ).correct_without_citation


def compare_answer_expectation(
    expectation: AnswerExpectation,
    actual_answer: str,
    *,
    expected_reference: str = "",
    refused: bool = False,
    answer_kind: str = "",
    has_supported_claim: bool = False,
) -> AnswerComparisonResult:
    """Score answer content without using citations or probabilistic judges."""

    comparator = expectation.comparator
    actual = actual_answer.strip()
    reasons: list[str] = []
    refusal_signal = refused or answer_kind == "no_answer"

    if comparator == "refusal":
        format_valid = refusal_signal
        conditions_correct = refusal_signal and not has_supported_claim
        if not refusal_signal:
            reasons.append("expected_refusal: prediction did not refuse")
        if has_supported_claim:
            reasons.append("invalid_refusal: refusal also contains a supported claim")
        return AnswerComparisonResult(
            comparator=comparator,
            answer_format_valid=format_valid,
            answer_value_correct=refusal_signal,
            answer_unit_correct=True,
            required_conditions_correct=conditions_correct,
            reasons=reasons,
        )

    format_valid = bool(actual) and not refusal_signal
    value_correct = False
    unit_correct = True
    slot_conditions_correct = True

    if not format_valid:
        reasons.append("answer_format_invalid: expected a non-refusal answer")
    elif comparator == "exact":
        candidates = [str(expectation.expected_value), *expectation.accepted_aliases]
        value_correct = any(actual == candidate.strip() for candidate in candidates)
    elif comparator in {"normalized_text", "categorical"}:
        candidates = [str(expectation.expected_value), *expectation.accepted_aliases]
        value_correct = _norm(actual) in {_norm(candidate) for candidate in candidates}
    elif comparator == "boolean":
        expected_boolean = _coerce_boolean(expectation.expected_value)
        actual_boolean = (
            expected_boolean
            if _norm(actual) in {_norm(alias) for alias in expectation.accepted_aliases}
            else _coerce_boolean(actual)
        )
        format_valid = actual_boolean is not None
        value_correct = format_valid and actual_boolean == expected_boolean
    elif comparator == "unordered_set":
        actual_values = _parse_unordered_values(actual)
        expected_values = {
            _norm(value) for value in (expectation.expected_value or []) if _norm(value)
        }
        format_valid = bool(actual_values)
        value_correct = actual_values == expected_values
    elif comparator in {"numeric", "numeric_with_unit"}:
        actual_numbers = _extract_numbers(actual)
        expected_numbers = _expected_numbers(expectation.expected_value)
        format_valid = bool(actual_numbers)
        value_correct = _numbers_match(
            expected_numbers,
            actual_numbers,
            absolute_tolerance=expectation.absolute_tolerance,
            relative_tolerance=expectation.relative_tolerance,
        )
        if comparator == "numeric_with_unit":
            expected_unit = _canonical_unit(expectation.expected_unit)
            actual_units = set(_answer_units(actual))
            unit_correct = bool(expected_unit) and expected_unit in actual_units
            format_valid = format_valid and bool(actual_units)
    elif comparator == "required_fact_slots":
        slots = expectation.expected_value if isinstance(expectation.expected_value, dict) else {}
        value_correct, slot_conditions_correct, slot_reasons = _match_fact_slots(
            slots,
            actual,
            expectation,
        )
        reasons.extend(slot_reasons)
        if expectation.expected_unit:
            expected_unit = _canonical_unit(expectation.expected_unit)
            unit_correct = expected_unit in set(_answer_units(actual))
        else:
            unit_correct = True
    else:  # pragma: no cover - Literal + Pydantic make this defensive only.
        format_valid = False
        reasons.append(f"unsupported_comparator: {comparator}")

    if not value_correct:
        reasons.append("answer_value_mismatch")
    if not unit_correct:
        reasons.append("answer_unit_mismatch")

    required_conditions_correct = _conditions_match(expectation, actual)
    if comparator == "required_fact_slots":
        required_conditions_correct = required_conditions_correct and slot_conditions_correct
    reference = expected_reference.strip()
    if reference and _has_negation(reference) != _has_negation(actual):
        required_conditions_correct = False
        reasons.append("negation_mismatch")
    if not required_conditions_correct and not any(
        reason.startswith(("missing_required_term", "forbidden_term", "negation_mismatch", "missing_fact_condition"))
        for reason in reasons
    ):
        reasons.append("required_conditions_mismatch")

    return AnswerComparisonResult(
        comparator=comparator,
        answer_format_valid=format_valid,
        answer_value_correct=value_correct,
        answer_unit_correct=unit_correct,
        required_conditions_correct=required_conditions_correct,
        reasons=list(dict.fromkeys(reasons)),
    )


def _answer_units(value: str) -> tuple[str, ...]:
    normalized = _norm(value)
    patterns = (
        (r"(?<!\w)(?:percentage points?|percent points?|百分点|个百分点|pp)(?!\w)", "percentage_point"),
        (r"%|(?<!\w)(?:percent|percentage)(?!\s+points?)(?!\w)|百分比", "percent"),
        (r"(?<!\w)bleu(?:\s+score)?(?!\w)", "bleu"),
        (r"(?<!\w)db(?!\w)|分贝", "db"),
        (r"(?<!\w)f1(?:\s+score)?(?!\w)", "f1"),
        (r"(?<!\w)rouge(?:-[l12])?(?!\w)", "rouge"),
        (r"(?<!\w)accuracy(?!\w)|准确率", "accuracy"),
        (r"(?<!\w)(?:seconds?|secs?)(?!\w)|秒", "second"),
        (r"(?<!\w)ms(?!\w)|毫秒", "millisecond"),
        (r"(?<!\w)gb(?!\w)", "gb"),
        (r"(?<!\w)mb(?!\w)", "mb"),
    )
    matches: list[tuple[int, str]] = []
    for pattern, canonical in patterns:
        matches.extend((match.start(), canonical) for match in re.finditer(pattern, normalized))
    return tuple(unit for _, unit in sorted(matches))


def _canonical_unit(value: str) -> str:
    units = _answer_units(value)
    if units:
        return units[0]
    return _norm(value).replace(" ", "_")


def _extract_numbers(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", value)]


def _expected_numbers(value: object) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return _extract_numbers(value)
    return []


def _numbers_match(
    expected: list[float],
    actual: list[float],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    if not expected or not actual:
        return False
    return all(
        any(
            abs(actual_value - expected_value)
            <= max(
                absolute_tolerance,
                relative_tolerance * abs(expected_value),
            )
            for actual_value in actual
        )
        for expected_value in expected
    )


def _legacy_answer_expectation(case: RealPaperEvaluationCase) -> AnswerExpectation:
    if not case.answerable or case.answer_comparator == "refusal":
        return AnswerExpectation(
            comparator="refusal",
            expected_value=None,
            expected_refusal=True,
        )
    source = case.expected_answer.strip() or case.gold_claim.strip()
    if case.answer_comparator == "exact_text":
        comparator: ExpectationComparator = "exact"
    elif case.answer_comparator == "numeric_unit":
        comparator = "numeric_with_unit"
    else:
        comparator = "normalized_text"
    source_units = _answer_units(source)
    expected_unit = (
        next(
            (
                unit
                for unit in (
                    "percentage_point",
                    "percent",
                    "bleu",
                    "db",
                    "f1",
                    "rouge",
                    "second",
                    "millisecond",
                    "gb",
                    "mb",
                    "accuracy",
                )
                if unit in source_units
            ),
            "",
        )
        if comparator == "numeric_with_unit"
        else ""
    )
    if comparator == "numeric_with_unit" and not expected_unit:
        # Old malformed numeric_unit records remain readable, but cannot be
        # promoted to a validated dataset by deterministic validation.
        comparator = "normalized_text"
    return AnswerExpectation(
        comparator=comparator,
        expected_value=source,
        expected_unit=expected_unit,
        expected_refusal=False,
    )


def _coerce_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = _norm(str(value))
    true_values = {"true", "yes", "是", "正确", "supported"}
    false_values = {"false", "no", "否", "错误", "unsupported"}
    if normalized in true_values:
        return True
    if normalized in false_values:
        return False
    return None


def _parse_unordered_values(value: str) -> set[str]:
    stripped = value.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return {_norm(item) for item in parsed if _norm(item)}
    return {
        _norm(item)
        for item in re.split(r"[,;、，；\n]+", stripped)
        if _norm(item)
    }


def _match_fact_slots(
    slots: dict[str, str | int | float | bool],
    actual: str,
    expectation: AnswerExpectation,
) -> tuple[bool, bool, list[str]]:
    value_correct = True
    conditions_correct = True
    reasons: list[str] = []
    condition_names = {"condition", "conditions", "qualifier", "constraint"}
    for name, expected in slots.items():
        if isinstance(expected, bool):
            matched = _coerce_boolean(actual) == expected
        elif isinstance(expected, (int, float)):
            matched = _numbers_match(
                [float(expected)],
                _extract_numbers(actual),
                absolute_tolerance=expectation.absolute_tolerance,
                relative_tolerance=expectation.relative_tolerance,
            )
        else:
            matched = _contains_term(actual, str(expected))
        if name.casefold() in condition_names:
            conditions_correct = conditions_correct and matched
            if not matched:
                reasons.append(f"missing_fact_condition: {name}")
        else:
            value_correct = value_correct and matched
            if not matched:
                reasons.append(f"missing_fact_slot: {name}")
    return value_correct, conditions_correct, reasons


def _conditions_match(expectation: AnswerExpectation, actual: str) -> bool:
    matched = True
    for term in expectation.required_terms:
        if not _contains_term(actual, term):
            matched = False
    for term in expectation.forbidden_terms:
        if _contains_term(actual, term):
            matched = False
    return matched


def _contains_term(value: str, term: str) -> bool:
    normalized_value = _norm(value)
    normalized_term = _norm(term)
    if not normalized_term:
        return False
    if re.fullmatch(r"[a-z0-9_+.-]+", normalized_term):
        return bool(
            re.search(
                rf"(?<![a-z0-9_]){re.escape(normalized_term)}(?![a-z0-9_])",
                normalized_value,
            )
        )
    return normalized_term in normalized_value


def _has_negation(value: str) -> bool:
    normalized = _norm(value)
    patterns = (
        r"(?<!\w)not(?!\w)",
        r"(?<!\w)no(?!\w)",
        r"(?<!\w)without(?!\w)",
        r"(?<!\w)fail(?:s|ed|ing)?(?!\w)",
        r"(?<!\w)cannot(?!\w)",
        r"(?<!\w)can't(?!\w)",
        r"不",
        r"未",
        r"没有",
        r"无法",
        r"并非",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _validate_answer_and_citations(
    *,
    answerability: Answerability,
    gold_claim: str,
    citations: list[AcceptableCitation],
    context: str,
) -> None:
    if answerability == "answerable":
        if not gold_claim.strip():
            raise ValueError(f"{context} answerable result requires a gold_claim")
        if not citations:
            raise ValueError(f"{context} answerable result requires reliable citations")
    else:
        if gold_claim.strip():
            raise ValueError(f"{context} refusal result must not invent a gold_claim")
        if citations:
            raise ValueError(f"{context} refusal result cannot contain direct support citations")


def _validate_near_duplicates(cases: list[RealPaperEvaluationCase]) -> None:
    normalized: list[tuple[str, str]] = [
        (case.case_id, _norm_question(case.question)) for case in cases
    ]
    for index, (left_id, left) in enumerate(normalized):
        for right_id, right in normalized[index + 1 :]:
            if left == right or SequenceMatcher(None, left, right).ratio() >= 0.96:
                raise ValueError(
                    "duplicate or near-duplicate question: "
                    f"{left_id}, {right_id}"
                )


def _adjudicated_gold(result: AdjudicatorResult) -> dict[str, Any]:
    return {
        "answerability": result.answerability,
        "gold_claim": result.gold_claim,
        "evidence_type": result.evidence_type,
        "evidence_level": result.evidence_level,
        "evidence_locator": result.evidence_locator,
        "acceptable_citations": result.acceptable_citations,
        "direct_support_found": result.answerability == "answerable",
    }


def _model_key(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)


def _citation_keys(citations: list[AcceptableCitation]) -> tuple[str, ...]:
    return tuple(sorted(_model_key(citation) for citation in citations))


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _norm_question(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))


def normalize_section(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", value.casefold()).strip()


def evidence_excerpt_checksum(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return (
        hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if normalized
        else ""
    )


def validate_development_sources(
    dataset: RealPaperDataset,
    resources_path: Path | None,
) -> tuple[RealPaperDataset, dict[str, Any]]:
    """Validate development labels against fixed local PDFs.

    This is deliberately offline and deterministic.  It can promote generated
    cases to validated, but it never changes expert-review fields.
    """

    if dataset.evaluation_tier != "development_benchmark":
        return dataset, {
            "status": "not_applicable",
            "validated_count": 0,
            "case_results": [],
        }
    if resources_path is None or not resources_path.is_file():
        return dataset, {
            "status": "blocked_missing_resources",
            "validated_count": len(evaluation_cases(dataset)),
            "case_results": [
                {
                    "case_id": case.case_id,
                    "status": case.development_status,
                    "errors": ["fixed local resource manifest is missing"],
                }
                for case in dataset.cases
                if case.development_status != "disabled"
            ],
        }

    manifest, resources = _load_validation_resource_manifest(resources_path)
    cache_root = str(manifest.get("cache_root") or "")
    updated_cases: list[RealPaperEvaluationCase] = []
    case_results: list[dict[str, Any]] = []
    for case in dataset.cases:
        if case.development_status == "disabled":
            updated_cases.append(case)
            case_results.append(
                {"case_id": case.case_id, "status": "disabled", "errors": []}
            )
            continue
        errors: list[str] = []
        resource = resources.get(case.paper_id)
        resource_file_present = False
        page_text = ""
        document_text = ""
        if resource is None:
            errors.append("fixed local PDF resource is missing")
        else:
            errors.extend(_resource_identity_errors(case, resource))
            pdf_path = _resolve_validation_resource_path(
                resource,
                resources_path,
                cache_root,
            )
            if not pdf_path.is_file():
                errors.append("fixed local PDF file is missing")
            else:
                resource_file_present = True
                payload = pdf_path.read_bytes()
                actual_hash = hashlib.sha256(payload).hexdigest()
                if actual_hash != case.source_hash:
                    errors.append("source_hash does not match fixed local PDF")
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(pdf_path, strict=False)
                    extracted_pages = [page.extract_text() or "" for page in reader.pages]
                    document_text = "\n".join(extracted_pages)
                    if len(reader.pages) != case.source_page_count:
                        errors.append("source_page_count does not match fixed local PDF")
                    elif case.page is None or case.page > len(reader.pages):
                        errors.append("evidence page does not exist in fixed local PDF")
                    else:
                        page_text = extracted_pages[case.page - 1]
                except Exception as error:
                    errors.append(f"fixed local PDF cannot be parsed: {type(error).__name__}")

        errors.extend(_development_label_errors(case, page_text, document_text))
        if errors:
            next_status: DevelopmentStatus = (
                "invalid" if resource_file_present else "generated"
            )
            payload = {
                **case.model_dump(mode="json"),
                "development_status": next_status,
                "validation_errors": list(dict.fromkeys(errors)),
            }
        else:
            excerpt_hash = evidence_excerpt_checksum(case.evidence_excerpt)
            anchors = [anchor.model_dump(mode="json") for anchor in case.acceptable_source_anchors]
            if case.answerable:
                matching = next(
                    (
                        anchor
                        for anchor in anchors
                        if anchor["paper_id"] == case.paper_id
                        and anchor["paper_version"] == case.paper_version
                        and anchor["source_hash"] == case.source_hash
                        and anchor["page"] == case.page
                    ),
                    None,
                )
                if matching is None:
                    matching = {
                        "paper_id": case.paper_id,
                        "paper_version": case.paper_version,
                        "source_hash": case.source_hash,
                        "page": case.page,
                        "normalized_section": case.normalized_section,
                        "chunk_hash": "",
                        "evidence_excerpt_hash": excerpt_hash,
                        "status": "verified",
                    }
                    anchors.append(matching)
                else:
                    matching["evidence_excerpt_hash"] = excerpt_hash
                    matching["status"] = "verified"
            payload = {
                **case.model_dump(mode="json"),
                "development_status": (
                    "maintainer_verified"
                    if case.development_status == "maintainer_verified"
                    else "validated"
                ),
                "evidence_excerpt_hash": excerpt_hash,
                "acceptable_source_anchors": anchors,
                "validation_errors": [],
            }
        updated = RealPaperEvaluationCase.model_validate(payload)
        updated_cases.append(updated)
        case_results.append(
            {
                "case_id": case.case_id,
                "status": updated.development_status,
                "errors": updated.validation_errors,
            }
        )

    updated_dataset = RealPaperDataset.model_validate(
        {
            **dataset.model_dump(mode="json"),
            "schema_version": REAL_PAPER_DATASET_SCHEMA_VERSION,
            "cases": [case.model_dump(mode="json") for case in updated_cases],
        }
    )
    validated_count = len(evaluation_cases(updated_dataset))
    resource_blocked = validated_count == 0 and any(
        any(
            marker in error
            for marker in (
                "fixed local PDF resource is missing",
                "fixed local PDF file is missing",
            )
        )
        for result in case_results
        for error in result["errors"]
    )
    return updated_dataset, {
        "status": (
            "complete"
            if validated_count
            else "blocked_missing_resources"
            if resource_blocked
            else "no_validated_cases"
        ),
        "validated_count": validated_count,
        "target_case_count": updated_dataset.target_case_count,
        "case_results": case_results,
    }


def _load_validation_resource_manifest(
    resources_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads(resources_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("real-paper resource manifest must be an object")
    if manifest.get("schema_version") != "real_paper_resources.v1":
        raise ValueError("unsupported real-paper resource manifest schema_version")
    rows = manifest.get("resources")
    if not isinstance(rows, list) or not rows:
        raise ValueError("real-paper resource manifest requires resources")
    resources: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each real-paper resource must be an object")
        paper_id = str(row.get("paper_id") or "").strip()
        if not paper_id:
            raise ValueError("real-paper resource requires paper_id")
        if paper_id in resources:
            raise ValueError(f"duplicate real-paper resource paper_id: {paper_id}")
        if not any(
            str(row.get(field) or "").strip()
            for field in ("doi", "arxiv_id", "openalex_id")
        ):
            raise ValueError(
                f"real-paper resource requires DOI, arXiv ID, or OpenAlex ID: {paper_id}"
            )
        resources[paper_id] = row
    return manifest, resources


def _resource_identity_errors(
    case: RealPaperEvaluationCase,
    resource: dict[str, Any],
) -> list[str]:
    expected = {
        "paper_id": case.paper_id,
        "title": case.title,
        "version": case.paper_version,
        "source_url": case.source_url,
        "sha256": case.source_hash,
        "page_count": case.source_page_count,
    }
    return [
        f"resource {field} does not match case"
        for field, value in expected.items()
        if str(resource.get(field) or "").strip() != str(value).strip()
    ]


def _resolve_validation_resource_path(
    resource: dict[str, Any],
    manifest_path: Path,
    cache_root: str,
) -> Path:
    local_path = str(resource.get("local_path") or "").strip()
    if local_path:
        candidate = Path(local_path).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
    identifier = str(resource.get("cache_identifier") or "").strip()
    root = Path(cache_root).expanduser()
    resolved_root = root.resolve() if root.is_absolute() else (manifest_path.parent / root).resolve()
    candidate = (resolved_root / identifier).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        return Path("/__invalid_resource_escape__")
    return candidate


def _development_label_errors(
    case: RealPaperEvaluationCase,
    page_text: str,
    document_text: str,
) -> list[str]:
    errors: list[str] = []
    if not expected_answer_matches_gold(case):
        errors.append("answer_expectation does not match gold_claim under its comparator")
    normalized_page = _norm(page_text)
    if case.answerable:
        if not case.evidence_excerpt.strip():
            errors.append("answerable case has no evidence_excerpt")
        elif _norm(case.evidence_excerpt) not in normalized_page:
            errors.append("evidence_excerpt is absent from the declared PDF page")
    else:
        if case.direct_support_found or case.acceptable_citations or case.acceptable_source_anchors:
            errors.append("refusal case contains annotated direct support evidence")
        if not case.refusal_probe_terms:
            errors.append("refusal case has no deterministic refusal_probe_terms")
        normalized_document = _norm(document_text)
        for term in case.refusal_probe_terms:
            if _norm(term) and _norm(term) in normalized_document:
                errors.append(f"refusal probe found direct support text: {term}")
    return errors


def write_real_paper_dataset(dataset: RealPaperDataset, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            dataset.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate and manage auditable ScholarFlow real-paper annotations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "coverage", "disagreements", "split-check"):
        command = subparsers.add_parser(name)
        command.add_argument("--cases", type=Path, required=True)
        if name == "validate":
            command.add_argument("--resources", type=Path)
            command.add_argument("--output", type=Path)
    promote = subparsers.add_parser("promote")
    promote.add_argument("--cases", type=Path, required=True)
    promote.add_argument("--case-id", required=True)
    promote.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        dataset = load_real_paper_dataset(args.cases, allow_unreviewed=True)
        if args.command == "validate":
            validated_dataset, source_validation = validate_development_sources(
                dataset,
                args.resources,
            )
            coverage = coverage_report(validated_dataset)
            readiness_errors = validate_dataset_for_evaluation(validated_dataset)
            if args.output:
                output = args.output.resolve()
                if Path("/private/tmp") not in output.parents:
                    raise ValueError("development validation output must be under /private/tmp")
                write_real_paper_dataset(validated_dataset, output)
            _print_json(
                {
                    "structurally_valid": True,
                    "evaluation_ready": not readiness_errors,
                    "coverage": coverage,
                    "source_validation": source_validation,
                    "evaluation_readiness_errors": readiness_errors,
                    "output": str(args.output.resolve()) if args.output else "",
                }
            )
        elif args.command == "coverage":
            _print_json(coverage_report(dataset))
        elif args.command == "disagreements":
            rows = unresolved_disagreements(dataset)
            _print_json({"count": len(rows), "cases": rows})
        elif args.command == "split-check":
            _print_json(
                {
                    "valid": True,
                    "paper_count": len({case.paper_id for case in dataset.cases}),
                    "by_split": coverage_report(dataset)["by_split"],
                }
            )
        elif args.command == "promote":
            output = args.output.resolve()
            if output == args.cases.resolve():
                raise ValueError("promote requires a separate --output audit artifact")
            promoted = promote_dataset_case(dataset, args.case_id)
            write_real_paper_dataset(promoted, output)
            promoted_case = next(
                case for case in promoted.cases if case.case_id == args.case_id
            )
            _print_json(
                {
                    "case_id": args.case_id,
                    "review_status": promoted_case.review_status,
                    "output": str(output),
                }
            )
    except (OSError, ValueError) as exc:
        print(f"real-paper dataset error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
