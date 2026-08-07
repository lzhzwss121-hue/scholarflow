from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from scholarflow_api.real_paper_evaluation import (
    RealPaperDataset,
    RealPaperPredictionSet,
    evaluate_real_paper_predictions,
    render_real_paper_markdown,
    write_real_paper_report,
)


def dataset_fixture(*, tier: str = "real_paper_unreviewed") -> dict[str, object]:
    source_hash = "a" * 64
    chunk_hash = "c" * 64
    locator = {
        "kind": "table",
        "value": "Table 2",
        "page": 4,
        "section": "Results",
        "paragraph": "",
        "table": "Table 2",
        "figure": "",
        "equation": "",
        "supplementary": False,
    }
    citation = {
        "citation_id": "paper-a:results:p.4:table-2",
        "paper_id": "paper-a",
        "paper_version": "v2",
        "source_hash": source_hash,
        "page": 4,
        "section": "Results",
        "locator": locator,
    }
    cases = [
        {
            "case_id": "case-answerable",
            "project_id": "project-a",
            "domain": "multimodal-evaluation",
            "paper_id": "paper-a",
            "title": "A Real Paper Fixture",
            "paper_version": "v2",
            "source_url": "https://example.org/paper-a/v2",
            "source_hash": source_hash,
            "source_page_count": 8,
            "question": "Does Method X reduce error on Dataset A?",
            "answerability": "answerable",
            "gold_claim": "Method X does not reduce error on Dataset A by 10%.",
            "evidence_type": "table",
            "evidence_level": "full_text",
            "evidence_excerpt": "Method X does not reduce error on Dataset A by 10%.",
            "evidence_locator": locator,
            "page": 4,
            "normalized_section": "results",
            "evidence_excerpt_hash": "",
            "semantic_locator": locator,
            "acceptable_source_anchors": [
                {
                    "paper_id": "paper-a",
                    "paper_version": "v2",
                    "source_hash": source_hash,
                    "page": 4,
                    "normalized_section": "results",
                    "chunk_hash": chunk_hash,
                    "evidence_excerpt_hash": "",
                    "status": "verified",
                }
            ],
            "acceptable_citations": [citation],
            "direct_support_found": True,
            "contradiction_notes": [
                "A positive reduction claim reverses the paper's negation.",
                "10% is not 10 percentage points.",
                "Dataset B is not Dataset A.",
            ],
            "contradiction_claims": [
                "Method X reduces error on Dataset B by 10 percentage points."
            ],
            "version_notes": "Test-only fixed v2 source.",
            "annotator_a_result": None,
            "annotator_b_result": None,
            "disagreement_fields": [],
            "adjudicator_result": None,
            "adjudication_date": None,
            "review_status": "draft",
            "label_origin": "human_draft",
            "split": "test",
            "case_types": [
                "answerable",
                "table",
                "dataset_metric",
                "numeric_unit_condition",
            ],
        },
        {
            "case_id": "case-refusal",
            "project_id": "project-a",
            "domain": "multimodal-evaluation",
            "paper_id": "paper-a",
            "title": "A Real Paper Fixture",
            "paper_version": "v2",
            "source_url": "https://example.org/paper-a/v2",
            "source_hash": source_hash,
            "source_page_count": 8,
            "question": "What result is reported for Dataset Z?",
            "answerability": "refusal",
            "gold_claim": "",
            "evidence_type": "main_text",
            "evidence_level": "full_text",
            "evidence_excerpt": "",
            "evidence_locator": {
                **locator,
                "kind": "paragraph",
                "value": "No Dataset Z result is present",
                "table": "",
            },
            "page": 4,
            "normalized_section": "results",
            "evidence_excerpt_hash": "",
            "semantic_locator": {
                **locator,
                "kind": "paragraph",
                "value": "No Dataset Z result is present",
                "table": "",
            },
            "acceptable_source_anchors": [],
            "acceptable_citations": [],
            "direct_support_found": False,
            "contradiction_notes": ["The paper does not report Dataset Z."],
            "contradiction_claims": [],
            "version_notes": "Test-only fixed v2 source.",
            "annotator_a_result": None,
            "annotator_b_result": None,
            "disagreement_fields": [],
            "adjudicator_result": None,
            "adjudication_date": None,
            "review_status": "draft",
            "label_origin": "human_draft",
            "split": "test",
            "case_types": ["refusal", "no_reliable_hit"],
        },
    ]
    if tier == "expert_labelled":
        for case in cases:
            answerability = case["answerability"]
            review_payload = {
                "completed_at": "2026-08-03T10:00:00Z",
                "independently_completed": True,
                "answerability": answerability,
                "gold_claim": case["gold_claim"],
                "evidence_type": case["evidence_type"],
                "evidence_level": case["evidence_level"],
                "evidence_locator": case["evidence_locator"],
                "acceptable_citations": case["acceptable_citations"],
                "notes": ["Test-only reviewer record."],
            }
            case["annotator_a_result"] = {
                **review_payload,
                "reviewer_id": "expert-reviewer-a-test",
            }
            case["annotator_b_result"] = {
                **review_payload,
                "reviewer_id": "expert-reviewer-b-test",
            }
            case["adjudicator_result"] = {
                "adjudicator_id": "expert-adjudicator-test",
                "completed_at": "2026-08-03T12:00:00Z",
                "answerability": answerability,
                "gold_claim": case["gold_claim"],
                "evidence_type": case["evidence_type"],
                "evidence_level": case["evidence_level"],
                "evidence_locator": case["evidence_locator"],
                "acceptable_citations": case["acceptable_citations"],
                "resolved_disagreement_fields": [],
                "rationale": "Test-only agreement adjudication.",
            }
            case["adjudication_date"] = "2026-08-03"
            case["review_status"] = "expert_labelled"
            case["label_origin"] = "human_annotation"
    return {
        "schema_version": "real_paper_dataset.v2",
        "dataset_id": "real-paper-contract-fixture",
        "evaluation_tier": tier,
        "description": "Non-expert fixture used to validate evaluation code.",
        "target_case_count": 50,
        "cases": cases,
    }


def correct_predictions() -> dict[str, object]:
    citation = {
        "citation_id": "runtime-generated-id-that-differs-from-gold",
        "project_id": "project-a",
        "paper_id": "paper-a",
        "page": 4,
        "section": "Results",
        "machine_locator": {
            "paper_id": "paper-a",
            "paper_version": "v2",
            "source_hash": "a" * 64,
            "page": 4,
            "normalized_section": "results",
            "chunk_index": 3,
            "chunk_hash": "c" * 64,
            "evidence_excerpt_hash": "d" * 64,
        },
        "semantic_locator": {
            "kind": "table",
            "value": "Table 2",
            "page": 4,
            "section": "Results",
            "table": "Table 2",
        },
        "locator": {"kind": "table", "value": "Table 2"},
        "evidence_level": "full_text",
        "evidence_verified": True,
    }
    return {
        "schema_version": "real_paper_predictions.v1",
        "prediction_set_id": "contract-predictions",
        "system_version": "test-only",
        "prediction_source": "offline_test_fixture",
        "cases": [
            {
                "case_id": "case-answerable",
                "project_id": "project-a",
                "refused": False,
                "retrieved_citations": [citation],
                "used_citations": [citation],
                "claims": [
                    {
                        "statement": "Method X does not reduce error on Dataset A by 10%.",
                        "status": "supported",
                        "method": "exact_quote",
                        "citation_ids": [citation["citation_id"]],
                        "evidence_level": "full_text",
                    }
                ],
            },
            {
                "case_id": "case-refusal",
                "project_id": "project-a",
                "refused": True,
                "retrieved_citations": [],
                "used_citations": [],
                "claims": [],
            },
        ],
    }


class RealPaperEvaluationContractTest(unittest.TestCase):
    def test_unreviewed_real_paper_fixture_is_never_presented_as_expert_gold(self) -> None:
        dataset = RealPaperDataset.model_validate(dataset_fixture())
        predictions = RealPaperPredictionSet.model_validate(correct_predictions())

        with self.assertRaisesRegex(ValueError, "only expert_labelled"):
            evaluate_real_paper_predictions(dataset, predictions, recall_k=5)
        report = evaluate_real_paper_predictions(
            dataset,
            predictions,
            recall_k=5,
            allow_unreviewed=True,
        )

        self.assertEqual(report["evaluation_tier"], "real_paper_unreviewed")
        self.assertEqual(report["review_status"], "unreviewed")
        self.assertTrue(report["human_review_required"])
        self.assertIn("不代表真实科研准确率", report["interpretation"])
        self.assertEqual(report["metrics"]["recall_at_5"], 1.0)
        self.assertEqual(report["metrics"]["mrr"], 1.0)
        self.assertEqual(report["metrics"]["source_identity_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["semantic_locator_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)
        self.assertEqual(report["metrics"]["citation_recall"], 1.0)
        self.assertEqual(report["metrics"]["citation_locatability"], 1.0)
        self.assertEqual(report["metrics"]["answer_precision"], 1.0)
        self.assertEqual(report["metrics"]["refusal_precision"], 1.0)
        self.assertEqual(report["metrics"]["refusal_recall"], 1.0)
        self.assertEqual(report["metrics"]["contradiction_escape_rate"], 0.0)
        self.assertEqual(report["metrics"]["evidence_level_false_positive_rate"], 0.0)
        self.assertEqual(report["metrics"]["unsupported_claim_rate"], 0.0)
        self.assertEqual(report["metrics"]["page_locator_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["table_locator_accuracy"], 1.0)
        self.assertIsNone(report["metrics"]["figure_locator_accuracy"])
        self.assertIn("multimodal-evaluation", report["groups"]["by_domain"])
        self.assertIn("paper-a", report["groups"]["by_paper"])
        self.assertIn("full_text", report["groups"]["by_evidence_level"])

    def test_adversarial_predictions_expose_binding_locator_and_semantic_failures(self) -> None:
        payload = correct_predictions()
        adversarial = payload["cases"][0]
        adversarial["retrieved_citations"] = [
            {
                "citation_id": "invented:citation",
                "project_id": "other-project",
                "paper_id": "paper-a",
                "page": 99,
                "section": "Results",
                "machine_locator": {
                    "paper_id": "paper-a",
                    "paper_version": "v1",
                    "source_hash": "b" * 64,
                    "page": 99,
                    "normalized_section": "results",
                    "chunk_index": 9,
                    "chunk_hash": "e" * 64,
                    "evidence_excerpt_hash": "f" * 64,
                },
                "semantic_locator": {"kind": "paragraph", "value": "Table 2"},
                "locator": {"kind": "paragraph", "value": "Table 2"},
                "evidence_level": "full_text",
                "evidence_verified": True,
            }
        ]
        adversarial["used_citations"] = list(adversarial["retrieved_citations"])
        adversarial["claims"] = [
            {
                "statement": "Method X reduces error on Dataset B by 10 percentage points.",
                "status": "supported",
                "method": "numeric_lexical",
                "citation_ids": ["invented:citation"],
                "evidence_level": "full_text",
            }
        ]

        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_fixture()),
            RealPaperPredictionSet.model_validate(payload),
            recall_k=5,
            allow_unreviewed=True,
        )
        case = next(item for item in report["cases"] if item["case_id"] == "case-answerable")
        errors = " ".join(case["errors"])

        self.assertIn("cross_project_citation", errors)
        self.assertIn("wrong_source_hash", errors)
        self.assertIn("wrong_source_version", errors)
        self.assertIn("wrong_page", errors)
        self.assertIn("否定关系不一致", errors)
        self.assertIn("数字或单位不一致", errors)
        self.assertIn("数据集、指标、模型或比较对象不一致", errors)
        self.assertGreater(report["metrics"]["contradiction_escape_rate"], 0.0)
        self.assertGreater(report["metrics"]["unsupported_claim_rate"], 0.0)
        self.assertGreater(
            report["metrics"]["evidence_level_false_positive_rate"],
            0.0,
        )
        self.assertEqual(report["metrics"]["citation_precision"], 0.0)
        self.assertEqual(report["metrics"]["source_identity_accuracy"], 0.0)
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 0.0)
        self.assertEqual(report["metrics"]["page_locator_accuracy"], 0.0)
        self.assertEqual(report["metrics"]["table_locator_accuracy"], 0.0)

    def test_missing_semantic_locator_is_unverified_not_incorrect(self) -> None:
        payload = correct_predictions()
        citation = payload["cases"][0]["used_citations"][0]
        citation["semantic_locator"] = None
        citation["locator"] = None
        payload["cases"][0]["retrieved_citations"] = [dict(citation)]
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_fixture()),
            RealPaperPredictionSet.model_validate(payload),
            allow_unreviewed=True,
        )
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)
        self.assertIsNone(report["metrics"]["semantic_locator_accuracy"])
        self.assertIsNone(report["metrics"]["table_locator_accuracy"])

    def test_evidence_excerpt_hash_can_bind_without_chunk_hash(self) -> None:
        dataset_payload = dataset_fixture()
        anchor = dataset_payload["cases"][0]["acceptable_source_anchors"][0]
        anchor["chunk_hash"] = ""
        anchor["evidence_excerpt_hash"] = "d" * 64
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_payload),
            RealPaperPredictionSet.model_validate(correct_predictions()),
            allow_unreviewed=True,
        )
        self.assertEqual(report["metrics"]["machine_anchor_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)

    def test_expert_dataset_requires_human_adjudication_and_model_gold_is_rejected(self) -> None:
        invalid_expert = dataset_fixture(tier="expert_labelled")
        invalid_expert["cases"][0]["review_status"] = "draft"
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(invalid_expert)

        model_gold = dataset_fixture()
        model_gold["cases"][0]["label_origin"] = "model_generated"
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(model_gold)

        unlocatable_gold = dataset_fixture()
        unlocatable_gold["cases"][0]["evidence_locator"]["page"] = 99
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(unlocatable_gold)

    def test_json_and_markdown_reports_keep_evidence_tiers_explicit(self) -> None:
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_fixture()),
            RealPaperPredictionSet.model_validate(correct_predictions()),
            allow_unreviewed=True,
        )
        markdown = render_real_paper_markdown(report)
        self.assertIn("real_paper_unreviewed", markdown)
        self.assertIn("不代表真实科研准确率", markdown)
        self.assertNotIn("专家已确认", markdown)

        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            paths = write_real_paper_report(report, Path(tmpdir))
            machine = json.loads(paths["json"].read_text(encoding="utf-8"))
            human = paths["markdown"].read_text(encoding="utf-8")
        self.assertEqual(machine["dataset_id"], "real-paper-contract-fixture")
        self.assertIn("人工审核", human)

    def test_blocked_execution_is_not_credited_as_a_correct_refusal(self) -> None:
        payload = correct_predictions()
        refusal = payload["cases"][1]
        refusal.update(
            {
                "execution_status": "blocked",
                "error": "fixed PDF is missing",
            }
        )
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_fixture()),
            RealPaperPredictionSet.model_validate(payload),
            allow_unreviewed=True,
        )
        self.assertEqual(report["counts"]["blocked_predictions"], 1)
        self.assertEqual(report["metrics"]["refusal_recall"], 0.0)
        refusal_case = next(
            case for case in report["cases"] if case["case_id"] == "case-refusal"
        )
        self.assertEqual(refusal_case["execution_status"], "blocked")
        self.assertIn("prediction_blocked", " ".join(refusal_case["errors"]))


if __name__ == "__main__":
    unittest.main()
