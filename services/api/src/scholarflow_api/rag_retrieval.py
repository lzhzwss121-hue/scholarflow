from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import ssl
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

import certifi

from scholarflow_api.database import utc_now


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_LOCAL_DIMENSIONS = 384
DEFAULT_MIN_SCORE = 0.18
LOCAL_EMBEDDING_MODEL = "local/hash-embedding-v1"
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_LATIN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_RETRIEVAL_STOP_TERMS = {
    "about",
    "answer",
    "approach",
    "current",
    "evidence",
    "find",
    "from",
    "how",
    "method",
    "methods",
    "model",
    "models",
    "paper",
    "papers",
    "result",
    "results",
    "study",
    "that",
    "the",
    "these",
    "this",
    "use",
    "uses",
    "using",
    "what",
    "which",
    "with",
}
_CJK_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "对象幻觉": ("object hallucination",),
    "物体幻觉": ("object hallucination",),
    "幻觉": ("hallucination",),
    "视觉定位": ("visual grounding",),
    "证据忠实性": ("evidence faithfulness",),
    "忠实性": ("faithfulness",),
    "检索增强生成": ("retrieval augmented generation", "rag"),
    "大语言模型": ("large language model", "llm"),
    "视觉语言模型": ("vision language model", "vlm"),
    "多模态大模型": ("multimodal large language model", "mllm"),
    "多模态": ("multimodal",),
    "机制可解释性": ("mechanistic interpretability",),
    "稀疏自编码器": ("sparse autoencoder", "sae"),
    "不确定性校准": ("uncertainty calibration",),
    "失败模式": ("failure mode",),
    "鲁棒性": ("robustness",),
    "解码": ("decoding",),
    "基准": ("benchmark",),
    "评测": ("evaluation",),
    "数据集": ("dataset",),
    "指标": ("metric",),
    "实验": ("experiment",),
    "医学": ("medical",),
    "图像": ("image",),
    "分割": ("segmentation",),
}


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int
    external_data_transfer: bool

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@dataclass
class EmbeddingRun:
    provider: str
    model: str
    dimensions: int
    requested_chunks: int
    embedded_chunks: int
    skipped_chunks: int
    failed_chunks: int
    status: str
    external_data_transfer: bool
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "requested_chunks": self.requested_chunks,
            "embedded_chunks": self.embedded_chunks,
            "skipped_chunks": self.skipped_chunks,
            "failed_chunks": self.failed_chunks,
            "status": self.status,
            "external_data_transfer": self.external_data_transfer,
            "warnings": self.warnings,
        }


class LocalHashEmbeddingProvider:
    """Deterministic, dependency-free lexical embeddings for local-first retrieval.

    This is intentionally labelled as a hash embedding rather than a semantic
    model. It keeps a zero-key installation useful and provides a stable
    fallback, while OpenRouter can be selected explicitly for semantic vectors.
    """

    name = "local"
    model = LOCAL_EMBEDDING_MODEL
    external_data_transfer = False

    def __init__(self, dimensions: int | None = None) -> None:
        configured = dimensions or _env_int(
            "SCHOLARFLOW_RAG_LOCAL_DIMENSIONS",
            DEFAULT_LOCAL_DIMENSIONS,
            minimum=64,
            maximum=2048,
        )
        self.dimensions = configured

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [local_hash_embedding(text, self.dimensions) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return local_hash_embedding(text, self.dimensions)


class OpenRouterEmbeddingProvider:
    name = "openrouter"
    external_data_transfer = True

    def __init__(self) -> None:
        self.model = os.getenv("OPENROUTER_RAG_MODEL") or DEFAULT_OPENROUTER_EMBEDDING_MODEL
        self.base_url = os.getenv("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self.api_key = os.getenv("OPENROUTER_API_KEY") or ""
        self.app_url = os.getenv(
            "OPENROUTER_APP_URL",
            "https://github.com/lzhzwss121-hue/scholarflow",
        )
        self.app_title = os.getenv("OPENROUTER_APP_TITLE", "ScholarFlow")
        self.timeout_seconds = _env_float(
            "OPENROUTER_TIMEOUT_SECONDS",
            25.0,
            minimum=1.0,
            maximum=120.0,
        )
        self.batch_size = _env_int(
            "SCHOLARFLOW_RAG_EMBEDDING_BATCH_SIZE",
            16,
            minimum=1,
            maximum=64,
        )
        self.dimensions = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed(texts[start : start + self.batch_size], "search_document"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text], "search_query")
        return vectors[0]

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingError(
                "OPENROUTER_API_KEY 未配置；未向外部服务发送论文文本。"
            )
        if not texts:
            return []
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(
                {
                    "model": self.model,
                    "input": texts,
                    "input_type": input_type,
                    "encoding_format": "float",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.app_url,
                "X-Title": self.app_title,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = _safe_http_error_detail(error)
            raise EmbeddingError(f"OpenRouter embedding 请求失败（HTTP {error.code}）：{detail}") from error
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, json.JSONDecodeError) as error:
            raise EmbeddingError(
                f"OpenRouter embedding 请求失败（{error.__class__.__name__}）。"
            ) from error

        raw_rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(raw_rows, list) or len(raw_rows) != len(texts):
            raise EmbeddingError("OpenRouter embedding 返回数量与输入 chunk 数量不一致。")
        ordered = sorted(
            raw_rows,
            key=lambda row: int(row.get("index", 0)) if isinstance(row, dict) else 0,
        )
        vectors = [_validate_vector(row.get("embedding") if isinstance(row, dict) else None) for row in ordered]
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingError("OpenRouter embedding 返回了不一致的向量维度。")
        self.dimensions = dimensions
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    selected = (os.getenv("SCHOLARFLOW_RAG_EMBEDDING_PROVIDER") or "local").strip().lower()
    if selected in {"local", "hash", "local-hash"}:
        return LocalHashEmbeddingProvider()
    if selected in {"openrouter", "open-router"}:
        return OpenRouterEmbeddingProvider()
    if selected in {"disabled", "none", "off"}:
        raise EmbeddingError("RAG embedding 已通过 SCHOLARFLOW_RAG_EMBEDDING_PROVIDER 禁用。")
    raise EmbeddingError(f"不支持的 RAG embedding provider：{selected}")


def embed_project_chunks(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    paper_id: str | None = None,
    force: bool = False,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingRun:
    active_provider = provider or get_embedding_provider()
    parameters: list[Any] = [project_id]
    paper_filter = ""
    if paper_id:
        paper_filter = " AND paper_id = ?"
        parameters.append(paper_id)
    rows = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT id, chunk_hash, chunk_text, embedding_model,
                   embedding_dimensions, embedding_json
            FROM paper_chunks
            WHERE project_id = ?{paper_filter}
            ORDER BY paper_id ASC, chunk_index ASC
            """,
            parameters,
        ).fetchall()
    ]
    return _embed_chunk_rows(
        connection,
        rows=rows,
        force=force,
        provider=active_provider,
    )


def _embed_chunk_rows(
    connection: sqlite3.Connection,
    *,
    rows: list[dict[str, Any]],
    force: bool,
    provider: EmbeddingProvider,
) -> EmbeddingRun:
    active_provider = provider
    stored_dimensions = {
        int(row.get("embedding_dimensions") or 0)
        for row in rows
        if str(row.get("embedding_model") or "") == active_provider.model
        and str(row.get("embedding_json") or "")
        and int(row.get("embedding_dimensions") or 0) > 0
    }
    if not active_provider.dimensions and len(stored_dimensions) == 1:
        active_provider.dimensions = next(iter(stored_dimensions))
    mixed_stored_dimensions = len(stored_dimensions) > 1
    pending = [
        row
        for row in rows
        if force
        or mixed_stored_dimensions
        or not _row_has_compatible_embedding(row, active_provider)
    ]
    skipped = len(rows) - len(pending)
    if not pending:
        dimensions = _provider_dimensions(active_provider, rows)
        return EmbeddingRun(
            provider=active_provider.name,
            model=active_provider.model,
            dimensions=dimensions,
            requested_chunks=len(rows),
            embedded_chunks=0,
            skipped_chunks=skipped,
            failed_chunks=0,
            status="ready" if rows else "not_started",
            external_data_transfer=active_provider.external_data_transfer,
            warnings=[] if rows else ["当前范围没有可生成 embedding 的 chunk。"],
        )

    try:
        vectors = active_provider.embed_documents([str(row["chunk_text"]) for row in pending])
        if len(vectors) != len(pending):
            raise EmbeddingError("embedding provider 返回数量与待处理 chunk 数量不一致。")
        dimensions = len(vectors[0]) if vectors else 0
        if not dimensions or any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingError("embedding provider 返回了空向量或不一致的向量维度。")
    except EmbeddingError as error:
        return EmbeddingRun(
            provider=active_provider.name,
            model=active_provider.model,
            dimensions=active_provider.dimensions,
            requested_chunks=len(rows),
            embedded_chunks=0,
            skipped_chunks=skipped,
            failed_chunks=len(pending),
            status="failed",
            external_data_transfer=active_provider.external_data_transfer,
            warnings=[str(error)],
        )

    now = utc_now()
    updated = 0
    for row, vector in zip(pending, vectors, strict=True):
        cursor = connection.execute(
            """
            UPDATE paper_chunks
            SET embedding_model = ?,
                embedding_dimensions = ?,
                embedding_json = ?,
                updated_at = ?
            WHERE id = ? AND chunk_hash = ?
            """,
            (
                active_provider.model,
                dimensions,
                json.dumps(vector, separators=(",", ":")),
                now,
                row["id"],
                row["chunk_hash"],
            ),
        )
        updated += max(0, int(cursor.rowcount or 0))
    failed = len(pending) - updated
    return EmbeddingRun(
        provider=active_provider.name,
        model=active_provider.model,
        dimensions=dimensions,
        requested_chunks=len(rows),
        embedded_chunks=updated,
        skipped_chunks=skipped,
        failed_chunks=failed,
        status="ready" if failed == 0 else "partial",
        external_data_transfer=active_provider.external_data_transfer,
        warnings=[] if failed == 0 else ["部分 chunk 在 embedding 期间已变化，未写入过期向量。"],
    )


def retrieve_project_chunks(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    query: str,
    top_k: int,
    paper_ids: list[str] | None = None,
    evidence_levels: list[str] | None = None,
    sections: list[str] | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
    max_chunks_per_paper: int = 3,
    refresh_embeddings: bool = True,
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    normalized_query = normalize_retrieval_text(query)
    if not normalized_query:
        return _empty_retrieval_result(
            query,
            top_k,
            min_score,
            "检索问题为空。",
            query_anchor_terms=[],
        )
    query_terms = retrieval_terms(normalized_query)
    query_anchors = retrieval_anchor_terms(normalized_query)

    parameters: list[Any] = [project_id]
    filters = ["pc.project_id = ?"]
    if paper_ids:
        placeholders = ",".join("?" for _ in paper_ids)
        filters.append(f"pc.paper_id IN ({placeholders})")
        parameters.extend(paper_ids)
    if evidence_levels:
        placeholders = ",".join("?" for _ in evidence_levels)
        filters.append(f"pc.evidence_level IN ({placeholders})")
        parameters.extend(evidence_levels)
    if sections:
        placeholders = ",".join("?" for _ in sections)
        filters.append(f"pc.section IN ({placeholders})")
        parameters.extend(sections)
    rows = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT
                pc.*,
                p.title AS paper_title,
                p.authors AS paper_authors,
                p.year AS paper_year,
                p.venue AS paper_venue,
                p.url AS paper_url
            FROM paper_chunks pc
            JOIN papers p ON p.id = pc.paper_id AND p.project_id = pc.project_id
            WHERE {' AND '.join(filters)}
            ORDER BY pc.paper_id ASC, pc.chunk_index ASC
            """,
            parameters,
        ).fetchall()
    ]
    if not rows:
        return _empty_retrieval_result(
            query,
            top_k,
            min_score,
            "当前项目或筛选范围没有可检索的论文 chunk。",
            query_anchor_terms=query_anchors,
        )

    warnings: list[str] = []
    active_provider: EmbeddingProvider | None = provider
    embedding_run: EmbeddingRun | None = None
    try:
        active_provider = active_provider or get_embedding_provider()
        if refresh_embeddings:
            embedding_run = _embed_chunk_rows(
                connection,
                rows=rows,
                force=False,
                provider=active_provider,
            )
            warnings.extend(embedding_run.warnings)
            if embedding_run.embedded_chunks:
                rows = _refresh_embedding_columns(connection, rows)
        query_vector = active_provider.embed_query(normalized_query)
    except EmbeddingError as error:
        query_vector = []
        warnings.append(str(error))

    document_term_sets = [set(retrieval_terms(str(row["chunk_text"]))) for row in rows]
    document_frequency = Counter(
        term
        for terms in document_term_sets
        for term in set(query_terms).intersection(terms)
    )
    scored: list[dict[str, Any]] = []
    vector_ready_count = 0
    for row, document_terms in zip(rows, document_term_sets, strict=True):
        lexical_score = lexical_relevance_score(
            normalized_query,
            query_terms,
            str(row["chunk_text"]),
            document_terms,
            document_frequency,
            len(rows),
        )
        stored_vector = _parse_stored_vector(row, active_provider)
        vector_score = cosine_similarity(query_vector, stored_vector) if query_vector and stored_vector else 0.0
        matched_query_terms = matched_retrieval_anchors(query_anchors, str(row["chunk_text"]))
        anchor_coverage = (
            len(matched_query_terms) / len(query_anchors)
            if query_anchors
            else lexical_score
        )
        if stored_vector:
            vector_ready_count += 1
        if query_vector and stored_vector:
            if active_provider and (
                active_provider.model == LOCAL_EMBEDDING_MODEL
                or active_provider.name == "local"
            ):
                # The local provider is a deterministic lexical hash, not a
                # semantic model. Keep collision-prone vector similarity as a
                # small tie-breaker instead of the main relevance signal.
                hybrid_score = 0.80 * lexical_score + 0.20 * max(0.0, vector_score)
            else:
                hybrid_score = 0.45 * lexical_score + 0.55 * max(0.0, vector_score)
            retrieval_mode = "hybrid"
        else:
            hybrid_score = lexical_score
            retrieval_mode = "lexical_only"
        passes_relevance_gate = passes_query_relevance_gate(
            query_anchor_count=len(query_anchors),
            anchor_coverage=anchor_coverage,
            lexical_score=lexical_score,
            vector_score=max(0.0, vector_score),
            retrieval_mode=retrieval_mode,
            provider=active_provider,
        )
        if str(row.get("evidence_level")) == "full_text" and hybrid_score > 0:
            hybrid_score = min(1.0, hybrid_score + 0.015)
        scored.append(
            {
                **row,
                "lexical_score": round(lexical_score, 6),
                "vector_score": round(max(0.0, vector_score), 6),
                "hybrid_score": round(hybrid_score, 6),
                "anchor_coverage": round(anchor_coverage, 6),
                "matched_query_terms": matched_query_terms,
                "query_anchor_count": len(query_anchors),
                "passes_relevance_gate": passes_relevance_gate,
                "retrieval_mode": retrieval_mode,
            }
        )

    scored.sort(
        key=lambda row: (
            float(row["hybrid_score"]),
            1 if row.get("evidence_level") == "full_text" else 0,
            -int(row.get("chunk_index") or 0),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    per_paper: Counter[str] = Counter()
    gated_count = 0
    for row in scored:
        if float(row["hybrid_score"]) < min_score:
            continue
        if not bool(row["passes_relevance_gate"]):
            gated_count += 1
            continue
        paper_id = str(row["paper_id"])
        if per_paper[paper_id] >= max_chunks_per_paper:
            continue
        per_paper[paper_id] += 1
        selected.append(_retrieval_hit(row, rank=len(selected) + 1))
        if len(selected) >= top_k:
            break

    vector_complete = bool(query_vector) and vector_ready_count == len(rows)
    retrieval_mode = "hybrid" if vector_complete else "lexical_only"
    if not selected:
        status = "no_reliable_hit"
        if gated_count:
            warnings.append(
                "候选虽然达到数值阈值，但缺少足够 query anchor 原文重合，已拒绝向量碰撞或泛化词命中。"
            )
        warnings.append(
            f"没有 chunk 达到最小相关性阈值 {min_score:.2f}；未返回低置信度证据。"
        )
    elif vector_complete and not warnings:
        status = "complete"
    else:
        status = "partial"
    provider_name = active_provider.name if active_provider else "disabled"
    model = active_provider.model if active_provider else ""
    dimensions = len(query_vector) if query_vector else 0
    score_explanation = retrieval_score_explanation(
        retrieval_mode=retrieval_mode,
        provider=active_provider,
    )
    return {
        "query": query,
        "status": status,
        "retrieval_mode": retrieval_mode,
        "provider": provider_name,
        "embedding_model": model,
        "embedding_dimensions": dimensions,
        "external_data_transfer": bool(active_provider and active_provider.external_data_transfer),
        "candidate_chunks": len(rows),
        "vector_ready_chunks": vector_ready_count,
        "returned_hits": len(selected),
        "top_k": top_k,
        "min_score": min_score,
        "query_anchor_terms": query_anchors,
        "rejected_by_relevance_gate": gated_count,
        "score_explanation": score_explanation,
        "hits": selected,
        "warnings": list(dict.fromkeys(warnings)),
    }


def local_hash_embedding(text: str, dimensions: int) -> list[float]:
    features = Counter(retrieval_terms(text, include_bigrams=True))
    vector = [0.0] * dimensions
    for feature, count in features.items():
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign * (1.0 + math.log(max(1, count)))
    return normalize_vector(vector)


def retrieval_terms(text: str, *, include_bigrams: bool = False) -> list[str]:
    normalized = expand_bilingual_retrieval_text(text)
    terms = _LATIN_PATTERN.findall(normalized)
    latin_words = list(terms)
    for term in latin_words:
        if "-" in term or "_" in term:
            terms.extend(part for part in re.split(r"[-_]+", term) if part)
    for run in _CJK_PATTERN.findall(normalized):
        characters = list(run)
        terms.extend(characters)
        terms.extend("".join(characters[index : index + 2]) for index in range(len(characters) - 1))
    if include_bigrams:
        terms.extend(
            f"{latin_words[index]}::{latin_words[index + 1]}"
            for index in range(len(latin_words) - 1)
        )
    return terms


def retrieval_anchor_terms(text: str) -> list[str]:
    normalized = normalize_retrieval_text(text)
    anchors: list[str] = []
    for token in _LATIN_PATTERN.findall(normalized):
        parts = [part for part in re.split(r"[-_]+", token) if part]
        for part in parts:
            if len(part) >= 3 and part not in _RETRIEVAL_STOP_TERMS and not part.isdigit():
                anchors.append(part)
        if len(parts) > 1:
            phrase = " ".join(parts)
            if phrase not in _RETRIEVAL_STOP_TERMS:
                anchors.append(phrase)
    for run in _CJK_PATTERN.findall(normalized):
        aliases = [
            english
            for chinese, english_aliases in sorted(
                _CJK_QUERY_ALIASES.items(),
                key=lambda item: len(item[0]),
                reverse=True,
            )
            if chinese in run
            for english in english_aliases
        ]
        if aliases:
            for alias in aliases:
                anchors.append(alias)
                anchors.extend(
                    part
                    for part in alias.split()
                    if len(part) >= 3 and part not in _RETRIEVAL_STOP_TERMS
                )
        elif 2 <= len(run) <= 8:
            anchors.append(run)
        elif len(run) > 8:
            anchors.extend(
                run[index : index + 2]
                for index in range(len(run) - 1)
                if run[index : index + 2] not in {"哪些", "如何", "当前", "论文", "研究", "方法"}
            )
    return list(dict.fromkeys(anchors))


def matched_retrieval_anchors(anchors: list[str], document: str) -> list[str]:
    normalized_document = normalize_retrieval_match_text(
        expand_bilingual_retrieval_text(document)
    )
    matches: list[str] = []
    for anchor in anchors:
        normalized_anchor = normalize_retrieval_match_text(anchor)
        if not normalized_anchor:
            continue
        if _CJK_PATTERN.search(normalized_anchor):
            matched = normalized_anchor in normalized_document
        else:
            pattern = r"(?<![a-z0-9])" + r"[\s-]+".join(
                re.escape(part)
                for part in normalized_anchor.split()
                if part
            ) + r"(?![a-z0-9])"
            matched = bool(re.search(pattern, normalized_document))
        if matched:
            matches.append(anchor)
    return matches


def passes_query_relevance_gate(
    *,
    query_anchor_count: int,
    anchor_coverage: float,
    lexical_score: float,
    vector_score: float,
    retrieval_mode: str,
    provider: EmbeddingProvider | None,
) -> bool:
    if query_anchor_count <= 0:
        return lexical_score >= 0.18
    minimum_coverage = 1.0 if query_anchor_count == 1 else (0.34 if query_anchor_count <= 3 else 0.25)
    lexical_support = anchor_coverage >= minimum_coverage and lexical_score >= 0.10
    if lexical_support:
        return True
    semantic_provider = bool(
        retrieval_mode == "hybrid"
        and provider
        and provider.name != "local"
        and provider.model != LOCAL_EMBEDDING_MODEL
    )
    return semantic_provider and vector_score >= 0.55


def lexical_relevance_score(
    query: str,
    query_terms: list[str],
    document: str,
    document_terms: set[str],
    document_frequency: Counter[str],
    document_count: int,
) -> float:
    anchor_terms = retrieval_anchor_terms(query)
    unique_query_terms = set(anchor_terms or query_terms)
    if not unique_query_terms:
        return 0.0
    weighted_total = 0.0
    weighted_match = 0.0
    for term in unique_query_terms:
        weight = math.log((document_count + 1) / (document_frequency.get(term, 0) + 1)) + 1.0
        weighted_total += weight
        if term in document_terms:
            weighted_match += weight
    coverage = weighted_match / weighted_total if weighted_total else 0.0
    phrase_bonus = (
        1.0
        if len(query) >= 4
        and normalize_retrieval_match_text(query) in normalize_retrieval_match_text(document)
        else 0.0
    )
    return min(1.0, 0.88 * coverage + 0.12 * phrase_bonus)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not magnitude:
        return vector
    return [value / magnitude for value in vector]


def normalize_retrieval_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def normalize_retrieval_match_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", str(value or "").lower())).strip()


def expand_bilingual_retrieval_text(value: Any) -> str:
    """Append deterministic Chinese/English equivalents for local retrieval.

    This is a small auditable concept lexicon, not machine translation. It
    improves both Chinese-query/English-paper and English-query/Chinese-paper
    recall without pretending the local hash provider is a semantic model.
    """

    normalized = normalize_retrieval_text(value)
    if not normalized:
        return ""
    equivalents: list[str] = []
    for chinese, english_aliases in sorted(
        _CJK_QUERY_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if chinese in normalized:
            equivalents.extend(english_aliases)
        for english in english_aliases:
            english_pattern = r"(?<![a-z0-9])" + r"[\s-]+".join(
                re.escape(part)
                for part in english.split()
                if part
            ) + r"(?![a-z0-9])"
            if re.search(english_pattern, normalize_retrieval_match_text(normalized)):
                equivalents.append(chinese)
    return " ".join([normalized, *dict.fromkeys(equivalents)]).strip()


def _retrieval_hit(row: dict[str, Any], *, rank: int) -> dict[str, Any]:
    page_start = row.get("page_start")
    page_end = row.get("page_end")
    page_label = (
        f"p.{page_start}"
        if page_start is not None and page_start == page_end
        else (
            f"pp.{page_start}-{page_end}"
            if page_start is not None and page_end is not None
            else "page-unknown"
        )
    )
    section = str(row.get("section") or "unknown")
    citation_id = f"{row['paper_id']}:{section}:{page_label}:chunk-{row['chunk_index']}"
    match_strength = retrieval_match_strength(
        hybrid_score=float(row["hybrid_score"]),
        anchor_coverage=float(row.get("anchor_coverage") or 0.0),
        matched_query_terms=list(row.get("matched_query_terms") or []),
        retrieval_mode=str(row.get("retrieval_mode") or "lexical_only"),
    )
    match_explanation = retrieval_match_explanation(
        row,
        match_strength=match_strength,
    )
    return {
        "rank": rank,
        "citation_id": citation_id,
        "paper_id": str(row["paper_id"]),
        "paper_title": str(row.get("paper_title") or ""),
        "paper_authors": str(row.get("paper_authors") or ""),
        "paper_year": str(row.get("paper_year") or ""),
        "paper_venue": str(row.get("paper_venue") or ""),
        "paper_url": str(row.get("paper_url") or ""),
        "chunk_id": str(row["id"]),
        "chunk_index": int(row["chunk_index"]),
        "chunk_hash": str(row["chunk_hash"]),
        "source": str(row.get("source") or ""),
        "source_origin": str(row.get("source_origin") or ""),
        "evidence_level": str(row.get("evidence_level") or "metadata_only"),
        "section": section,
        "page_start": page_start,
        "page_end": page_end,
        "text": str(row.get("chunk_text") or ""),
        "lexical_score": float(row["lexical_score"]),
        "vector_score": float(row["vector_score"]),
        "hybrid_score": float(row["hybrid_score"]),
        "anchor_coverage": float(row.get("anchor_coverage") or 0.0),
        "matched_query_terms": list(row.get("matched_query_terms") or []),
        "match_strength": match_strength,
        "match_explanation": match_explanation,
    }


def retrieval_match_strength(
    *,
    hybrid_score: float,
    anchor_coverage: float,
    matched_query_terms: list[str],
    retrieval_mode: str,
) -> str:
    if matched_query_terms and anchor_coverage >= 0.6 and hybrid_score >= 0.35:
        return "strong"
    if (
        matched_query_terms
        and anchor_coverage >= 0.3
        and hybrid_score >= 0.22
    ) or (
        retrieval_mode == "hybrid"
        and hybrid_score >= 0.55
    ):
        return "moderate"
    return "borderline"


def retrieval_match_explanation(
    row: dict[str, Any],
    *,
    match_strength: str,
) -> str:
    matched = list(row.get("matched_query_terms") or [])
    anchor_count = max(0, int(row.get("query_anchor_count") or 0))
    matched_label = " / ".join(matched[:6]) if matched else "无直接词面锚点"
    evidence_label = (
        "PDF/用户全文"
        if str(row.get("evidence_level") or "") == "full_text"
        else "论文摘要"
        if str(row.get("evidence_level") or "") == "abstract_only"
        else "元数据"
    )
    strength_label = {
        "strong": "强命中",
        "moderate": "中等命中",
        "borderline": "门槛命中",
    }.get(match_strength, "门槛命中")
    return (
        f"{strength_label}：覆盖 {len(matched)}/{anchor_count} 个问题锚点"
        f"（{matched_label}）；关键词分 {float(row['lexical_score']):.2f}，"
        f"向量分 {float(row['vector_score']):.2f}，"
        f"混合分 {float(row['hybrid_score']):.2f}；证据来自{evidence_label}。"
    )


def retrieval_score_explanation(
    *,
    retrieval_mode: str,
    provider: EmbeddingProvider | None,
) -> str:
    if retrieval_mode == "lexical_only":
        return (
            "当前混合分等于关键词相关性分；结果仍须通过问题锚点覆盖门槛，"
            "该分数不是论文结论正确率。"
        )
    if provider and (
        provider.name == "local"
        or provider.model == LOCAL_EMBEDDING_MODEL
    ):
        return (
            "本地模式的混合分由 80% 关键词相关性与 20% hash 向量相似度组成；"
            "hash 向量只作排序辅助，不是训练语义模型，结果仍须通过问题锚点门槛。"
        )
    return (
        "外部语义模式的混合分由 45% 关键词相关性与 55% 向量相似度组成；"
        "语义命中仍不代表论文结论正确，必须核对 citation 原文。"
    )


def _refresh_embedding_columns(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {
        str(row["id"]): dict(row)
        for row in connection.execute(
            """
            SELECT id, embedding_model, embedding_dimensions, embedding_json
            FROM paper_chunks
            WHERE id IN ({})
            """.format(",".join("?" for _ in rows)),
            [row["id"] for row in rows],
        ).fetchall()
    }
    for row in rows:
        refreshed = by_id.get(str(row["id"]))
        if refreshed:
            row.update(refreshed)
    return rows


def _row_has_compatible_embedding(
    row: dict[str, Any],
    provider: EmbeddingProvider,
) -> bool:
    if str(row.get("embedding_model") or "") != provider.model:
        return False
    vector = _parse_json_vector(row.get("embedding_json"))
    if not vector:
        return False
    expected_dimensions = provider.dimensions
    return not expected_dimensions or len(vector) == expected_dimensions


def _parse_stored_vector(
    row: dict[str, Any],
    provider: EmbeddingProvider | None,
) -> list[float]:
    if provider is None or str(row.get("embedding_model") or "") != provider.model:
        return []
    vector = _parse_json_vector(row.get("embedding_json"))
    if not vector:
        return []
    if provider.dimensions and len(vector) != provider.dimensions:
        return []
    return normalize_vector(vector)


def _parse_json_vector(value: Any) -> list[float]:
    try:
        parsed = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError):
        return []
    try:
        return _validate_vector(parsed)
    except EmbeddingError:
        return []


def _validate_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise EmbeddingError("embedding provider 返回了空向量。")
    vector: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or not math.isfinite(float(item)):
            raise EmbeddingError("embedding provider 返回了非法向量值。")
        vector.append(float(item))
    return vector


def _provider_dimensions(
    provider: EmbeddingProvider,
    rows: list[dict[str, Any]],
) -> int:
    if provider.dimensions:
        return provider.dimensions
    for row in rows:
        if str(row.get("embedding_model") or "") == provider.model:
            dimensions = int(row.get("embedding_dimensions") or 0)
            if dimensions:
                return dimensions
    return 0


def _empty_retrieval_result(
    query: str,
    top_k: int,
    min_score: float,
    warning: str,
    *,
    query_anchor_terms: list[str],
) -> dict[str, Any]:
    return {
        "query": query,
        "status": "no_reliable_hit",
        "retrieval_mode": "lexical_only",
        "provider": "",
        "embedding_model": "",
        "embedding_dimensions": 0,
        "external_data_transfer": False,
        "candidate_chunks": 0,
        "vector_ready_chunks": 0,
        "returned_hits": 0,
        "top_k": top_k,
        "min_score": min_score,
        "query_anchor_terms": query_anchor_terms,
        "rejected_by_relevance_gate": 0,
        "score_explanation": (
            "当前没有可评分的命中；系统不会把空结果或低相关 chunk 包装成答案。"
        ),
        "hits": [],
        "warnings": [warning],
    }


def _safe_http_error_detail(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return "远程服务拒绝请求"
    message = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(message, dict):
        message = message.get("message")
    normalized = re.sub(r"\s+", " ", str(message or "")).strip()
    return normalized[:240] or "远程服务拒绝请求"


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
