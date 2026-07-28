from __future__ import annotations

import json
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


FIXTURE_PORT = int(os.getenv("SCHOLARFLOW_FIXTURE_PORT", "18765"))
API_PORT = 18010
WORKER_HEALTH_PORT = 18011


def fixture_abstract(index: int) -> str:
    return (
        "This paper studies object hallucination in vision language models and "
        "evidence faithfulness for visual question answering. "
        f"Grounded Method {index} evaluates Dataset A against Baseline B using "
        "citation precision, hallucination rate, and controlled counterexamples. "
        "The analysis reports limitations and does not turn correlation into causation."
    )


def arxiv_feed() -> bytes:
    entries = []
    for index in range(1, 11):
        entries.append(
            f"""
  <entry>
    <id>http://arxiv.org/abs/2607.{index:05d}</id>
    <updated>2026-07-{index:02d}T00:00:00Z</updated>
    <published>2026-07-{index:02d}T00:00:00Z</published>
    <title>Evidence Grounded Object Hallucination Evaluation {index}</title>
    <summary>{fixture_abstract(index)}</summary>
    <author><name>Fixture Researcher {index}</name></author>
    <link href="https://example.test/papers/{index}" rel="alternate" type="text/html"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
"""
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\" "
        "xmlns:arxiv=\"http://arxiv.org/schemas/atom\">"
        + "".join(entries)
        + "</feed>"
    ).encode()


def inverted_abstract(text: str) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for position, word in enumerate(text.split()):
        result.setdefault(word, []).append(position)
    return result


def openalex_payload() -> bytes:
    results = []
    for index in range(1, 11):
        results.append(
            {
                "id": f"https://openalex.org/WFIXTURE{index}",
                "doi": f"https://doi.org/10.5555/fixture.{index}",
                "display_name": f"Evidence Grounded Object Hallucination Evaluation {index}",
                "publication_year": 2026,
                "authorships": [
                    {"author": {"display_name": f"Fixture Researcher {index}"}},
                ],
                "abstract_inverted_index": inverted_abstract(fixture_abstract(index)),
                "primary_location": {
                    "landing_page_url": f"https://example.test/papers/{index}",
                    "pdf_url": None,
                    "source": {"display_name": "Fixture Conference"},
                },
                "best_oa_location": None,
                "type": "article",
                "cited_by_count": 10 + index,
            }
        )
    return json.dumps({"results": results}).encode()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        path = urlparse(self.path).path
        if path == "/arxiv":
            payload = arxiv_feed()
            content_type = "application/atom+xml"
        elif path == "/openalex":
            payload = openalex_payload()
            content_type = "application/json"
        elif path == "/health":
            payload = b'{"status":"ok"}'
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class WorkerHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if urlparse(self.path).path != "/health":
            self.send_error(404)
            return
        payload = b'{"status":"ok","worker":"playwright-real-worker"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def patch_literature_sources() -> None:
    from scholarflow_api import literature

    literature.ARXIV_API_URL = f"http://127.0.0.1:{FIXTURE_PORT}/arxiv"
    literature.OPENALEX_WORKS_URL = f"http://127.0.0.1:{FIXTURE_PORT}/openalex"
    literature.REQUEST_CACHE.clear()


def serve_api() -> None:
    fixture_server = ThreadingHTTPServer(
        ("127.0.0.1", FIXTURE_PORT),
        FixtureHandler,
    )
    fixture_thread = threading.Thread(
        target=fixture_server.serve_forever,
        name="scholarflow-literature-fixture",
        daemon=True,
    )
    fixture_thread.start()
    patch_literature_sources()

    import uvicorn
    from scholarflow_api.main import app

    try:
        uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="warning")
    finally:
        fixture_server.shutdown()
        fixture_server.server_close()


def serve_worker() -> None:
    patch_literature_sources()
    health_server = ThreadingHTTPServer(
        ("127.0.0.1", WORKER_HEALTH_PORT),
        WorkerHealthHandler,
    )
    health_thread = threading.Thread(
        target=health_server.serve_forever,
        name="scholarflow-worker-health",
        daemon=True,
    )
    health_thread.start()

    from scholarflow_api.jobs.worker import main

    try:
        sys.argv = [sys.argv[0], "--poll-interval", "0.05"]
        main()
    finally:
        health_server.shutdown()
        health_server.server_close()


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"api", "worker"}:
        raise SystemExit("usage: real_backend_harness.py api|worker")
    if sys.argv[1] == "api":
        serve_api()
    else:
        serve_worker()


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
