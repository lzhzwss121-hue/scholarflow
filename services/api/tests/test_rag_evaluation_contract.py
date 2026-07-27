from __future__ import annotations

import unittest

from scholarflow_api.rag_evaluation import assess_rag_answer


def answer_fixture(
    *,
    evidence_level: str = "full_text",
    anchor_coverage: float | None = None,
) -> dict[str, object]:
    citation_id = "paper_eval:experiments:p.7:chunk-1"
    return {
        "question": "What evidence supports the reported improvement?",
        "status": "partial",
        "answer_kind": "extractive_evidence",
        "answer": "The paper reports an improvement.",
        "claims": [
            {
                "id": "rag-claim-1",
                "statement": "The paper reports an improvement.",
                "citation_ids": [citation_id],
                "confidence": "medium",
                "evidence_level": evidence_level,
                "verification": {
                    "status": "supported",
                    "method": "exact_quote",
                    "reasons": ["The statement is a direct quote."],
                    "citation_ids": [citation_id],
                    "provider": "",
                    "model": "",
                    "prompt_version": "",
                },
            }
        ],
        "citations": [
            {
                "citation_id": citation_id,
                "paper_id": "paper_eval",
                "evidence_level": evidence_level,
                "hybrid_score": 0.52,
                **(
                    {"anchor_coverage": anchor_coverage}
                    if anchor_coverage is not None
                    else {}
                ),
            }
        ],
        "citation_validation": {
            "available_citation_ids": [citation_id],
            "used_citation_ids": [citation_id],
            "rejected_citation_ids": [],
            "rejected_claim_count": 0,
        },
    }


class RagEvaluationContractTest(unittest.TestCase):
    def test_full_text_traceable_answer_scores_strong_but_requires_human_review(self) -> None:
        assessment = assess_rag_answer(
            answer_fixture(),
            evaluation_id="rag_eval_full_text",
            evaluated_at="2026-07-18T00:00:00+00:00",
        )

        self.assertEqual(assessment["quality_status"], "strong_evidence")
        self.assertGreaterEqual(assessment["score"], 80)
        self.assertEqual(assessment["metrics"]["claim_traceability"], 1.0)
        self.assertEqual(assessment["metrics"]["citation_integrity"], 1.0)
        self.assertEqual(assessment["metrics"]["full_text_coverage"], 1.0)
        self.assertTrue(assessment["human_review_required"])
        self.assertIn("不能替代", assessment["disclaimer"])
        self.assertTrue(any("不代表结论真实" in item for item in assessment["risk_flags"]))
        self.assertIn("不判断论文结论是否真实", assessment["disclaimer"])

    def test_abstract_evidence_cannot_receive_strong_evidence_status(self) -> None:
        assessment = assess_rag_answer(
            answer_fixture(evidence_level="abstract_only"),
            evaluation_id="rag_eval_abstract",
            evaluated_at="2026-07-18T00:00:00+00:00",
        )

        self.assertEqual(assessment["quality_status"], "review_required")
        self.assertEqual(assessment["metrics"]["full_text_coverage"], 0.0)
        self.assertTrue(
            any("摘要级证据" in item for item in assessment["risk_flags"])
        )
        full_text_check = next(
            item
            for item in assessment["checks"]
            if item["id"] == "full_text_coverage"
        )
        self.assertEqual(full_text_check["status"], "warn")
        self.assertIn("上传 PDF", full_text_check["remediation"])

    def test_safe_refusal_is_not_presented_as_a_numeric_quality_score(self) -> None:
        assessment = assess_rag_answer(
            {
                "question": "Unsupported question",
                "status": "no_reliable_hit",
                "answer_kind": "no_answer",
                "answer": "",
                "claims": [],
                "citations": [],
                "citation_validation": {
                    "available_citation_ids": [],
                    "used_citation_ids": [],
                    "rejected_citation_ids": [],
                    "rejected_claim_count": 0,
                },
            },
            evaluation_id="rag_eval_refusal",
            evaluated_at="2026-07-18T00:00:00+00:00",
        )

        self.assertEqual(assessment["quality_status"], "safe_refusal")
        self.assertIsNone(assessment["score"])
        self.assertFalse(assessment["human_review_required"])
        boundary = next(
            item
            for item in assessment["checks"]
            if item["id"] == "answer_boundary"
        )
        self.assertEqual(boundary["status"], "pass")

    def test_unknown_citation_and_rejected_claim_lower_the_score(self) -> None:
        answer = answer_fixture()
        answer["claims"][0]["citation_ids"] = ["invented:citation"]
        answer["citation_validation"] = {
            "available_citation_ids": ["paper_eval:experiments:p.7:chunk-1"],
            "used_citation_ids": ["invented:citation"],
            "rejected_citation_ids": ["invented:citation"],
            "rejected_claim_count": 1,
        }
        assessment = assess_rag_answer(
            answer,
            evaluation_id="rag_eval_invalid",
            evaluated_at="2026-07-18T00:00:00+00:00",
        )

        self.assertEqual(assessment["quality_status"], "review_required")
        self.assertLess(assessment["score"], 50)
        self.assertEqual(assessment["metrics"]["citation_integrity"], 0.0)
        citation_check = next(
            item
            for item in assessment["checks"]
            if item["id"] == "citation_integrity"
        )
        self.assertEqual(citation_check["status"], "fail")

    def test_low_query_anchor_coverage_cannot_be_scored_as_strong_evidence(self) -> None:
        assessment = assess_rag_answer(
            answer_fixture(anchor_coverage=0.1),
            evaluation_id="rag_eval_low_query_coverage",
            evaluated_at="2026-07-18T00:00:00+00:00",
        )

        self.assertEqual(assessment["quality_status"], "review_required")
        self.assertLess(assessment["score"], 60)
        self.assertEqual(assessment["metrics"]["mean_anchor_coverage"], 0.1)
        relevance_check = next(
            item
            for item in assessment["checks"]
            if item["id"] == "query_relevance"
        )
        self.assertEqual(relevance_check["status"], "fail")


if __name__ == "__main__":
    unittest.main()
