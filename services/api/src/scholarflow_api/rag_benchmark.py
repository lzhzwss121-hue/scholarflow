from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholarflow_api.database import get_connection, init_db, utc_now
from scholarflow_api.rag_answer import verify_claim_support
from scholarflow_api.rag_index import replace_paper_chunks
from scholarflow_api.rag_retrieval import retrieve_project_chunks


BENCHMARK_VERSION = "evidence_hybrid_rag.v1"
PROJECT_ID = "rag-offline-eval"


@dataclass(frozen=True)
class EvidenceDocument:
    paper_id: str
    direction: str
    model: str
    dataset: str
    metric: str
    relation: str
    text: str
    adversarial_claim: str
    section: str
    page: int
    verified: bool = True


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    direction: str
    query: str
    expected_paper_ids: tuple[str, ...]
    should_refuse: bool
    adversarial_claim: str = ""


def evidence_documents() -> list[EvidenceDocument]:
    return [
        _document("halluguard", "multimodal_hallucination", "HalluGuard", "POPE",
                  "object hallucination rate", "reduces", "10% relative, from 30% to 27%",
                  "HalluGuard does not reduce object hallucination rate on POPE.", 3),
        _document("visionfence", "multimodal_hallucination", "VisionFence", "CHAIR",
                  "hallucination rate", "does not reduce", "remaining at 18%",
                  "VisionFence reduces hallucination rate on CHAIR.", 5),
        _document("groundtrace", "multimodal_hallucination", "GroundTrace", "ObjectScope",
                  "grounding accuracy", "is higher than Baseline A", "72% versus 64%",
                  "GroundTrace has lower grounding accuracy than Baseline A on ObjectScope.", 7),
        _document("captionshield", "multimodal_hallucination", "CaptionShield", "MMHal",
                  "faithfulness score", "may improve", "under high-resolution inputs",
                  "CaptionShield improves faithfulness score on MMHal without conditions.", 9),
        _document("evalmirror", "multimodal_hallucination", "EvalMirror", "HallusionBench",
                  "error frequency", "is correlated with", "attention entropy",
                  "EvalMirror attention entropy causes error frequency on HallusionBench.", 11),
        _document("sparselens", "mechanistic_interpretability", "SparseLens", "FeatureBench",
                  "feature localization accuracy", "improves", "by 8%",
                  "SparseLens degrades feature localization accuracy on FeatureBench.", 4),
        _document("circuitprobe", "mechanistic_interpretability", "CircuitProbe", "IOI",
                  "causal tracing accuracy", "does not improve", "remaining at 61%",
                  "CircuitProbe improves causal tracing accuracy on IOI.", 6),
        _document("tokenscope", "mechanistic_interpretability", "TokenScope", "BiasTrace",
                  "circuit precision", "is higher than Baseline B", "81% versus 73%",
                  "TokenScope has lower circuit precision than Baseline B on BiasTrace.", 8),
        _document("causalpatch", "mechanistic_interpretability", "CausalPatch", "GreaterThan",
                  "intervention fidelity", "may improve", "when the target layer is known",
                  "CausalPatch improves intervention fidelity on GreaterThan unconditionally.", 10),
        _document("featureatlas", "mechanistic_interpretability", "FeatureAtlas", "NeuronMap",
                  "concept purity", "is correlated with", "decoder sparsity",
                  "FeatureAtlas decoder sparsity causes concept purity on NeuronMap.", 12),
        _document("tempscale", "uncertainty_calibration", "TempScale", "Dataset U",
                  "expected calibration error", "decreases", "from 12% to 8%",
                  "TempScale increases expected calibration error on Dataset U.", 3),
        _document("robustcal", "uncertainty_calibration", "RobustCal", "Dataset V",
                  "expected calibration error", "does not decrease", "remaining at 9%",
                  "RobustCal decreases expected calibration error on Dataset V.", 5),
        _document("bayesbin", "uncertainty_calibration", "BayesBin", "Dataset W",
                  "Brier score", "is lower than Baseline C", "0.14 versus 0.19",
                  "BayesBin has a higher Brier score than Baseline C on Dataset W.", 7),
        _document("selectivegate", "uncertainty_calibration", "SelectiveGate", "Dataset X",
                  "selective accuracy", "may improve", "when coverage is below 80%",
                  "SelectiveGate improves selective accuracy on Dataset X at every coverage.", 9),
        _document("confidencemap", "uncertainty_calibration", "ConfidenceMap", "Dataset Y",
                  "calibration gap", "is correlated with", "domain shift magnitude",
                  "ConfidenceMap domain shift magnitude causes the calibration gap on Dataset Y.", 11),
    ]


def _document(
    slug: str,
    direction: str,
    model: str,
    dataset: str,
    metric: str,
    relation: str,
    result: str,
    adversarial_claim: str,
    page: int,
) -> EvidenceDocument:
    sentence = f"{model} {relation} {metric} on {dataset}, {result}."
    text = (
        f"[PDF page {page}]\n[Section: results]\n"
        f"{sentence} The comparison uses the same evaluation split and reports the unit explicitly. "
        f"原文结果：{model} 在 {dataset} 上关于 {metric} 的结论为 {relation}，结果是 {result}。"
    )
    return EvidenceDocument(
        paper_id=f"paper-{slug}",
        direction=direction,
        model=model,
        dataset=dataset,
        metric=metric,
        relation=relation,
        text=text,
        adversarial_claim=adversarial_claim,
        section="results",
        page=page,
    )


def benchmark_cases() -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for document in evidence_documents():
        queries = [
            f"What does {document.model} report for {document.metric} on {document.dataset}?",
            f"{document.model} {document.dataset} {document.metric} original result",
            f"{document.model} 在 {document.dataset} 上的 {document.metric} 结果是什么？",
            f"请给出 {document.model} 的可定位原文证据和页码。",
            f"Does {document.model} increase or decrease {document.metric} on {document.dataset}?",
            f"{document.model} comparison direction numeric result {document.dataset}",
            f"{document.model} 在 {document.dataset} 上是否存在限制、否定或条件性结论？",
        ]
        for index, query in enumerate(queries, start=1):
            cases.append(
                BenchmarkCase(
                    id=f"{document.paper_id}-q{index}",
                    direction=document.direction,
                    query=query,
                    expected_paper_ids=(document.paper_id,),
                    should_refuse=False,
                    adversarial_claim=document.adversarial_claim,
                )
            )

    refusal_topics = [
        "marine isotope chronology in Bronze Age shipwrecks",
        "volcanic ash composition in Antarctic ice cores",
        "medieval manuscript ink spectroscopy",
        "quantum error correction for trapped ion hardware",
        "soil microbiome response to nitrogen fertilizer",
        "economic inflation forecasting with household surveys",
        "protein folding energy landscapes in membrane receptors",
        "urban traffic signal optimization during festivals",
        "stellar metallicity in dwarf galaxies",
        "legal precedent retrieval for maritime insurance",
        "coral reef bleaching under ocean acidification",
        "battery cathode degradation under fast charging",
        "speech therapy outcomes for childhood apraxia",
        "cryptographic side channels in smart cards",
        "agricultural pest migration under monsoon variation",
        "ancient ceramic provenance using neutron activation",
        "fluid dynamics of turbine blade cavitation",
        "forest carbon flux measured by eddy covariance",
        "music cognition during polyrhythmic perception",
        "supply chain inventory control under port closures",
        "gene regulation in zebrafish embryogenesis",
        "earthquake early warning from seismic arrays",
        "railway timetable optimization with passenger demand",
        "photon transport in layered biological tissue",
        "language change in historical dialect atlases",
        "enzyme kinetics under noncompetitive inhibition",
        "satellite orbit determination from radar observations",
        "wastewater phosphorus recovery by crystallization",
        "museum visitor navigation using indoor positioning",
        "wind farm wake interaction over complex terrain",
    ]
    directions = (
        "multimodal_hallucination",
        "mechanistic_interpretability",
        "uncertainty_calibration",
    )
    for index, query in enumerate(refusal_topics, start=1):
        cases.append(
            BenchmarkCase(
                id=f"refuse-{index:02d}",
                direction=directions[(index - 1) % len(directions)],
                query=query,
                expected_paper_ids=(),
                should_refuse=True,
            )
        )
    return cases


def seed_benchmark(connection) -> None:
    now = utc_now()
    connection.execute(
        """
        INSERT INTO projects (
            id, title, description, keyword, field, language, workflow, stage,
            active_session_id, created_at, updated_at
        )
        VALUES (?, ?, '', ?, 'offline-evaluation', 'zh-CN', 'rag', 'evaluation',
                NULL, ?, ?)
        """,
        (PROJECT_ID, "Evidence-aware Hybrid RAG offline benchmark", "offline benchmark", now, now),
    )
    for index, document in enumerate(evidence_documents()):
        connection.execute(
            """
            INSERT INTO papers (
                id, project_id, title, authors, abstract, year, type, venue,
                source, url, pdf_url, relation, priority, code, relevance_score,
                relevance_quality, matched_terms_json, review_required, created_at
            )
            VALUES (?, ?, ?, 'Offline Eval', ?, '2026', 'Evaluation', 'Offline',
                    'fixture', ?, ?, ?, 'High', '', 1.0, 'strong', '[]', 0, ?)
            """,
            (
                document.paper_id,
                PROJECT_ID,
                f"{document.model}: {document.metric} on {document.dataset}",
                document.text,
                f"https://arxiv.org/abs/2607.{index + 1:05d}",
                f"https://arxiv.org/pdf/2607.{index + 1:05d}.pdf",
                document.direction,
                now,
            ),
        )
        replace_paper_chunks(
            connection,
            project_id=PROJECT_ID,
            paper_id=document.paper_id,
            text=document.text,
            source="pdf.full_text",
            source_origin="offline_verified_pdf",
            evidence_level="full_text",
            now=now,
            evidence_verified=True,
            parser_version="offline_pdf_fixture.v1",
        )

    deceptive = EvidenceDocument(
        paper_id="paper-user-paste",
        direction="multimodal_hallucination",
        model="HalluGuard",
        dataset="POPE",
        metric="object hallucination rate",
        relation="reduces",
        text=(
            "[PDF page 99]\n[Section: results]\n"
            "HalluGuard reduces object hallucination rate on POPE by 10%. "
            "This text was pasted by a user and was not parsed from a PDF."
        ),
        adversarial_claim="",
        section="results",
        page=99,
        verified=False,
    )
    connection.execute(
        """
        INSERT INTO papers (
            id, project_id, title, authors, abstract, year, type, venue,
            source, url, pdf_url, relation, priority, code, relevance_score,
            relevance_quality, matched_terms_json, review_required, created_at
        )
        VALUES (?, ?, ?, 'Offline Eval', ?, '2026', 'Evaluation', 'Offline',
                'fixture', '', '', ?, 'Low', '', 1.0, 'strong', '[]', 0, ?)
        """,
        (
            deceptive.paper_id,
            PROJECT_ID,
            "Unverified pasted HalluGuard note",
            deceptive.text,
            deceptive.direction,
            now,
        ),
    )
    replace_paper_chunks(
        connection,
        project_id=PROJECT_ID,
        paper_id=deceptive.paper_id,
        text=deceptive.text,
        source="user_provided.full_text",
        source_origin="user_provided",
        evidence_level="full_text",
        now=now,
        evidence_verified=False,
        parser_version="user_text_fixture.v1",
    )


def run_benchmark(connection) -> dict[str, Any]:
    cases = benchmark_cases()
    answerable = [case for case in cases if not case.should_refuse]
    refusal = [case for case in cases if case.should_refuse]
    recall_hits = 0
    reciprocal_rank = 0.0
    citation_correct = 0
    citation_total = 0
    locatable = 0
    contradiction_escapes = 0
    contradiction_checks = 0
    false_full_text = 0
    full_text_hits = 0
    predicted_refusals = 0
    true_refusals = 0
    diversity_values: list[float] = []
    case_results: list[dict[str, Any]] = []

    for case in cases:
        retrieval = retrieve_project_chunks(
            connection,
            project_id=PROJECT_ID,
            query=case.query,
            top_k=5,
            min_score=0.18,
            max_chunks_per_paper=2,
            refresh_embeddings=False,
        )
        hits = list(retrieval.get("hits") or [])
        retrieved_ids = [str(hit.get("paper_id") or "") for hit in hits]
        predicted_refusal = retrieval.get("status") == "no_reliable_hit" or not hits
        if predicted_refusal:
            predicted_refusals += 1
            if case.should_refuse:
                true_refusals += 1

        rank = next(
            (
                index
                for index, paper_id in enumerate(retrieved_ids, start=1)
                if paper_id in case.expected_paper_ids
            ),
            0,
        )
        if not case.should_refuse:
            if rank and rank <= 5:
                recall_hits += 1
                reciprocal_rank += 1.0 / rank
            for hit in hits:
                citation_total += 1
                if str(hit.get("paper_id") or "") in case.expected_paper_ids:
                    citation_correct += 1
                if hit.get("page_start") is not None and str(hit.get("section") or "") not in {"", "unknown"}:
                    locatable += 1
                if hit.get("evidence_level") == "full_text":
                    full_text_hits += 1
                    if str(hit.get("paper_id") or "") == "paper-user-paste":
                        false_full_text += 1
            if hits:
                diversity_values.append(len(set(retrieved_ids)) / len(hits))

            gold_hit = next(
                (hit for hit in hits if str(hit.get("paper_id") or "") in case.expected_paper_ids),
                None,
            )
            if gold_hit and case.adversarial_claim:
                contradiction_checks += 1
                verification = verify_claim_support(
                    case.adversarial_claim,
                    [gold_hit],
                    citation_ids=[str(gold_hit["citation_id"])],
                    project_id=PROJECT_ID,
                )
                if verification["status"] == "supported":
                    contradiction_escapes += 1

        case_results.append(
            {
                "id": case.id,
                "direction": case.direction,
                "should_refuse": case.should_refuse,
                "status": retrieval.get("status"),
                "retrieved_paper_ids": retrieved_ids,
                "gold_rank": rank,
            }
        )

    metrics = {
        "recall_at_5": _ratio(recall_hits, len(answerable)),
        "mrr": _ratio(reciprocal_rank, len(answerable)),
        "citation_precision": _ratio(citation_correct, citation_total),
        "citation_locatability": _ratio(locatable, citation_total),
        "contradiction_escape_rate": _ratio(contradiction_escapes, contradiction_checks),
        "refusal_precision": _ratio(true_refusals, predicted_refusals),
        "refusal_recall": _ratio(true_refusals, len(refusal)),
        "full_text_false_positive_rate": _ratio(false_full_text, full_text_hits),
        "per_paper_diversity": (
            round(sum(diversity_values) / len(diversity_values), 6)
            if diversity_values
            else 0.0
        ),
    }
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "case_count": len(cases),
        "answerable_count": len(answerable),
        "refusal_count": len(refusal),
        "direction_count": len({case.direction for case in cases}),
        "metrics": metrics,
        "counts": {
            "recall_hits": recall_hits,
            "citation_correct": citation_correct,
            "citation_total": citation_total,
            "contradiction_escapes": contradiction_escapes,
            "contradiction_checks": contradiction_checks,
            "predicted_refusals": predicted_refusals,
            "true_refusals": true_refusals,
            "refusal_false_positives": predicted_refusals - true_refusals,
            "false_full_text_hits": false_full_text,
            "full_text_hits": full_text_hits,
        },
        "cases": case_results,
    }


def _ratio(numerator: float, denominator: int) -> float:
    return round(float(numerator) / denominator, 6) if denominator else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ScholarFlow's fixed offline RAG benchmark.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    db_path = Path(os.environ.get("SCHOLARFLOW_DB_PATH", ""))
    if not db_path.is_absolute() or not str(db_path).startswith("/private/tmp/"):
        raise SystemExit("SCHOLARFLOW_DB_PATH must be an unused path under /private/tmp.")
    if db_path.exists():
        raise SystemExit(f"Refusing to overwrite existing benchmark database: {db_path}")
    init_db()
    with get_connection() as connection:
        seed_benchmark(connection)
        result = run_benchmark(connection)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = args.output.resolve()
        if not str(output).startswith("/private/tmp/"):
            raise SystemExit("--output must be under /private/tmp.")
        output.write_text(rendered + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "benchmark_version": result["benchmark_version"],
                "case_count": result["case_count"],
                "answerable_count": result["answerable_count"],
                "refusal_count": result["refusal_count"],
                "direction_count": result["direction_count"],
                "metrics": result["metrics"],
                "counts": result["counts"],
                "output": str(args.output.resolve()) if args.output else "",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
