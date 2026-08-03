from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from pydantic import ValidationError

from scholarflow_api.real_paper_dataset import (
    RealPaperDataset,
    coverage_report,
    main,
    promote_case,
    validate_dataset_for_evaluation,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def citation(*, paper_id: str = "paper-a", page: int = 4) -> dict[str, object]:
    return {
        "citation_id": f"{paper_id}:v2:p.{page}:table-2",
        "paper_id": paper_id,
        "paper_version": "v2",
        "source_hash": HASH_A,
        "page": page,
        "section": "Results",
        "locator": {
            "kind": "table",
            "value": "Table 2, Method X row",
            "page": page,
            "section": "Results",
            "paragraph": "",
            "table": "Table 2",
            "figure": "",
            "equation": "",
            "supplementary": False,
        },
    }


def review(reviewer_id: str, *, claim: str = "Method X reports 10% on Dataset A.") -> dict[str, object]:
    return {
        "reviewer_id": reviewer_id,
        "completed_at": "2026-08-03T10:00:00Z",
        "independently_completed": True,
        "answerability": "answerable",
        "gold_claim": claim,
        "evidence_type": "table",
        "evidence_level": "full_text",
        "evidence_locator": citation()["locator"],
        "acceptable_citations": [citation()],
        "notes": ["Test-only human review record."],
    }


def adjudication(*, claim: str = "Method X reports 10% on Dataset A.") -> dict[str, object]:
    return {
        "adjudicator_id": "adjudicator-test",
        "completed_at": "2026-08-03T12:00:00Z",
        "answerability": "answerable",
        "gold_claim": claim,
        "evidence_type": "table",
        "evidence_level": "full_text",
        "evidence_locator": citation()["locator"],
        "acceptable_citations": [citation()],
        "resolved_disagreement_fields": [],
        "rationale": "Both independent test reviews agree with the source locator.",
    }


def case_payload(*, case_id: str = "case-a", paper_id: str = "paper-a", split: str = "train") -> dict[str, object]:
    item = {
        "case_id": case_id,
        "project_id": "project-a",
        "paper_id": paper_id,
        "title": "A Real Paper Test Fixture",
        "paper_version": "v2",
        "source_url": "https://example.org/paper-a/v2",
        "source_hash": HASH_A,
        "source_page_count": 8,
        "domain": "multimodal-evaluation",
        "question": "What does Method X report on Dataset A?",
        "answerability": "answerable",
        "gold_claim": "Method X reports 10% on Dataset A.",
        "evidence_type": "table",
        "evidence_level": "full_text",
        "evidence_excerpt": "Method X | Dataset A | 10%",
        "evidence_locator": citation(paper_id=paper_id)["locator"],
        "acceptable_citations": [citation(paper_id=paper_id)],
        "direct_support_found": True,
        "contradiction_notes": ["10% is not 10 percentage points."],
        "contradiction_claims": [],
        "version_notes": "Test fixture fixed to v2.",
        "annotator_a_result": None,
        "annotator_b_result": None,
        "disagreement_fields": [],
        "adjudicator_result": None,
        "adjudication_date": None,
        "review_status": "draft",
        "label_origin": "human_draft",
        "split": split,
        "case_types": ["answerable", "table", "dataset_metric", "numeric_unit_condition"],
    }
    if paper_id != "paper-a":
        item["source_hash"] = HASH_B
        item["source_url"] = f"https://example.org/{paper_id}/v2"
        item["evidence_locator"] = citation(paper_id=paper_id)["locator"]
        item["acceptable_citations"] = [citation(paper_id=paper_id)]
        item["acceptable_citations"][0]["source_hash"] = HASH_B
    return item


def dataset_payload(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "real_paper_dataset.v2",
        "dataset_id": "dataset-test",
        "evaluation_tier": "real_paper_unreviewed",
        "description": "Test-only dataset contract fixture.",
        "target_case_count": 50,
        "cases": cases,
    }


class RealPaperDatasetContractTest(unittest.TestCase):
    def test_repository_schema_and_datasets_expose_the_audit_fields(self) -> None:
        schema = json.loads(
            Path("evals/real_papers/cases.schema.json").read_text(encoding="utf-8")
        )
        required = set(schema["$defs"]["case"]["required"])
        for field in (
            "paper_version",
            "source_hash",
            "evidence_locator",
            "annotator_a_result",
            "annotator_b_result",
            "disagreement_fields",
            "adjudicator_result",
            "adjudication_date",
            "review_status",
            "split",
        ):
            self.assertIn(field, required)
        unreviewed = RealPaperDataset.model_validate_json(
            Path("evals/real_papers/cases.unreviewed.json").read_text(encoding="utf-8")
        )
        expert = RealPaperDataset.model_validate_json(
            Path("evals/real_papers/cases.expert.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(unreviewed.cases), 4)
        self.assertTrue(all(case.review_status == "draft" for case in unreviewed.cases))
        self.assertEqual(len(expert.cases), 0)

    def test_coverage_cli_reports_real_zero_of_fifty(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(
                [
                    "coverage",
                    "--cases",
                    "evals/real_papers/cases.expert.json",
                ]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(report["completed_expert_count"], 0)
        self.assertEqual(report["gap_to_minimum"], 50)

    def test_illegal_state_jump_is_rejected(self) -> None:
        case = RealPaperDataset.model_validate(dataset_payload([case_payload()])).cases[0]
        with self.assertRaisesRegex(ValueError, "illegal review status transition"):
            promote_case(case, target_status="expert_labelled")

    def test_single_reviewer_cannot_promote(self) -> None:
        payload = case_payload()
        payload["annotator_a_result"] = review("reviewer-a-test")
        case = RealPaperDataset.model_validate(dataset_payload([payload])).cases[0]
        with self.assertRaisesRegex(ValueError, "two independent reviewers"):
            promote_case(case)

    def test_unresolved_disagreement_cannot_promote(self) -> None:
        payload = case_payload()
        payload["annotator_a_result"] = review("reviewer-a-test")
        payload["annotator_b_result"] = review(
            "reviewer-b-test", claim="Method X reports 11% on Dataset A."
        )
        case = promote_case(
            RealPaperDataset.model_validate(dataset_payload([payload])).cases[0]
        )
        self.assertEqual(case.review_status, "independently_reviewed")
        self.assertIn("gold_claim", case.disagreement_fields)
        candidate = case.__class__.model_validate(
            {
                **case.model_dump(),
                "adjudicator_result": adjudication(),
                "adjudication_date": "2026-08-03",
            }
        )
        with self.assertRaisesRegex(ValueError, "unresolved disagreement"):
            promote_case(candidate)

    def test_two_reviewers_and_adjudicator_promote_one_state_at_a_time(self) -> None:
        payload = case_payload()
        payload["annotator_a_result"] = review("reviewer-a-test")
        payload["annotator_b_result"] = review("reviewer-b-test")
        draft = RealPaperDataset.model_validate(dataset_payload([payload])).cases[0]
        independently_reviewed = promote_case(draft)
        self.assertEqual(independently_reviewed.review_status, "independently_reviewed")
        candidate = independently_reviewed.__class__.model_validate(
            {
                **independently_reviewed.model_dump(),
                "adjudicator_result": adjudication(),
                "adjudication_date": "2026-08-03",
            }
        )
        adjudicated = promote_case(candidate)
        self.assertEqual(adjudicated.review_status, "adjudicated")
        expert = promote_case(adjudicated)
        self.assertEqual(expert.review_status, "expert_labelled")
        self.assertEqual(expert.label_origin, "human_annotation")

    def test_same_paper_cannot_cross_splits(self) -> None:
        payload = dataset_payload(
            [case_payload(case_id="case-a", split="train"), case_payload(case_id="case-b", split="test")]
        )
        with self.assertRaisesRegex(ValidationError, "paper_id cannot appear in multiple splits"):
            RealPaperDataset.model_validate(payload)

    def test_version_and_hash_are_required_and_citation_version_must_match(self) -> None:
        missing = case_payload()
        missing["source_hash"] = ""
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(dataset_payload([missing]))

        wrong_version = case_payload()
        wrong_version["acceptable_citations"][0]["paper_version"] = "v1"
        with self.assertRaisesRegex(ValidationError, "wrong paper version"):
            RealPaperDataset.model_validate(dataset_payload([wrong_version]))

    def test_locator_out_of_range_is_rejected(self) -> None:
        payload = case_payload()
        payload["acceptable_citations"][0]["page"] = 9
        payload["acceptable_citations"][0]["locator"]["page"] = 9
        with self.assertRaisesRegex(ValidationError, "page exceeds source_page_count"):
            RealPaperDataset.model_validate(dataset_payload([payload]))

    def test_duplicate_and_near_duplicate_questions_are_rejected(self) -> None:
        second = case_payload(case_id="case-b")
        second["question"] = "What does Method X report on Dataset A ?"
        with self.assertRaisesRegex(ValidationError, "duplicate or near-duplicate question"):
            RealPaperDataset.model_validate(dataset_payload([case_payload(), second]))

    def test_coverage_statistics_are_exact_and_show_gap(self) -> None:
        second = case_payload(case_id="case-b", paper_id="paper-b", split="test")
        second.update(
            {
                "question": "Does this paper contain a direct result for Dataset Z?",
                "answerability": "refusal",
                "gold_claim": "",
                "evidence_type": "abstract",
                "evidence_level": "abstract_only",
                "evidence_excerpt": "",
                "acceptable_citations": [],
                "direct_support_found": False,
                "case_types": ["refusal", "abstract_insufficient", "no_reliable_hit"],
            }
        )
        dataset = RealPaperDataset.model_validate(dataset_payload([case_payload(), second]))
        report = coverage_report(dataset)
        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["paper_count"], 2)
        self.assertEqual(report["answerable_count"], 1)
        self.assertEqual(report["refusal_count"], 1)
        self.assertEqual(report["refusal_ratio"], 0.5)
        self.assertEqual(report["completed_expert_count"], 0)
        self.assertEqual(report["minimum_target"], 50)
        self.assertEqual(report["gap_to_minimum"], 50)

    def test_expert_evaluation_rejects_incomplete_or_small_dataset(self) -> None:
        dataset = RealPaperDataset.model_validate(dataset_payload([case_payload()]))
        errors = validate_dataset_for_evaluation(dataset)
        self.assertIn("dataset tier is not expert_labelled", errors)
        self.assertIn("0/50 cases are expert_labelled", errors)

    def test_refusal_with_direct_support_is_rejected(self) -> None:
        payload = case_payload()
        payload.update(
            {
                "answerability": "refusal",
                "gold_claim": "",
                "acceptable_citations": [],
                "direct_support_found": True,
                "case_types": ["refusal"],
            }
        )
        with self.assertRaisesRegex(ValidationError, "refusal cases cannot contain direct support"):
            RealPaperDataset.model_validate(dataset_payload([payload]))


if __name__ == "__main__":
    unittest.main()
