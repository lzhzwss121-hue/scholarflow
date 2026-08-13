from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scholarflow_api.database import get_connection, init_db, utc_now
from scholarflow_api.full_text import parse_pdf_bytes
from scholarflow_api.rag_index import index_paper_full_text
from scholarflow_api.real_paper_evaluation import (
    EvidenceLocator,
    PredictedCitation,
    PredictedClaim,
    PredictionRuntimeMetadata,
    PredictionSourceIdentity,
    RealPaperCasePrediction,
    RealPaperPredictionSet,
)
from scholarflow_api.real_paper_dataset import (
    MachineLocator,
    evidence_excerpt_checksum,
    normalize_section,
)
from scholarflow_api.schemas import RagAnswerRequest


RUNNER_VERSION = "real_paper_prediction_runner.v2"
RAG_SERVICE_NAME = "rag_service.create_project_rag_answer"

# These labels may be loaded later by the evaluator, but they are deliberately
# absent from RuntimeEvaluationCase. Keeping an explicit deny-list makes the
# prompt/retrieval boundary auditable when the gold schema evolves.
FORBIDDEN_GOLD_FIELDS = frozenset(
    {
        "gold_claim",
        "gold_answer",
        "expected_answer",
        "answer_expectation",
        "acceptable_citations",
        "acceptable_source_anchors",
        "expected_refusal",
        "answerability",
        "evidence_type",
        "evidence_level",
        "evidence_excerpt",
        "evidence_locator",
        "semantic_locator",
        "normalized_section",
        "evidence_excerpt_hash",
        "page",
        "direct_support_found",
        "contradiction_annotations",
        "contradiction_notes",
        "contradiction_claims",
        "version_notes",
        "evaluator_notes",
        "annotator_a_result",
        "annotator_b_result",
        "disagreement_fields",
        "adjudicator_result",
        "adjudication_date",
        "review_status",
        "label_origin",
        "development_status",
        "answer_comparator",
        "refusal_probe_terms",
        "validation_errors",
    }
)
RUNTIME_CASE_FIELDS = (
    "case_id",
    "project_id",
    "paper_id",
    "title",
    "source_url",
    "paper_version",
    "source_hash",
    "source_page_count",
    "question",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeEvaluationCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    paper_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    source_url: str = Field(min_length=1, max_length=2000)
    paper_version: str = Field(min_length=1, max_length=200)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_page_count: int = Field(ge=1)
    question: str = Field(min_length=1, max_length=3000)

    @property
    def source(self) -> str:
        return self.source_url

    @property
    def version(self) -> str:
        return self.paper_version


class RuntimeEvaluationDataset(StrictModel):
    schema_version: Literal["real_paper_dataset.v2", "real_paper_dataset.v3"]
    dataset_id: str = Field(min_length=1, max_length=300)
    evaluation_tier: Literal[
        "development_benchmark",
        "expert_labelled",
        "real_paper_unreviewed",
    ]
    cases: list[RuntimeEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "RuntimeEvaluationDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        return self


class RealPaperResource(StrictModel):
    paper_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=1000)
    doi: str = Field(default="", max_length=300)
    arxiv_id: str = Field(default="", max_length=200)
    openalex_id: str = Field(default="", max_length=300)
    version: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    local_path: str = Field(default="", max_length=4000)
    cache_identifier: str = Field(default="", max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    page_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_fixed_resource(self) -> "RealPaperResource":
        if not (self.local_path.strip() or self.cache_identifier.strip()):
            raise ValueError("resource requires local_path or cache_identifier")
        if not any((self.doi.strip(), self.arxiv_id.strip(), self.openalex_id.strip())):
            raise ValueError("resource requires DOI, arXiv ID, or OpenAlex ID")
        return self


class RealPaperResourceManifest(StrictModel):
    schema_version: Literal["real_paper_resources.v1"]
    manifest_id: str = Field(min_length=1, max_length=300)
    cache_root: str = Field(default="", max_length=4000)
    resources: list[RealPaperResource] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_paper_resources(self) -> "RealPaperResourceManifest":
        paper_ids = [resource.paper_id for resource in self.resources]
        if len(paper_ids) != len(set(paper_ids)):
            raise ValueError("resource paper_id values must be unique")
        return self


class CaseBlockedError(RuntimeError):
    pass


def load_runtime_cases(path: Path) -> RuntimeEvaluationDataset:
    """Load only fields allowed to cross the evaluation/runtime boundary.

    The raw case file contains gold labels by design. This projection happens
    before Pydantic runtime validation, so no gold field is retained on the
    object later passed to ingestion, retrieval, or answer services.
    """

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(raw_cases, list):
        raise ValueError("real-paper cases must contain a cases array")
    projected_cases: list[dict[str, Any]] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("each real-paper case must be an object")
        if raw.get("evaluation_tier") == "development_benchmark" and raw_case.get(
            "development_status", "generated"
        ) not in {"validated", "maintainer_verified"}:
            continue
        projected_cases.append({field: raw_case.get(field) for field in RUNTIME_CASE_FIELDS})
    if raw.get("evaluation_tier") == "development_benchmark" and not projected_cases:
        raise ValueError(
            "development benchmark has no validated or maintainer_verified cases"
        )
    projected = {
        "schema_version": raw.get("schema_version"),
        "dataset_id": raw.get("dataset_id"),
        "evaluation_tier": raw.get("evaluation_tier"),
        "cases": projected_cases,
    }
    return RuntimeEvaluationDataset.model_validate(projected)


def load_resource_manifest(path: Path) -> RealPaperResourceManifest:
    return RealPaperResourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def real_paper_resource_json_schema() -> dict[str, Any]:
    return RealPaperResourceManifest.model_json_schema()


def run_real_paper_predictions(
    *,
    cases_path: Path,
    resources_path: Path,
    output_path: Path,
    work_dir: Path | None = None,
    top_k: int = 5,
    min_score: float = 0.18,
) -> RealPaperPredictionSet:
    output = _require_private_tmp_path(output_path, label="prediction output")
    run_root = _require_private_tmp_path(
        work_dir or output.parent / f"{output.stem}-work",
        label="prediction work directory",
    )
    runtime_dataset = load_runtime_cases(cases_path)
    manifest = load_resource_manifest(resources_path)
    resources = {resource.paper_id: resource for resource in manifest.resources}
    run_root.mkdir(parents=True, exist_ok=True)

    predictions: list[RealPaperCasePrediction] = []
    for case in runtime_dataset.cases:
        isolation_id = _isolation_id(runtime_dataset.dataset_id, case.case_id)
        database_path = run_root / f"{isolation_id}.sqlite3"
        resource = resources.get(case.paper_id)
        source_identity = _declared_source_identity(resource) if resource else None
        runtime_metadata = PredictionRuntimeMetadata(
            runner_version=RUNNER_VERSION,
            rag_service=RAG_SERVICE_NAME,
            database_isolation_id=isolation_id,
            ingestion_status="not_started",
            external_data_transfer=False,
        )
        try:
            if resource is None:
                raise CaseBlockedError(
                    f"No fixed offline resource exists for paper_id {case.paper_id}; "
                    "schema fixtures and network fallback are forbidden."
                )
            prediction = _run_case(
                case=case,
                resource=resource,
                manifest_path=resources_path,
                manifest=manifest,
                database_path=database_path,
                isolation_id=isolation_id,
                top_k=top_k,
                min_score=min_score,
            )
        except CaseBlockedError as error:
            prediction = _failed_prediction(
                case=case,
                execution_status="blocked",
                error=str(error),
                source_identity=source_identity,
                runtime_metadata=runtime_metadata.model_copy(
                    update={"ingestion_status": "blocked"}
                ),
            )
        except Exception as error:  # A single malformed case must not erase the batch.
            prediction = _failed_prediction(
                case=case,
                execution_status="error",
                error=f"{type(error).__name__}: {error}",
                source_identity=source_identity,
                runtime_metadata=runtime_metadata.model_copy(
                    update={"ingestion_status": "error"}
                ),
            )
        predictions.append(prediction)

    fingerprint_payload = {
        "runner_version": RUNNER_VERSION,
        "dataset": runtime_dataset.model_dump(mode="json"),
        "resources": [
            _declared_source_identity(resources.get(case.paper_id)).model_dump(mode="json")
            if resources.get(case.paper_id)
            else {"paper_id": case.paper_id, "missing": True}
            for case in runtime_dataset.cases
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    prediction_set = RealPaperPredictionSet(
        schema_version="real_paper_predictions.v1",
        prediction_set_id=f"offline-system-{fingerprint}",
        system_version=RUNNER_VERSION,
        prediction_source="offline_system_run",
        cases=predictions,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            prediction_set.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return prediction_set


def _run_case(
    *,
    case: RuntimeEvaluationCase,
    resource: RealPaperResource,
    manifest_path: Path,
    manifest: RealPaperResourceManifest,
    database_path: Path,
    isolation_id: str,
    top_k: int,
    min_score: float,
) -> RealPaperCasePrediction:
    _validate_case_resource_identity(case, resource)
    pdf_path = _resolve_resource_path(resource, manifest_path, manifest.cache_root)
    if not pdf_path.is_file():
        raise CaseBlockedError("Fixed local PDF resource is missing; offline fallback is forbidden.")
    payload = pdf_path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != resource.sha256.lower():
        raise CaseBlockedError(
            "Fixed PDF SHA-256 does not match the manifest; version substitution is forbidden."
        )
    actual_page_count = _pdf_page_count(payload)
    if actual_page_count != resource.page_count:
        raise CaseBlockedError(
            "Fixed PDF page_count does not match the manifest; resource integrity failed."
        )
    extracted = parse_pdf_bytes(
        payload,
        pdf_url=resource.source_url,
        source="user_uploaded_pdf",
    )
    qualification = extracted.evidence_qualification()
    if qualification.level != "full_text" or not qualification.verified:
        detail = extracted.error or qualification.reason
        raise CaseBlockedError(
            "Local PDF did not qualify as verified full_text: " + detail
        )
    if database_path.exists():
        raise CaseBlockedError("Isolated case database already exists; refusing stale state reuse.")

    with _offline_rag_environment(database_path):
        init_db()
        now = utc_now()
        with get_connection() as connection:
            _insert_runtime_project_and_paper(connection, case, resource, now)
            chunks = index_paper_full_text(
                connection,
                project_id=case.project_id,
                paper_id=case.paper_id,
                text=extracted.text,
                source_origin="user_uploaded_pdf",
                now=now,
                evidence_verified=True,
                parser_version="pypdf.v1",
            )
            if not chunks or not all(
                chunk.get("evidence_level") == "full_text"
                and bool(chunk.get("evidence_verified"))
                and chunk.get("page_start") is not None
                and str(chunk.get("section") or "") not in {"", "unknown"}
                for chunk in chunks
            ):
                raise CaseBlockedError(
                    "PDF ingestion produced no fully verified and locatable chunks."
                )

        # This public workflow service invokes answer_project_rag, persists its
        # artifact/evaluation, and applies the same deterministic refusal gates
        # used by the API. The runner never synthesizes a final answer itself.
        from scholarflow_api.services.rag_service import create_project_rag_answer

        response = create_project_rag_answer(
            case.project_id,
            RagAnswerRequest(
                query=case.question,
                language=_answer_language(case.question),
                top_k=max(1, min(top_k, 20)),
                paper_ids=[case.paper_id],
                evidence_levels=["full_text"],
                min_score=max(0.0, min(min_score, 1.0)),
                max_chunks_per_paper=max(1, min(top_k, 10)),
                refresh_embeddings=True,
            ),
        ).model_dump(mode="json")

    source_identity = PredictionSourceIdentity(
        paper_id=resource.paper_id,
        doi=resource.doi,
        arxiv_id=resource.arxiv_id,
        openalex_id=resource.openalex_id,
        version=resource.version,
        source_url=resource.source_url,
        sha256=actual_hash,
        page_count=actual_page_count,
        resource_identifier=resource.cache_identifier or f"sha256:{actual_hash}",
    )
    return _normalize_rag_response(
        case=case,
        response=response,
        source_identity=source_identity,
        isolation_id=isolation_id,
    )


def _normalize_rag_response(
    *,
    case: RuntimeEvaluationCase,
    response: dict[str, Any],
    source_identity: PredictionSourceIdentity,
    isolation_id: str,
) -> RealPaperCasePrediction:
    retrieval = response.get("retrieval") or {}
    retrieved = [
        _normalize_citation(item, source_identity=source_identity)
        for item in retrieval.get("hits") or []
        if isinstance(item, dict)
    ]
    answer_citations = [
        _normalize_citation(item, source_identity=source_identity)
        for item in response.get("citations") or []
        if isinstance(item, dict)
    ]
    used_ids = set(
        str(item)
        for item in (response.get("citation_validation") or {}).get(
            "used_citation_ids", []
        )
    )
    used = [citation for citation in answer_citations if citation.citation_id in used_ids]
    refused = (
        response.get("status") == "no_reliable_hit"
        or response.get("answer_kind") == "no_answer"
    )
    claims = [] if refused else [
        _normalize_claim(item)
        for item in response.get("claims") or []
        if isinstance(item, dict)
    ]
    execution_status: Literal["complete", "partial"] = (
        "complete" if response.get("status") == "complete" else "partial"
    )
    runtime = PredictionRuntimeMetadata(
        runner_version=RUNNER_VERSION,
        rag_service=RAG_SERVICE_NAME,
        database_isolation_id=isolation_id,
        ingestion_status="verified_full_text",
        retrieval_status=str(retrieval.get("status") or ""),
        answer_status=str(response.get("status") or ""),
        embedding_provider=str(retrieval.get("provider") or ""),
        embedding_model=str(retrieval.get("embedding_model") or ""),
        generation_provider=str(response.get("generation_provider") or ""),
        generation_model=str(response.get("generation_model") or ""),
        parser_version="pypdf.v1",
        external_data_transfer=bool(response.get("external_data_transfer")),
    )
    if runtime.external_data_transfer:
        raise RuntimeError("offline prediction attempted an external data transfer")
    return RealPaperCasePrediction(
        case_id=case.case_id,
        project_id=case.project_id,
        refused=refused,
        answer=str(response.get("answer") or ""),
        execution_status=execution_status,
        error="",
        retrieved_citations=retrieved,
        used_citations=used,
        claims=claims,
        source_identity=source_identity,
        runtime_metadata=runtime,
    )


def _normalize_citation(
    raw: dict[str, Any],
    *,
    source_identity: PredictionSourceIdentity,
) -> PredictedCitation:
    page = raw.get("page_start")
    chunk_index = int(raw.get("chunk_index") or 0)
    chunk_hash = str(raw.get("chunk_hash") or "")
    section = str(raw.get("section") or "")
    raw_semantic = raw.get("semantic_locator")
    semantic_locator = (
        EvidenceLocator.model_validate(raw_semantic)
        if isinstance(raw_semantic, dict)
        else None
    )
    machine_locator = MachineLocator(
        paper_id=str(raw.get("paper_id") or ""),
        paper_version=source_identity.version,
        source_hash=source_identity.sha256,
        page=int(page) if page is not None else None,
        normalized_section=normalize_section(section),
        chunk_index=chunk_index,
        chunk_hash=chunk_hash,
        evidence_excerpt_hash=evidence_excerpt_checksum(str(raw.get("text") or "")),
    )
    return PredictedCitation(
        citation_id=str(raw.get("citation_id") or ""),
        project_id=str(raw.get("project_id") or ""),
        paper_id=str(raw.get("paper_id") or ""),
        page=int(page) if page is not None else None,
        section=section,
        machine_locator=machine_locator,
        semantic_locator=semantic_locator,
        locator=semantic_locator,
        evidence_level=str(raw.get("evidence_level") or "metadata_only"),
        evidence_verified=bool(raw.get("evidence_verified")),
    )


def _normalize_claim(raw: dict[str, Any]) -> PredictedClaim:
    verification = raw.get("verification") or {}
    return PredictedClaim(
        statement=str(raw.get("statement") or ""),
        status=str(verification.get("status") or "not_checked"),
        method=str(verification.get("method") or "rule_based"),
        citation_ids=[str(item) for item in raw.get("citation_ids") or []],
        evidence_level=str(raw.get("evidence_level") or "metadata_only"),
    )


def _failed_prediction(
    *,
    case: RuntimeEvaluationCase,
    execution_status: Literal["blocked", "error"],
    error: str,
    source_identity: PredictionSourceIdentity | None,
    runtime_metadata: PredictionRuntimeMetadata,
) -> RealPaperCasePrediction:
    return RealPaperCasePrediction(
        case_id=case.case_id,
        project_id=case.project_id,
        refused=True,
        answer="",
        execution_status=execution_status,
        error=error,
        retrieved_citations=[],
        used_citations=[],
        claims=[],
        source_identity=source_identity,
        runtime_metadata=runtime_metadata,
    )


def _validate_case_resource_identity(
    case: RuntimeEvaluationCase,
    resource: RealPaperResource,
) -> None:
    mismatches = []
    if resource.paper_id != case.paper_id:
        mismatches.append("paper_id")
    if resource.title.strip() != case.title.strip():
        mismatches.append("title")
    if resource.version.strip() != case.version.strip():
        mismatches.append("version")
    if resource.source_url.strip() != case.source.strip():
        mismatches.append("source URL")
    if resource.sha256.lower() != case.source_hash.lower():
        mismatches.append("SHA-256 source hash")
    if resource.page_count != case.source_page_count:
        mismatches.append("page count")
    if mismatches:
        raise CaseBlockedError(
            "Fixed resource identity mismatch for " + ", ".join(mismatches) + "."
        )


def _resolve_resource_path(
    resource: RealPaperResource,
    manifest_path: Path,
    cache_root: str,
) -> Path:
    if resource.local_path.strip():
        candidate = Path(resource.local_path).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
    if not cache_root.strip():
        raise CaseBlockedError(
            "cache_identifier was supplied without a cache_root; offline resource cannot be resolved."
        )
    root = Path(cache_root).expanduser()
    resolved_root = root.resolve() if root.is_absolute() else (manifest_path.parent / root).resolve()
    candidate = (resolved_root / resource.cache_identifier).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise CaseBlockedError("cache_identifier escapes the configured cache_root.")
    return candidate


def _declared_source_identity(
    resource: RealPaperResource | None,
) -> PredictionSourceIdentity | None:
    if resource is None:
        return None
    return PredictionSourceIdentity(
        paper_id=resource.paper_id,
        doi=resource.doi,
        arxiv_id=resource.arxiv_id,
        openalex_id=resource.openalex_id,
        version=resource.version,
        source_url=resource.source_url,
        sha256=resource.sha256.lower(),
        page_count=resource.page_count,
        resource_identifier=resource.cache_identifier or f"sha256:{resource.sha256.lower()}",
    )


def _pdf_page_count(payload: bytes) -> int:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload), strict=False)
        return len(reader.pages)
    except Exception as error:
        raise CaseBlockedError(f"Unable to inspect fixed PDF page count: {error}") from error


def _insert_runtime_project_and_paper(
    connection,
    case: RuntimeEvaluationCase,
    resource: RealPaperResource,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO projects (
            id, title, description, keyword, field, language, workflow, stage,
            active_session_id, created_at, updated_at
        )
        VALUES (?, ?, '', ?, 'offline-real-paper-evaluation', 'en', 'rag',
                'evaluation', NULL, ?, ?)
        """,
        (case.project_id, f"Offline evaluation: {case.title}", case.question, now, now),
    )
    canonical_work_id = (
        f"doi:{resource.doi.lower()}"
        if resource.doi
        else f"arxiv:{resource.arxiv_id.lower()}"
        if resource.arxiv_id
        else f"openalex:{resource.openalex_id.lower()}"
    )
    connection.execute(
        """
        INSERT INTO papers (
            id, project_id, title, authors, abstract, year, type, venue,
            source, url, pdf_url, relation, priority, code, relevance_score,
            relevance_quality, matched_terms_json, review_required, created_at,
            doi, arxiv_id, openalex_id, canonical_work_id
        )
        VALUES (?, ?, ?, '', '', '', 'Evaluation', '', 'offline_fixed_pdf', ?, ?,
                '', 'High', '', 1.0, 'strong', '[]', 0, ?, ?, ?, ?, ?)
        """,
        (
            case.paper_id,
            case.project_id,
            case.title,
            resource.source_url,
            resource.source_url,
            now,
            resource.doi,
            resource.arxiv_id,
            resource.openalex_id,
            canonical_work_id,
        ),
    )


@contextmanager
def _offline_rag_environment(database_path: Path) -> Iterator[None]:
    overrides = {
        "SCHOLARFLOW_DB_PATH": str(database_path),
        "SCHOLARFLOW_MODEL_PROVIDER": "local",
        "SCHOLARFLOW_RAG_EMBEDDING_PROVIDER": "local",
        "SCHOLARFLOW_RAG_GENERATION_PROVIDER": "local",
        "OPENROUTER_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _answer_language(question: str) -> Literal["zh-CN", "en"]:
    return "zh-CN" if re.search(r"[\u3400-\u9fff]", question) else "en"


def _isolation_id(dataset_id: str, case_id: str) -> str:
    digest = hashlib.sha256(f"{dataset_id}\0{case_id}".encode("utf-8")).hexdigest()[:16]
    return f"case-{digest}"


def _require_private_tmp_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path("/private/tmp") or Path("/private/tmp") not in resolved.parents:
        raise ValueError(f"{label} must be under /private/tmp")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run fixed local PDFs through ScholarFlow PDF ingestion, FTS retrieval, and "
            "RAG answer services without exposing evaluation gold labels."
        )
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.18)
    args = parser.parse_args()
    predictions = run_real_paper_predictions(
        cases_path=args.cases,
        resources_path=args.resources,
        output_path=args.output,
        work_dir=args.work_dir,
        top_k=args.top_k,
        min_score=args.min_score,
    )
    counts: dict[str, int] = {}
    for case in predictions.cases:
        counts[case.execution_status] = counts.get(case.execution_status, 0) + 1
    print(
        json.dumps(
            {
                "prediction_source": predictions.prediction_source,
                "prediction_set_id": predictions.prediction_set_id,
                "case_count": len(predictions.cases),
                "status_counts": counts,
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
