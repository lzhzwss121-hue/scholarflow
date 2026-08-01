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
    adjudication = "adjudicated" if tier == "expert_labelled" else "unreviewed"
    annotator = "expert-reviewer-1" if tier == "expert_labelled" else "repository-maintainer-unreviewed"
    return {
        "schema_version": "real_paper_eval.v1",
        "dataset_id": "real-paper-contract-fixture",
        "evaluation_tier": tier,
        "description": "Non-expert fixture used to validate evaluation code.",
        "cases": [
            {
                "case_id": "case-answerable",
                "project_id": "project-a",
                "domain": "multimodal-evaluation",
                "paper_id": "paper-a",
                "title": "A Real Paper Fixture",
                "source": "arxiv",
                "version": "v2",
                "question": "Does Method X reduce error on Dataset A?",
                "answerable": True,
                "gold_claim": "Method X does not reduce error on Dataset A by 10%.",
                "evidence_level": "full_text",
                "page": 4,
                "section": "Results",
                "locator": {"kind": "table", "value": "Table 2"},
                "acceptable_citations": [
                    {
                        "citation_id": "paper-a:results:p.4:table-2",
                        "paper_id": "paper-a",
                        "page": 4,
                        "section": "Results",
                        "locator": {"kind": "table", "value": "Table 2"},
                    }
                ],
                "contradiction_notes": [
                    "A positive reduction claim reverses the paper's negation.",
                    "10% is not 10 percentage points.",
                    "Dataset B is not Dataset A.",
                ],
                "contradiction_claims": [
                    "Method X reduces error on Dataset B by 10 percentage points."
                ],
                "annotator": annotator,
                "label_origin": "human_annotation",
                "adjudication_status": adjudication,
            },
            {
                "case_id": "case-refusal",
                "project_id": "project-a",
                "domain": "multimodal-evaluation",
                "paper_id": "paper-a",
                "title": "A Real Paper Fixture",
                "source": "arxiv",
                "version": "v2",
                "question": "What result is reported for Dataset Z?",
                "answerable": False,
                "gold_claim": "",
                "evidence_level": "full_text",
                "page": 4,
                "section": "Results",
                "locator": {"kind": "paragraph", "value": "No Dataset Z result is present"},
                "acceptable_citations": [],
                "contradiction_notes": ["The paper does not report Dataset Z."],
                "contradiction_claims": [],
                "annotator": annotator,
                "label_origin": "human_annotation",
                "adjudication_status": adjudication,
            },
        ],
    }


def correct_predictions() -> dict[str, object]:
    citation = {
        "citation_id": "paper-a:results:p.4:table-2",
        "project_id": "project-a",
        "paper_id": "paper-a",
        "page": 4,
        "section": "Results",
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

        report = evaluate_real_paper_predictions(dataset, predictions, recall_k=5)

        self.assertEqual(report["evaluation_tier"], "real_paper_unreviewed")
        self.assertEqual(report["review_status"], "unreviewed")
        self.assertTrue(report["human_review_required"])
        self.assertIn("不代表真实科研准确率", report["interpretation"])
        self.assertEqual(report["metrics"]["recall_at_5"], 1.0)
        self.assertEqual(report["metrics"]["mrr"], 1.0)
        self.assertEqual(report["metrics"]["citation_precision"], 1.0)
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
        )
        case = next(item for item in report["cases"] if item["case_id"] == "case-answerable")
        errors = " ".join(case["errors"])

        self.assertIn("invalid_citation", errors)
        self.assertIn("cross_project_citation", errors)
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
        self.assertEqual(report["metrics"]["page_locator_accuracy"], 0.0)
        self.assertEqual(report["metrics"]["table_locator_accuracy"], 0.0)

    def test_expert_dataset_requires_human_adjudication_and_model_gold_is_rejected(self) -> None:
        invalid_expert = dataset_fixture(tier="expert_labelled")
        invalid_expert["cases"][0]["adjudication_status"] = "unreviewed"
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(invalid_expert)

        model_gold = dataset_fixture()
        model_gold["cases"][0]["label_origin"] = "model_generated"
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(model_gold)

        unlocatable_gold = dataset_fixture()
        unlocatable_gold["cases"][0]["page"] = 99
        with self.assertRaises(ValidationError):
            RealPaperDataset.model_validate(unlocatable_gold)

    def test_json_and_markdown_reports_keep_evidence_tiers_explicit(self) -> None:
        report = evaluate_real_paper_predictions(
            RealPaperDataset.model_validate(dataset_fixture()),
            RealPaperPredictionSet.model_validate(correct_predictions()),
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


if __name__ == "__main__":
    unittest.main()
