from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scholarflow_api.database import utc_now
from scholarflow_api.literature import search_arxiv


LIVE_REPORT_VERSION = "rag_live_external_smoke.v1"


def run_live_external_smoke(
    *,
    query: str,
    max_results: int = 3,
) -> dict[str, Any]:
    base = {
        "report_schema_version": LIVE_REPORT_VERSION,
        "evaluation_tier": "live_external_smoke",
        "run_at": utc_now(),
        "query": query,
        "fixture_fallback_used": False,
        "metrics": None,
        "papers": [],
        "errors": [],
        "interpretation": (
            "该报告只检查当前外部 arXiv 连接和真实记录形状，"
            "不计算离线 benchmark 指标，也不代表科研答案准确。"
        ),
    }
    try:
        papers = search_arxiv(query, max_results=max_results)
    except Exception as error:  # External failures are report data, not fixture triggers.
        return {
            **base,
            "status": "blocked",
            "errors": [f"{type(error).__name__}: {error}"],
            "reason": "arXiv live request failed; no fixture replacement was used.",
        }
    records = [
        {
            "title": paper.title,
            "source": paper.source,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "arxiv_id": paper.arxiv_id,
        }
        for paper in papers
    ]
    if not records:
        return {
            **base,
            "status": "blocked",
            "papers": [],
            "reason": "arXiv returned no live records; no fixture replacement was used.",
        }
    incomplete = [
        item
        for item in records
        if item["source"] != "arxiv"
        or not item["url"]
        or not item["pdf_url"]
        or not item["arxiv_id"]
    ]
    return {
        **base,
        "status": "partial" if incomplete else "complete",
        "papers": records,
        "reason": (
            f"{len(incomplete)}/{len(records)} live records lacked a complete arXiv/PDF identity."
            if incomplete
            else f"Received {len(records)} live arXiv records with PDF identities."
        ),
    }


def render_live_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ScholarFlow RAG Live External Smoke",
        "",
        f"- Tier: `{report['evaluation_tier']}`",
        f"- Status: `{report['status']}`",
        f"- Query: `{report['query']}`",
        f"- Fixture fallback used: `{str(report['fixture_fallback_used']).lower()}`",
        "",
        "> " + report["interpretation"],
        "",
        str(report.get("reason") or ""),
    ]
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    if report.get("papers"):
        lines.extend(["", "## Live records", ""])
        lines.extend(
            f"- {paper['title']} — {paper['arxiv_id']} — {paper['pdf_url']}"
            for paper in report["papers"]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_live_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    resolved = output_dir.resolve()
    if not str(resolved).startswith("/private/tmp/"):
        raise ValueError("live smoke reports must be written under /private/tmp")
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "rag-live-external-smoke.json"
    markdown_path = resolved / "rag-live-external-smoke.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_live_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a live arXiv connectivity smoke separately from offline RAG evaluation."
    )
    parser.add_argument(
        "--query",
        default="evidence grounded retrieval augmented generation",
    )
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("/private/tmp/scholarflow-rag-live-smoke"),
    )
    args = parser.parse_args()
    report = run_live_external_smoke(
        query=args.query,
        max_results=max(1, min(args.max_results, 10)),
    )
    paths = write_live_report(report, args.report_dir)
    print(
        json.dumps(
            {
                "evaluation_tier": report["evaluation_tier"],
                "status": report["status"],
                "paper_count": len(report["papers"]),
                "fixture_fallback_used": report["fixture_fallback_used"],
                "reason": report["reason"],
                "report_json": str(paths["json"]),
                "report_markdown": str(paths["markdown"]),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
