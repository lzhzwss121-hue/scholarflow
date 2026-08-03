from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REAL_PAPER_DATASET_SCHEMA_VERSION = "real_paper_dataset.v2"
MINIMUM_EXPERT_CASES = 50
MAXIMUM_TARGET_CASES = 100

EvaluationTier = Literal["real_paper_unreviewed", "expert_labelled"]
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
    answerability: Answerability
    gold_claim: str = Field(max_length=5000)
    evidence_type: EvidenceType
    evidence_level: EvidenceLevel
    evidence_excerpt: str = Field(default="", max_length=500)
    evidence_locator: EvidenceLocator
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
    review_status: ReviewStatus
    label_origin: Literal[
        "human_draft",
        "human_annotation",
        "imported_bibliographic_fixture",
    ]
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
    def page(self) -> int:
        return self.evidence_locator.page or 1

    @property
    def section(self) -> str:
        return self.evidence_locator.section

    @property
    def locator(self) -> EvidenceLocator:
        return self.evidence_locator

    @property
    def adjudication_status(self) -> str:
        if self.review_status in {"adjudicated", "expert_labelled"}:
            return "adjudicated"
        if self.review_status == "independently_reviewed":
            return "pending"
        return "unreviewed"

    @model_validator(mode="after")
    def validate_audit_contract(self) -> "RealPaperEvaluationCase":
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
    schema_version: Literal["real_paper_dataset.v2"]
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
    if not allow_unreviewed and dataset.evaluation_tier != "expert_labelled":
        raise ValueError(
            "default real-paper evaluation accepts only expert_labelled datasets; "
            "pass allow_unreviewed=True only for annotation/contract tooling"
        )
    return dataset


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
        else "real_paper_unreviewed"
    )
    return RealPaperDataset.model_validate(
        {**dataset.model_dump(), "evaluation_tier": tier, "cases": cases}
    )


def coverage_report(dataset: RealPaperDataset) -> dict[str, Any]:
    statuses = Counter(case.review_status for case in dataset.cases)
    answerability = Counter(case.answerability for case in dataset.cases)
    expert_count = statuses.get("expert_labelled", 0)
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
        "minimum_target": MINIMUM_EXPERT_CASES,
        "configured_target": dataset.target_case_count,
        "gap_to_minimum": max(0, MINIMUM_EXPERT_CASES - expert_count),
        "gap_to_configured_target": max(0, dataset.target_case_count - expert_count),
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
    if dataset.evaluation_tier != "expert_labelled":
        errors.append("dataset tier is not expert_labelled")
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


def _write_dataset(dataset: RealPaperDataset, output: Path) -> None:
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
    promote = subparsers.add_parser("promote")
    promote.add_argument("--cases", type=Path, required=True)
    promote.add_argument("--case-id", required=True)
    promote.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        dataset = load_real_paper_dataset(args.cases, allow_unreviewed=True)
        if args.command == "validate":
            coverage = coverage_report(dataset)
            readiness_errors = validate_dataset_for_evaluation(dataset)
            _print_json(
                {
                    "structurally_valid": True,
                    "evaluation_ready": not readiness_errors,
                    "coverage": coverage,
                    "evaluation_readiness_errors": readiness_errors,
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
            _write_dataset(promoted, output)
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
