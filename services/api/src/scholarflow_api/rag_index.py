from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from scholarflow_api.database import new_id


RAG_CHUNK_SIZE = max(400, int(os.getenv("SCHOLARFLOW_RAG_CHUNK_SIZE", "1400")))
RAG_CHUNK_OVERLAP = max(
    0,
    min(
        RAG_CHUNK_SIZE // 3,
        int(os.getenv("SCHOLARFLOW_RAG_CHUNK_OVERLAP", "180")),
    ),
)
RAG_MIN_CHUNK_CHARS = max(40, int(os.getenv("SCHOLARFLOW_RAG_MIN_CHUNK_CHARS", "120")))
RAG_INDEX_VERSION = "paper_chunks.v1"
EVIDENCE_RANK = {"metadata_only": 0, "abstract_only": 1, "full_text": 2}


@dataclass
class LocatedTextBlock:
    section: str
    page: int | None
    text: str


@dataclass
class PaperChunkRecord:
    id: str
    project_id: str
    paper_id: str
    chunk_index: int
    source: str
    source_origin: str
    evidence_level: str
    section: str
    page_start: int | None
    page_end: int | None
    chunk_text: str
    char_count: int
    token_count: int
    chunk_hash: str
    index_version: str
    embedding_model: str
    embedding_dimensions: int
    embedding_json: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_paper_chunks(
    *,
    project_id: str,
    paper_id: str,
    text: str,
    source: str,
    source_origin: str,
    evidence_level: str,
    now: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[PaperChunkRecord]:
    normalized = normalize_source_text(text)
    if len(normalized) < 40:
        return []
    effective_size = max(200, chunk_size or RAG_CHUNK_SIZE)
    effective_overlap = max(0, min(effective_size // 3, RAG_CHUNK_OVERLAP if overlap is None else overlap))
    records: list[PaperChunkRecord] = []
    for block in parse_located_text_blocks(normalized):
        pieces = split_block_text(block.text, effective_size, effective_overlap)
        for piece in pieces:
            if len(piece) < RAG_MIN_CHUNK_CHARS and records:
                previous = records[-1]
                if (
                    previous.page_start == block.page
                    and previous.section == block.section
                    and len(previous.chunk_text) + len(piece) + 1 <= effective_size + effective_overlap
                ):
                    merged = normalize_inline_text(f"{previous.chunk_text} {piece}")
                    previous.chunk_text = merged
                    previous.char_count = len(merged)
                    previous.token_count = estimate_token_count(merged)
                    previous.chunk_hash = chunk_checksum(
                        source=previous.source,
                        section=previous.section,
                        page=previous.page_start,
                        text=merged,
                    )
                    continue
            chunk_index = len(records)
            records.append(
                PaperChunkRecord(
                    id=new_id("paper_chunk"),
                    project_id=project_id,
                    paper_id=paper_id,
                    chunk_index=chunk_index,
                    source=source,
                    source_origin=source_origin,
                    evidence_level=evidence_level,
                    section=block.section,
                    page_start=block.page,
                    page_end=block.page,
                    chunk_text=piece,
                    char_count=len(piece),
                    token_count=estimate_token_count(piece),
                    chunk_hash=chunk_checksum(
                        source=source,
                        section=block.section,
                        page=block.page,
                        text=piece,
                    ),
                    index_version=RAG_INDEX_VERSION,
                    embedding_model="",
                    embedding_dimensions=0,
                    embedding_json="",
                    created_at=now,
                    updated_at=now,
                ),
            )
    return records


def parse_located_text_blocks(text: str) -> list[LocatedTextBlock]:
    blocks: list[LocatedTextBlock] = []
    current_page: int | None = None
    current_section = "unknown"
    buffer: list[str] = []

    def flush() -> None:
        body = normalize_source_text("\n".join(buffer))
        buffer.clear()
        if body:
            blocks.append(LocatedTextBlock(section=current_section, page=current_page, text=body))

    for line in text.splitlines():
        stripped = line.strip()
        page_match = re.fullmatch(r"\[PDF page (\d+)\]", stripped)
        if page_match:
            flush()
            current_page = int(page_match.group(1))
            continue
        section_match = re.fullmatch(r"\[Section: ([a-z_]+)\]", stripped)
        if section_match:
            flush()
            current_section = section_match.group(1)
            continue
        buffer.append(line)
    flush()
    return blocks or [LocatedTextBlock(section="unknown", page=None, text=text)]


def split_block_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = normalize_inline_text(text)
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        hard_end = min(len(normalized), start + chunk_size)
        end = choose_chunk_boundary(normalized, start, hard_end)
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and normalized[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def choose_chunk_boundary(text: str, start: int, hard_end: int) -> int:
    if hard_end >= len(text):
        return len(text)
    minimum = start + int((hard_end - start) * 0.62)
    candidate = text[start:hard_end]
    boundaries = [
        candidate.rfind("。"),
        candidate.rfind("！"),
        candidate.rfind("？"),
        candidate.rfind(". "),
        candidate.rfind("; "),
        candidate.rfind("；"),
        candidate.rfind(" "),
    ]
    best = max(boundaries)
    return start + best + 1 if best >= minimum - start else hard_end


def replace_paper_chunks(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    paper_id: str,
    text: str,
    source: str,
    source_origin: str,
    evidence_level: str,
    now: str,
    allow_downgrade: bool = False,
) -> list[dict[str, Any]]:
    existing = connection.execute(
        """
        SELECT evidence_level
        FROM paper_chunks
        WHERE project_id = ? AND paper_id = ?
        ORDER BY
            CASE evidence_level
                WHEN 'full_text' THEN 2
                WHEN 'abstract_only' THEN 1
                ELSE 0
            END DESC
        LIMIT 1
        """,
        (project_id, paper_id),
    ).fetchone()
    existing_level = str(existing["evidence_level"]) if existing else ""
    if (
        existing_level
        and EVIDENCE_RANK.get(existing_level, 0) > EVIDENCE_RANK.get(evidence_level, 0)
        and not allow_downgrade
    ):
        return fetch_paper_chunks(connection, project_id, paper_id)

    records = build_paper_chunks(
        project_id=project_id,
        paper_id=paper_id,
        text=text,
        source=source,
        source_origin=source_origin,
        evidence_level=evidence_level,
        now=now,
    )
    if not records:
        return fetch_paper_chunks(connection, project_id, paper_id)

    connection.execute(
        "DELETE FROM paper_chunks WHERE project_id = ? AND paper_id = ?",
        (project_id, paper_id),
    )
    connection.executemany(
        """
        INSERT INTO paper_chunks (
            id, project_id, paper_id, chunk_index, source, source_origin,
            evidence_level, section, page_start, page_end, chunk_text,
            char_count, token_count, chunk_hash, index_version,
            embedding_model, embedding_dimensions, embedding_json,
            created_at, updated_at
        )
        VALUES (
            :id, :project_id, :paper_id, :chunk_index, :source, :source_origin,
            :evidence_level, :section, :page_start, :page_end, :chunk_text,
            :char_count, :token_count, :chunk_hash, :index_version,
            :embedding_model, :embedding_dimensions, :embedding_json,
            :created_at, :updated_at
        )
        """,
        [record.to_dict() for record in records],
    )
    return [record.to_dict() for record in records]


def index_paper_abstract(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    paper_id: str,
    abstract: str,
    source_origin: str,
    now: str,
) -> list[dict[str, Any]]:
    return replace_paper_chunks(
        connection,
        project_id=project_id,
        paper_id=paper_id,
        text=abstract,
        source="metadata.abstract",
        source_origin=source_origin,
        evidence_level="abstract_only",
        now=now,
    )


def index_paper_full_text(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    paper_id: str,
    text: str,
    source_origin: str,
    now: str,
) -> list[dict[str, Any]]:
    source = "user_provided.full_text" if source_origin == "user_provided" else "pdf.full_text"
    return replace_paper_chunks(
        connection,
        project_id=project_id,
        paper_id=paper_id,
        text=text,
        source=source,
        source_origin=source_origin,
        evidence_level="full_text",
        now=now,
    )


def fetch_paper_chunks(
    connection: sqlite3.Connection,
    project_id: str,
    paper_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM paper_chunks
        WHERE project_id = ? AND paper_id = ?
        ORDER BY chunk_index ASC
        """,
        (project_id, paper_id),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_paper_chunks(
    connection: sqlite3.Connection,
    project_id: str,
    paper_id: str,
) -> int:
    cursor = connection.execute(
        "DELETE FROM paper_chunks WHERE project_id = ? AND paper_id = ?",
        (project_id, paper_id),
    )
    return max(0, int(cursor.rowcount or 0))


def paper_index_status(
    connection: sqlite3.Connection,
    project_id: str,
    paper_id: str,
    *,
    message: str = "",
) -> dict[str, Any]:
    rows = fetch_paper_chunks(connection, project_id, paper_id)
    levels = {str(row.get("evidence_level") or "") for row in rows}
    sections = list(dict.fromkeys(str(row.get("section") or "unknown") for row in rows))
    pages = sorted(
        {
            int(row["page_start"])
            for row in rows
            if row.get("page_start") is not None
        },
    )
    evidence_level = "full_text" if "full_text" in levels else ("abstract_only" if rows else "metadata_only")
    embedded_count = sum(1 for row in rows if str(row.get("embedding_json") or ""))
    embedding_models = {
        str(row.get("embedding_model") or "")
        for row in rows
        if str(row.get("embedding_json") or "")
    }
    embedding_dimensions = {
        int(row.get("embedding_dimensions") or 0)
        for row in rows
        if str(row.get("embedding_json") or "")
    }
    embedding_status = (
        "ready"
        if rows and embedded_count == len(rows)
        else ("partial" if embedded_count else "not_started")
    )
    return {
        "paper_id": paper_id,
        "status": "indexed" if rows else "not_indexed",
        "chunk_count": len(rows),
        "evidence_level": evidence_level,
        "source": str(rows[0].get("source") or "") if rows else "",
        "source_origin": str(rows[0].get("source_origin") or "") if rows else "",
        "sections": sections if rows else [],
        "page_numbers": pages,
        "indexed_at": max((str(row.get("updated_at") or "") for row in rows), default=""),
        "index_version": str(rows[0].get("index_version") or "") if rows else RAG_INDEX_VERSION,
        "embedding_status": embedding_status,
        "embedded_chunks": embedded_count,
        "embedding_model": (
            next(iter(embedding_models))
            if len(embedding_models) == 1
            else ("mixed" if embedding_models else "")
        ),
        "embedding_dimensions": (
            next(iter(embedding_dimensions))
            if len(embedding_dimensions) == 1
            else 0
        ),
        "message": message,
    }


def project_index_status(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    paper_rows = connection.execute(
        "SELECT id FROM papers WHERE project_id = ? ORDER BY created_at ASC",
        (project_id,),
    ).fetchall()
    aggregate = connection.execute(
        """
        SELECT
            COUNT(*) AS total_chunks,
            COUNT(DISTINCT paper_id) AS indexed_papers,
            SUM(CASE WHEN evidence_level = 'full_text' THEN 1 ELSE 0 END) AS full_text_chunks,
            SUM(CASE WHEN evidence_level = 'abstract_only' THEN 1 ELSE 0 END) AS abstract_chunks,
            SUM(CASE WHEN embedding_json <> '' THEN 1 ELSE 0 END) AS embedded_chunks,
            COUNT(DISTINCT CASE WHEN embedding_json <> '' THEN embedding_model END) AS embedding_models,
            MIN(CASE WHEN embedding_json <> '' THEN embedding_model END) AS embedding_model,
            COUNT(DISTINCT CASE WHEN embedding_json <> '' THEN embedding_dimensions END) AS embedding_dimension_counts,
            MIN(CASE WHEN embedding_json <> '' THEN embedding_dimensions END) AS embedding_dimensions,
            MAX(updated_at) AS latest_indexed_at
        FROM paper_chunks
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    indexed_ids = {
        str(row["paper_id"])
        for row in connection.execute(
            "SELECT DISTINCT paper_id FROM paper_chunks WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    }
    paper_ids = [str(row["id"]) for row in paper_rows]
    total_chunks = int(aggregate["total_chunks"] or 0)
    embedded_chunks = int(aggregate["embedded_chunks"] or 0)
    embedding_status = (
        "ready"
        if total_chunks and embedded_chunks == total_chunks
        else ("partial" if embedded_chunks else "not_started")
    )
    return {
        "project_id": project_id,
        "total_papers": len(paper_ids),
        "indexed_papers": int(aggregate["indexed_papers"] or 0),
        "total_chunks": total_chunks,
        "full_text_chunks": int(aggregate["full_text_chunks"] or 0),
        "abstract_chunks": int(aggregate["abstract_chunks"] or 0),
        "unindexed_paper_ids": [paper_id for paper_id in paper_ids if paper_id not in indexed_ids],
        "latest_indexed_at": str(aggregate["latest_indexed_at"] or ""),
        "index_version": RAG_INDEX_VERSION,
        "embedding_status": embedding_status,
        "embedded_chunks": embedded_chunks,
        "embedding_model": (
            str(aggregate["embedding_model"] or "")
            if int(aggregate["embedding_models"] or 0) <= 1
            else "mixed"
        ),
        "embedding_dimensions": (
            int(aggregate["embedding_dimensions"] or 0)
            if int(aggregate["embedding_dimension_counts"] or 0) <= 1
            else 0
        ),
    }


def normalize_source_text(value: Any) -> str:
    text = str(value or "").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_inline_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def estimate_token_count(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def chunk_checksum(*, source: str, section: str, page: int | None, text: str) -> str:
    payload = f"{source}\n{section}\n{page if page is not None else ''}\n{normalize_inline_text(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
