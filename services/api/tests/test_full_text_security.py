from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import urllib.parse
import urllib.request
import unittest
from unittest.mock import patch

from scholarflow_api import full_text


PUBLIC_HOST = "public-pdf.example"
PUBLIC_IPV4 = "93.184.216.34"
PUBLIC_IPV6 = "2606:2800:220:1:248:1893:25c8:1946"


def dns_record(address: str, port: int) -> tuple:
    parsed = full_text.ipaddress.ip_address(address)
    family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
    socket_address = (address, port, 0, 0) if parsed.version == 6 else (address, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", socket_address)


@contextmanager
def public_fixture_dns():
    original_getaddrinfo = socket.getaddrinfo

    def resolve(host: str, port: int, *args, **kwargs):
        if host.rstrip(".").lower() == PUBLIC_HOST:
            return [
                dns_record(PUBLIC_IPV4, port),
                dns_record(PUBLIC_IPV6, port),
            ]
        return original_getaddrinfo(host, port, *args, **kwargs)

    with patch.object(full_text.socket, "getaddrinfo", side_effect=resolve):
        yield


@contextmanager
def local_http_server(handler_type: type[BaseHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def quiet_handler() -> type[BaseHTTPRequestHandler]:
    class QuietHandler(BaseHTTPRequestHandler):
        requests: list[str] = []

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract.
            type(self).requests.append(self.path)
            payload = b"metadata should never be reached"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args) -> None:
            return

    return QuietHandler


def proxy_handler(
    *,
    private_redirect_url: str = "",
    oversized_bytes: int = 0,
) -> type[BaseHTTPRequestHandler]:
    class FixtureProxyHandler(BaseHTTPRequestHandler):
        requests: list[str] = []

        def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract.
            type(self).requests.append(self.path)
            target = urllib.parse.urlparse(self.path)
            path = target.path
            if path == "/redirect-private":
                self.send_response(302)
                self.send_header("Location", private_redirect_url)
                self.end_headers()
                return
            if path.startswith("/redirect/"):
                redirect_number = int(path.rsplit("/", 1)[-1])
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://{PUBLIC_HOST}/redirect/{redirect_number + 1}",
                )
                self.end_headers()
                return
            if path == "/not-pdf":
                payload = b"<html>not a PDF</html>"
            elif path == "/oversized":
                payload = b"%PDF-" + (b"x" * oversized_bytes)
            else:
                payload = b"%PDF-1.7\nfixture"
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args) -> None:
            return

    return FixtureProxyHandler


@contextmanager
def proxy_transport(proxy_url: str):
    with public_fixture_dns(), patch.object(
        full_text.urllib.request,
        "getproxies",
        return_value={"http": proxy_url},
    ), patch.object(
        full_text.urllib.request,
        "proxy_bypass",
        return_value=False,
    ):
        yield


class FullTextUrlSecurityTest(unittest.TestCase):
    def test_direct_non_public_ip_addresses_are_rejected(self) -> None:
        blocked_urls = [
            "http://127.0.0.1/paper.pdf",
            "http://[::1]/paper.pdf",
            "http://192.168.1.10/paper.pdf",
            "http://10.1.2.3/paper.pdf",
            "http://172.16.10.20/paper.pdf",
            "http://169.254.1.5/paper.pdf",
            "http://169.254.169.254/latest/meta-data",
            "http://0.0.0.0/paper.pdf",
            "http://224.0.0.1/paper.pdf",
            "http://240.0.0.1/paper.pdf",
            "http://[::ffff:192.168.1.10]/paper.pdf",
        ]

        for url in blocked_urls:
            with self.subTest(url=url), self.assertRaises(full_text.FullTextFetchError):
                full_text.validate_public_http_url(url)

    def test_url_rejects_credentials_local_names_and_non_http_schemes(self) -> None:
        blocked_urls = [
            "https://user@example.com/paper.pdf",
            "https://user:secret@example.com/paper.pdf",
            "http://localhost/paper.pdf",
            "http://host.local/paper.pdf",
            "file:///private/tmp/paper.pdf",
            "ftp://example.com/paper.pdf",
        ]

        for url in blocked_urls:
            with self.subTest(url=url), self.assertRaises(full_text.FullTextFetchError):
                full_text.validate_public_http_url(url)

    def test_hostname_resolving_to_private_ip_is_rejected(self) -> None:
        private_dns = [dns_record("10.20.30.40", 443)]
        with patch.object(full_text.socket, "getaddrinfo", return_value=private_dns):
            with self.assertRaisesRegex(full_text.FullTextFetchError, "非公网"):
                full_text.validate_public_http_url(f"https://{PUBLIC_HOST}/paper.pdf")

    def test_mixed_public_and_private_dns_results_are_rejected(self) -> None:
        mixed_dns = [
            dns_record(PUBLIC_IPV4, 443),
            dns_record("192.168.50.2", 443),
        ]
        with patch.object(full_text.socket, "getaddrinfo", return_value=mixed_dns):
            with self.assertRaisesRegex(full_text.FullTextFetchError, "非公网"):
                full_text.validate_public_http_url(f"https://{PUBLIC_HOST}/paper.pdf")

    def test_public_ipv4_and_ipv6_dns_results_are_allowed(self) -> None:
        with public_fixture_dns():
            full_text.validate_public_http_url(f"https://{PUBLIC_HOST}/paper.pdf")

    def test_redirect_to_localhost_is_rejected_before_internal_handler(self) -> None:
        internal_handler = quiet_handler()
        with local_http_server(internal_handler) as internal_server:
            internal_url = (
                f"http://127.0.0.1:{internal_server.server_port}/latest/meta-data"
            )
            outer_handler = proxy_handler(private_redirect_url=internal_url)
            with local_http_server(outer_handler) as proxy_server, proxy_transport(
                f"http://127.0.0.1:{proxy_server.server_port}"
            ):
                with self.assertRaisesRegex(full_text.FullTextFetchError, "非公网"):
                    full_text.download_pdf_bytes(
                        f"http://{PUBLIC_HOST}/redirect-private"
                    )

        self.assertEqual(len(outer_handler.requests), 1)
        self.assertEqual(internal_handler.requests, [])

    def test_redirect_limit_is_enforced_before_next_request(self) -> None:
        handler = proxy_handler()
        with local_http_server(handler) as proxy_server, proxy_transport(
            f"http://127.0.0.1:{proxy_server.server_port}"
        ):
            with self.assertRaisesRegex(full_text.FullTextFetchError, "重定向次数超过"):
                full_text.download_pdf_bytes(f"http://{PUBLIC_HOST}/redirect/0")

        self.assertEqual(len(handler.requests), full_text.PDF_MAX_REDIRECTS + 1)

    def test_https_redirect_cannot_downgrade_to_http(self) -> None:
        handler = full_text.PublicPdfRedirectHandler()
        with public_fixture_dns(), self.assertRaisesRegex(
            full_text.FullTextFetchError,
            "HTTPS",
        ):
            handler.redirect_request(
                urllib.request.Request(f"https://{PUBLIC_HOST}/paper.pdf"),
                None,
                302,
                "Found",
                {},
                f"http://{PUBLIC_HOST}/paper.pdf",
            )

    def test_redirect_rejects_non_http_location(self) -> None:
        handler = full_text.PublicPdfRedirectHandler()
        with self.assertRaisesRegex(full_text.FullTextFetchError, "http/https"):
            handler.redirect_request(
                urllib.request.Request(f"http://{PUBLIC_HOST}/paper.pdf"),
                None,
                302,
                "Found",
                {},
                "file:///private/tmp/paper.pdf",
            )

    def test_normal_public_pdf_fixture_can_be_downloaded(self) -> None:
        handler = proxy_handler()
        with local_http_server(handler) as proxy_server, proxy_transport(
            f"http://127.0.0.1:{proxy_server.server_port}"
        ):
            payload = full_text.download_pdf_bytes(
                f"http://{PUBLIC_HOST}/paper.pdf"
            )

        self.assertEqual(payload, b"%PDF-1.7\nfixture")
        self.assertEqual(len(handler.requests), 1)

    def test_non_pdf_content_is_still_rejected(self) -> None:
        handler = proxy_handler()
        with local_http_server(handler) as proxy_server, proxy_transport(
            f"http://127.0.0.1:{proxy_server.server_port}"
        ):
            with self.assertRaisesRegex(full_text.FullTextFetchError, "不是 PDF"):
                full_text.download_pdf_bytes(f"http://{PUBLIC_HOST}/not-pdf")

    def test_oversized_pdf_is_still_rejected(self) -> None:
        handler = proxy_handler(oversized_bytes=64)
        with patch.object(full_text, "PDF_MAX_BYTES", 16), local_http_server(
            handler
        ) as proxy_server, proxy_transport(
            f"http://127.0.0.1:{proxy_server.server_port}"
        ):
            with self.assertRaisesRegex(full_text.FullTextFetchError, "超过上限"):
                full_text.download_pdf_bytes(f"http://{PUBLIC_HOST}/oversized")


if __name__ == "__main__":
    unittest.main()
