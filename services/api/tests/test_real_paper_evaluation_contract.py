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
from scholarflow_api.real_paper_dataset import evidence_excerpt_checksum


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
    if tier == "development_benchmark":
        answerable = cases[0]
        answerable.update(
            {
                "development_status": "validated",
                "expected_answer": answerable["gold_claim"],
                "answer_comparator": "normalized_text",
                "refusal_probe_terms": [],
                "validation_errors": [],
                "evidence_excerpt_hash": evidence_excerpt_checksum(
                    str(answerable["evidence_excerpt"])
                ),
            }
        )
        refusal = cases[1]
        refusal.update(
            {
                "development_status": "validated",
                "expected_answer": "",
                "answer_comparator": "refusal",
                "refusal_probe_terms": ["Dataset Z result"],
                "validation_errors": [],
            }
        )
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


def comparator_report(
    *,
    expectation: dict[str, object],
    gold_claim: str,
    predicted_claim: str,
    citation_is_correct: bool = True,
) -> dict[str, object]:
    dataset_payload = dataset_fixture(tier="development_benchmark")
    answerable = dataset_payload["cases"][0]
    answerable.update(
        {
            "gold_claim": gold_claim,
            "expected_answer": gold_claim,
            "answer_expectation": expectation,
            "evidence_excerpt": gold_claim,
            "evidence_excerpt_hash": evidence_excerpt_checksum(gold_claim),
            "contradiction_claims": [],
        }
    )
    dataset_payload["cases"] = [answerable]

    prediction_payload = correct_predictions()
    predicted = prediction_payload["cases"][0]
    predicted["claims"][0]["statement"] = predicted_claim
    if not citation_is_correct:
        for key in ("retrieved_citations", "used_citations"):
            predicted[key][0]["machine_locator"]["source_hash"] = "b" * 64
    prediction_payload["cases"] = [predicted]
    return evaluate_real_paper_predictions(
        RealPaperDataset.model_validate(dataset_payload),
        RealPaperPredictionSet.model_validate(prediction_payload),
    )


class RealPaperEvaluationContractTest(unittest.TestCase):
    def test_unreviewed_real_paper_fixture_is_never_presented_as_expert_gold(self) -> None:
        dataset = RealPaperDataset.model_validate(dataset_fixture())
        predictions = RealPaperPredictionSet.model_validate(correct_predictions())

        with self.assertRaisesRegex(ValueError, "development_benchmark or expert_labelled"):
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

    def test_validated_development_benchmark_runs_without_expert_review_fields(self) -> None:
        payload = dataset_fixture(tier="development_benchmark")
        for case in payload["cases"]:
            for field in (
                "annotator_a_result",
                "annotator_b_result",
                "disagreement_fields",
                "adjudicator_result",
                "adjudication_date",
                "review_status",
                "label_origin",
            ):
                case.pop(field)
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(payload),
            RealPaperPredictionSet.model_validate(correct_predictions()),
        )
        self.assertEqual(report["evaluation_tier"], "development_benchmark")
        self.assertEqual(report["review_status"], "development_validated")
        self.assertFalse(report["human_review_required"])
        self.assertEqual(report["case_count"], 2)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)
        self.assertIn("不代表真实科研准确率", report["interpretation"])

    def test_generated_development_case_is_excluded_from_metrics(self) -> None:
        payload = dataset_fixture(tier="development_benchmark")
        payload["cases"][0].update(
            {
                "development_status": "generated",
                "expected_answer": "",
                "evidence_excerpt_hash": "",
            }
        )
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(payload),
            RealPaperPredictionSet.model_validate(correct_predictions()),
        )
        self.assertEqual(report["case_count"], 1)
        self.assertEqual(report["excluded_case_count"], 1)

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

    def test_numeric_with_unit_accepts_rephrasing_but_enforces_tolerance(self) -> None:
        expectation = {
            "comparator": "numeric_with_unit",
            "expected_value": 28.4,
            "expected_unit": "BLEU",
            "absolute_tolerance": 0.05,
            "relative_tolerance": 0,
            "accepted_aliases": [],
            "required_terms": [],
            "forbidden_terms": [],
            "expected_refusal": False,
        }
        accepted = comparator_report(
            expectation=expectation,
            gold_claim="The system reports a BLEU score of 28.4.",
            predicted_claim="The reported result is 28.4 BLEU.",
        )
        accepted_case = accepted["cases"][0]
        self.assertTrue(accepted_case["answer_format_valid"])
        self.assertTrue(accepted_case["answer_value_correct"])
        self.assertTrue(accepted_case["answer_unit_correct"])
        self.assertTrue(accepted_case["required_conditions_correct"])
        self.assertTrue(accepted_case["citation_binding_correct"])
        self.assertTrue(accepted_case["final_answer_correct"])

        within_tolerance = comparator_report(
            expectation=expectation,
            gold_claim="The system reports a BLEU score of 28.4.",
            predicted_claim="The reported result is 28.44 BLEU.",
        )
        self.assertTrue(within_tolerance["cases"][0]["answer_value_correct"])
        self.assertTrue(within_tolerance["cases"][0]["final_answer_correct"])

        rejected = comparator_report(
            expectation=expectation,
            gold_claim="The system reports a BLEU score of 28.4.",
            predicted_claim="The reported result is 28.5 BLEU.",
        )
        rejected_case = rejected["cases"][0]
        self.assertTrue(rejected_case["answer_format_valid"])
        self.assertFalse(rejected_case["answer_value_correct"])
        self.assertFalse(rejected_case["final_answer_correct"])

    def test_numeric_comparators_reject_unit_sign_and_magnitude_errors(self) -> None:
        cases = (
            (
                {
                    "comparator": "numeric_with_unit",
                    "expected_value": 10,
                    "expected_unit": "%",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "The gain is 10%.",
                "The gain is 10 percentage points.",
                "answer_unit_correct",
            ),
            (
                {
                    "comparator": "numeric_with_unit",
                    "expected_value": -2.5,
                    "expected_unit": "dB",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "The change is -2.5 dB.",
                "The change is 2.5 dB.",
                "answer_value_correct",
            ),
            (
                {
                    "comparator": "numeric_with_unit",
                    "expected_value": 28.4,
                    "expected_unit": "BLEU",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "The score is 28.4 BLEU.",
                "The score is 28.4 dB.",
                "answer_unit_correct",
            ),
            (
                {
                    "comparator": "numeric",
                    "expected_value": 10,
                    "expected_unit": "",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "The value is 10.",
                "The value is 0.1.",
                "answer_value_correct",
            ),
        )
        for expectation, gold, actual, failing_field in cases:
            with self.subTest(actual=actual):
                report = comparator_report(
                    expectation=expectation,
                    gold_claim=gold,
                    predicted_claim=actual,
                )
                self.assertFalse(report["cases"][0][failing_field])
                self.assertFalse(report["cases"][0]["final_answer_correct"])

    def test_conditions_and_negation_are_deterministic_gates(self) -> None:
        missing_condition = comparator_report(
            expectation={
                "comparator": "numeric_with_unit",
                "expected_value": 76.2,
                "expected_unit": "%",
                "absolute_tolerance": 0,
                "relative_tolerance": 0,
                "accepted_aliases": [],
                "required_terms": ["zero-shot"],
                "forbidden_terms": [],
                "expected_refusal": False,
            },
            gold_claim="Zero-shot accuracy is 76.2%.",
            predicted_claim="Accuracy is 76.2%.",
        )
        self.assertFalse(
            missing_condition["cases"][0]["required_conditions_correct"]
        )

        negation_reversal = comparator_report(
            expectation={
                "comparator": "numeric_with_unit",
                "expected_value": 10,
                "expected_unit": "%",
                "absolute_tolerance": 0,
                "relative_tolerance": 0,
                "accepted_aliases": [],
                "required_terms": [],
                "forbidden_terms": [],
                "expected_refusal": False,
            },
            gold_claim="Method X does not reduce error by 10%.",
            predicted_claim="Method X reduces error by 10%.",
        )
        self.assertFalse(
            negation_reversal["cases"][0]["required_conditions_correct"]
        )
        self.assertFalse(negation_reversal["cases"][0]["final_answer_correct"])

    def test_categorical_alias_set_boolean_and_fact_slot_comparators(self) -> None:
        scenarios = (
            (
                {
                    "comparator": "categorical",
                    "expected_value": "ImageNet",
                    "expected_unit": "",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": ["ILSVRC 2012"],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "ImageNet",
                "ILSVRC 2012",
            ),
            (
                {
                    "comparator": "boolean",
                    "expected_value": True,
                    "expected_unit": "",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": ["yes"],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "true",
                "yes",
            ),
            (
                {
                    "comparator": "unordered_set",
                    "expected_value": ["accuracy", "F1"],
                    "expected_unit": "",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "accuracy, F1",
                "F1; accuracy",
            ),
            (
                {
                    "comparator": "required_fact_slots",
                    "expected_value": {
                        "dataset": "ImageNet",
                        "metric": "accuracy",
                        "value": 76.2,
                        "condition": "zero-shot",
                    },
                    "expected_unit": "%",
                    "absolute_tolerance": 0,
                    "relative_tolerance": 0,
                    "accepted_aliases": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "expected_refusal": False,
                },
                "ImageNet zero-shot accuracy is 76.2%.",
                "At 76.2%, zero-shot accuracy is reported on ImageNet.",
            ),
        )
        for expectation, gold, actual in scenarios:
            with self.subTest(comparator=expectation["comparator"]):
                report = comparator_report(
                    expectation=expectation,
                    gold_claim=gold,
                    predicted_claim=actual,
                )
                self.assertTrue(report["cases"][0]["answer_value_correct"])
                self.assertTrue(report["cases"][0]["final_answer_correct"])

    def test_refusal_requires_no_answer_and_no_supported_claim(self) -> None:
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(
                dataset_fixture(tier="development_benchmark")
            ),
            RealPaperPredictionSet.model_validate(correct_predictions()),
        )
        refusal = next(
            item for item in report["cases"] if item["case_id"] == "case-refusal"
        )
        self.assertTrue(refusal["answer_format_valid"])
        self.assertTrue(refusal["answer_value_correct"])
        self.assertTrue(refusal["required_conditions_correct"])
        self.assertTrue(refusal["final_answer_correct"])

        payload = correct_predictions()
        pseudo_refusal = payload["cases"][1]
        pseudo_refusal.update(
            {
                "refused": False,
                "answer_kind": "no_answer",
                "claims": [
                    {
                        "statement": "Dataset Z reports 90% accuracy.",
                        "status": "supported",
                        "method": "exact_quote",
                        "citation_ids": [],
                        "evidence_level": "full_text",
                    }
                ],
            }
        )
        rejected = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(
                dataset_fixture(tier="development_benchmark")
            ),
            RealPaperPredictionSet.model_validate(payload),
        )
        rejected_refusal = next(
            item for item in rejected["cases"] if item["case_id"] == "case-refusal"
        )
        self.assertFalse(rejected_refusal["required_conditions_correct"])
        self.assertFalse(rejected_refusal["final_answer_correct"])

    def test_answer_dimensions_do_not_bypass_citation_binding(self) -> None:
        report = comparator_report(
            expectation={
                "comparator": "normalized_text",
                "expected_value": "Method X reports 10% on Dataset A.",
                "expected_unit": "",
                "absolute_tolerance": 0,
                "relative_tolerance": 0,
                "accepted_aliases": [],
                "required_terms": [],
                "forbidden_terms": [],
                "expected_refusal": False,
            },
            gold_claim="Method X reports 10% on Dataset A.",
            predicted_claim="Method X reports 10% on Dataset A.",
            citation_is_correct=False,
        )
        case = report["cases"][0]
        self.assertTrue(case["answer_value_correct"])
        self.assertFalse(case["citation_binding_correct"])
        self.assertFalse(case["final_answer_correct"])

    def test_legacy_gold_claim_defaults_to_normalized_text(self) -> None:
        payload = dataset_fixture()
        answerable = payload["cases"][0]
        answerable.pop("expected_answer", None)
        answerable.pop("answer_comparator", None)
        case = RealPaperDataset.model_validate(payload).cases[0]
        self.assertEqual(case.answer_expectation.comparator, "normalized_text")
        self.assertEqual(case.answer_expectation.expected_value, case.gold_claim)

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
        self.assertIn("Legacy 数据只用于兼容性检查", human)

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
