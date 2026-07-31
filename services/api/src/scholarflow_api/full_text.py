from __future__ import annotations

import io
import ipaddress
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

import certifi

from scholarflow_api.schemas import EvidenceQualification


# Direction Review fetches at most 10 papers. A 6-second per-file timeout with
# five workers keeps the added PDF phase to roughly two waves (< 15 seconds)
# under ordinary timeout behavior, below the web client's 30-second API budget.
PDF_TIMEOUT_SECONDS = float(os.getenv("SCHOLARFLOW_PDF_TIMEOUT_SECONDS", "6"))
PDF_MAX_BYTES = int(os.getenv("SCHOLARFLOW_PDF_MAX_BYTES", str(20 * 1024 * 1024)))
PDF_MAX_PAGES = int(os.getenv("SCHOLARFLOW_PDF_MAX_PAGES", "80"))
PDF_MAX_TEXT_CHARS = int(os.getenv("SCHOLARFLOW_PDF_MAX_TEXT_CHARS", "50000"))
PDF_MIN_TEXT_CHARS = int(os.getenv("SCHOLARFLOW_PDF_MIN_TEXT_CHARS", "1200"))
PDF_FETCH_WORKERS = max(1, min(6, int(os.getenv("SCHOLARFLOW_PDF_FETCH_WORKERS", "5"))))
PDF_MAX_REDIRECTS = 5
PDF_AUTO_FETCH_ENABLED = os.getenv("SCHOLARFLOW_AUTO_FETCH_PDF", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
VERIFIED_PDF_SOURCE_ORIGINS = frozenset(
    {
        "arxiv_pdf",
        "openalex_open_access_pdf",
        "open_access_pdf",
        "user_uploaded_pdf",
    },
)
BLOCKED_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("169.254.170.2"),
        ipaddress.ip_address("168.63.129.16"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


RESEARCH_PAGE_MARKERS = {
    "method": 5,
    "methodology": 5,
    "approach": 3,
    "architecture": 3,
    "algorithm": 3,
    "experiment": 5,
    "evaluation": 4,
    "dataset": 4,
    "benchmark": 4,
    "baseline": 4,
    "ablation": 6,
    "results": 3,
    "limitations": 5,
    "failure": 4,
    "conclusion": 2,
}

SECTION_HEADING_PATTERNS = [
    ("abstract", r"^(?:abstract)$"),
    ("introduction", r"^(?:\d+(?:\.\d+)*[\s.:-]*)?introduction$"),
    ("related_work", r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:related work|background|preliminaries)$"),
    (
        "method",
        r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:method|methods|methodology|approach|proposed method|framework|model architecture)$",
    ),
    (
        "experiments",
        r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:experiment|experiments|experimental setup|evaluation|evaluations)$",
    ),
    ("results", r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:result|results|analysis|ablation|ablation study)$"),
    ("limitations", r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:limitation|limitations|failure cases?|discussion)$"),
    ("conclusion", r"^(?:\d+(?:\.\d+)*[\s.:-]*)?(?:conclusion|conclusions|concluding remarks)$"),
    ("references", r"^(?:references|bibliography)$"),
]


@dataclass
class FullTextResult:
    status: str = ""
    pdf_url: str = ""
    source: str = ""
    page_count: int = 0
    character_count: int = 0
    error: str = ""
    failure_stage: str = ""
    recovery_hint: str = ""
    text: str = ""

    @property
    def is_extracted(self) -> bool:
        qualification = self.evidence_qualification()
        return qualification.level == "full_text" and qualification.verified

    def evidence_qualification(
        self,
        *,
        has_abstract: bool = False,
    ) -> EvidenceQualification:
        return qualify_full_text_result(self, has_abstract=has_abstract)

    def to_provenance(
        self,
        qualification: EvidenceQualification | None = None,
        *,
        has_abstract: bool = False,
    ) -> dict[str, Any]:
        qualification = qualification or self.evidence_qualification(
            has_abstract=has_abstract,
        )
        data = asdict(self)
        data.pop("text", None)
        data["page_numbers"] = extract_page_numbers(self.text)
        data["section_names"] = extract_section_names(self.text)
        data["evidence_qualification"] = qualification.model_dump()
        return data


def qualify_full_text_result(
    result: FullTextResult,
    *,
    has_abstract: bool = False,
) -> EvidenceQualification:
    normalized_text = normalize_extracted_text(result.text)
    actual_character_count = len(normalized_text)
    section_names = extract_section_names(normalized_text)
    source_origin = normalize_space(result.source)
    verified_pdf = (
        result.status == "extracted"
        and source_origin in VERIFIED_PDF_SOURCE_ORIGINS
        and result.page_count > 0
        and result.character_count >= PDF_MIN_TEXT_CHARS
        and actual_character_count >= PDF_MIN_TEXT_CHARS
    )
    if verified_pdf:
        return EvidenceQualification(
            level="full_text",
            verified=True,
            source_origin=source_origin,
            character_count=actual_character_count,
            page_count=result.page_count,
            section_names=section_names,
            reason="PDF 来源、解析状态、页数和有效文本量均通过统一检查。",
        )
    if source_origin == "user_provided" and normalized_text:
        return EvidenceQualification(
            level="supplemental_text",
            verified=False,
            source_origin=source_origin,
            character_count=actual_character_count,
            page_count=0,
            section_names=[],
            reason="用户补充文本未经过 PDF 解析、页码和来源验证。",
        )
    if has_abstract:
        return EvidenceQualification(
            level="abstract_only",
            verified=False,
            source_origin=source_origin or "metadata.abstract",
            character_count=0,
            page_count=0,
            section_names=[],
            reason="当前只有摘要可作为论文内容证据。",
        )
    return EvidenceQualification(
        level="metadata_only",
        verified=False,
        source_origin=source_origin or "metadata",
        character_count=0,
        page_count=0,
        section_names=[],
        reason="当前没有通过验证的摘要或 PDF 正文证据。",
    )


def qualify_supplemental_text(
    text: str,
    *,
    has_abstract: bool = False,
    source_origin: str = "user_provided",
) -> EvidenceQualification:
    normalized = normalize_extracted_text(text)
    if normalized:
        return EvidenceQualification(
            level="supplemental_text",
            verified=False,
            source_origin=source_origin,
            character_count=len(normalized),
            page_count=0,
            section_names=[],
            reason="用户补充文本未经过 PDF 解析、页码和来源验证。",
        )
    return qualify_full_text_result(
        FullTextResult(source=source_origin),
        has_abstract=has_abstract,
    )


def qualify_card_context(
    text: str,
    qualification: EvidenceQualification | None,
    *,
    has_abstract: bool = False,
) -> EvidenceQualification:
    normalized = normalize_extracted_text(text)
    if qualification and qualification.level == "full_text":
        checked = qualify_full_text_result(
            FullTextResult(
                status="extracted",
                source=qualification.source_origin,
                page_count=qualification.page_count,
                character_count=qualification.character_count,
                text=normalized,
            ),
            has_abstract=has_abstract,
        )
        if checked.level == "full_text" and checked.verified:
            return checked
    if normalized:
        return qualify_supplemental_text(
            normalized,
            has_abstract=has_abstract,
            source_origin=(
                qualification.source_origin
                if qualification and qualification.level == "supplemental_text"
                else "user_provided"
            ),
        )
    return qualify_full_text_result(
        FullTextResult(
            source=qualification.source_origin if qualification else "",
        ),
        has_abstract=has_abstract,
    )


def normalize_persisted_evidence_qualification(
    payload: object,
    provenance: object,
    *,
    has_abstract: bool = False,
) -> EvidenceQualification:
    raw = _as_mapping(payload)
    raw_provenance = _as_mapping(provenance)
    if not raw:
        return _legacy_qualification(has_abstract=has_abstract)

    level = normalize_space(str(raw.get("level") or "")).lower().replace("-", "_")
    verified = raw.get("verified") is True
    source_origin = normalize_space(str(raw.get("source_origin") or ""))
    character_count = _safe_nonnegative_int(raw.get("character_count"))
    page_count = _safe_nonnegative_int(raw.get("page_count"))
    section_names = [
        normalize_space(str(item))
        for item in raw.get("section_names", [])
        if normalize_space(str(item))
    ] if isinstance(raw.get("section_names"), list) else []
    reason = normalize_space(str(raw.get("reason") or ""))

    if level == "full_text":
        provenance_status = normalize_space(
            str(raw_provenance.get("status") or ""),
        )
        provenance_source = normalize_space(
            str(raw_provenance.get("source") or ""),
        )
        provenance_chars = _safe_nonnegative_int(
            raw_provenance.get("character_count"),
        )
        provenance_pages = _safe_nonnegative_int(raw_provenance.get("page_count"))
        valid = (
            verified
            and source_origin in VERIFIED_PDF_SOURCE_ORIGINS
            and provenance_status == "extracted"
            and provenance_source == source_origin
            and character_count >= PDF_MIN_TEXT_CHARS
            and provenance_chars >= PDF_MIN_TEXT_CHARS
            and character_count == provenance_chars
            and page_count > 0
            and provenance_pages > 0
            and page_count == provenance_pages
        )
        if valid:
            return EvidenceQualification(
                level="full_text",
                verified=True,
                source_origin=source_origin,
                character_count=character_count,
                page_count=page_count,
                section_names=section_names,
                reason=reason or "已持久化的 PDF 证据资格通过一致性检查。",
            )
        return _legacy_qualification(
            has_abstract=has_abstract,
            reason="全文资格字段不完整或与 provenance 冲突，已保守降级。",
        )

    if level == "supplemental_text":
        return EvidenceQualification(
            level="supplemental_text",
            verified=False,
            source_origin=source_origin or "user_provided",
            character_count=character_count,
            page_count=0,
            section_names=[],
            reason=reason or "用户补充文本未经过 PDF 验证。",
        )
    if level == "abstract_only":
        return EvidenceQualification(
            level="abstract_only",
            verified=False,
            source_origin=source_origin or "metadata.abstract",
            character_count=0,
            page_count=0,
            section_names=[],
            reason=reason or "当前只有摘要证据。",
        )
    return EvidenceQualification(
        level="metadata_only",
        verified=False,
        source_origin=source_origin or "metadata",
        character_count=0,
        page_count=0,
        section_names=[],
        reason=reason or "当前只有元数据证据。",
    )


def _legacy_qualification(
    *,
    has_abstract: bool,
    reason: str = "",
) -> EvidenceQualification:
    if has_abstract:
        return EvidenceQualification(
            level="abstract_only",
            verified=False,
            source_origin="metadata.abstract",
            reason=reason or "旧 Artifact 缺少 evidence_qualification，已保守降级为摘要级。",
        )
    return EvidenceQualification(
        level="metadata_only",
        verified=False,
        source_origin="metadata",
        reason=reason or "旧 Artifact 缺少 evidence_qualification，已保守降级为元数据级。",
    )


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, EvidenceQualification):
        return value.model_dump()
    return value if isinstance(value, Mapping) else {}


def _safe_nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class FullTextFetchError(RuntimeError):
    def __init__(
        self,
        status: str,
        message: str,
        *,
        failure_stage: str = "",
        recovery_hint: str = "",
    ) -> None:
        self.status = status
        self.failure_stage = failure_stage or ("parse" if status == "parse_failed" else "download")
        self.recovery_hint = recovery_hint or recovery_hint_for_stage(self.failure_stage)
        super().__init__(message)


def provided_full_text(text: str) -> FullTextResult:
    normalized = normalize_extracted_text(text)
    return FullTextResult(
        status="supplemental_text",
        source="user_provided",
        character_count=len(normalized),
        recovery_hint="如需全文级证据，请上传带可提取文本层的 PDF。",
        text=normalized,
    )


def resolve_open_full_text(paper: dict[str, Any]) -> FullTextResult:
    pdf_url = discover_pdf_url(paper)
    source = infer_pdf_source(paper, pdf_url)
    if not PDF_AUTO_FETCH_ENABLED:
        return FullTextResult(
            status="disabled",
            pdf_url=pdf_url,
            source=source,
            error="自动获取开放 PDF 已由 SCHOLARFLOW_AUTO_FETCH_PDF 关闭。",
            failure_stage="configuration",
            recovery_hint="开启 SCHOLARFLOW_AUTO_FETCH_PDF，或在 Paper Reader 中上传本地 PDF。",
        )
    if not pdf_url:
        return FullTextResult(
            status="not_available",
            source=source,
            error="检索元数据未提供可验证的开放 PDF URL。",
            failure_stage="discovery",
            recovery_hint="在 Paper Reader 中上传本地 PDF，或补充公开 PDF URL。",
        )

    try:
        payload = download_pdf_bytes(pdf_url)
    except FullTextFetchError as error:
        return FullTextResult(
            status=error.status,
            pdf_url=pdf_url,
            source=source,
            error=str(error),
            failure_stage=error.failure_stage,
            recovery_hint=error.recovery_hint,
        )

    return parse_pdf_bytes(payload, pdf_url=pdf_url, source=source)


def resolve_open_full_texts(papers: list[dict[str, Any]]) -> list[FullTextResult]:
    if not papers:
        return []
    if len(papers) == 1 or PDF_FETCH_WORKERS == 1:
        return [resolve_open_full_text(paper) for paper in papers]
    with ThreadPoolExecutor(max_workers=min(PDF_FETCH_WORKERS, len(papers))) as executor:
        return list(executor.map(resolve_open_full_text, papers))


def discover_pdf_url(paper: dict[str, Any]) -> str:
    explicit = normalize_space(paper.get("pdf_url", ""))
    if explicit:
        return explicit

    landing_url = normalize_space(paper.get("url", ""))
    parsed = urllib.parse.urlparse(landing_url)
    host = (parsed.hostname or "").lower()
    if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        identifier = arxiv_identifier_from_url(landing_url)
        if identifier:
            return f"https://arxiv.org/pdf/{identifier}.pdf"
    return ""


def arxiv_identifier_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip("/")
    match = re.match(r"(?:abs|pdf)/(.+?)(?:\.pdf)?$", path, flags=re.IGNORECASE)
    if not match:
        return ""
    identifier = match.group(1).strip("/")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", identifier):
        return ""
    return identifier


def infer_pdf_source(paper: dict[str, Any], pdf_url: str) -> str:
    source = normalize_space(paper.get("source", "")).lower()
    host = (urllib.parse.urlparse(pdf_url).hostname or "").lower()
    if source == "arxiv" or host.endswith("arxiv.org"):
        return "arxiv_pdf"
    if source == "openalex":
        return "openalex_open_access_pdf"
    return "open_access_pdf" if pdf_url else ""


def download_pdf_bytes(url: str) -> bytes:
    validate_public_http_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/pdf",
            "User-Agent": "ScholarFlow/0.1 (open-access paper reader)",
        },
    )
    try:
        # Use certifi's CA bundle explicitly. Some Python builds on macOS do not
        # discover the system trust store, which otherwise makes valid arXiv
        # certificates look untrusted. SSL verification remains enabled.
        context = trusted_ssl_context()
        opener = build_pdf_opener(context)
        with opener.open(request, timeout=PDF_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            # Defense in depth for custom transports. Redirect targets have
            # already been validated before the opener connects to them.
            validate_public_http_url(final_url)
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > PDF_MAX_BYTES:
                raise FullTextFetchError(
                    "download_failed",
                    f"开放 PDF 大小 {content_length} bytes，超过上限 {PDF_MAX_BYTES} bytes。",
                )
            payload = response.read(PDF_MAX_BYTES + 1)
    except FullTextFetchError:
        raise
    except ssl.SSLCertVerificationError as error:
        raise FullTextFetchError(
            "download_failed",
            f"开放 PDF TLS 证书验证失败：{error}",
            failure_stage="tls_verification",
            recovery_hint="检查系统时间与 certifi 安装，或在 Paper Reader 中上传本地 PDF；不要关闭 TLS 校验。",
        ) from error
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        message = str(error)
        if "CERTIFICATE_VERIFY_FAILED" in message.upper():
            message = f"TLS 证书验证失败：{message}"
        failure_stage = "tls_verification" if "TLS 证书验证失败" in message else "download"
        raise FullTextFetchError(
            "download_failed",
            f"开放 PDF 下载失败：{message}",
            failure_stage=failure_stage,
            recovery_hint=(
                "检查系统时间与 certifi 安装，或在 Paper Reader 中上传本地 PDF；不要关闭 TLS 校验。"
                if failure_stage == "tls_verification"
                else "稍后重试开放 PDF 下载，或在 Paper Reader 中上传本地 PDF。"
            ),
        ) from error

    if len(payload) > PDF_MAX_BYTES:
        raise FullTextFetchError("download_failed", f"开放 PDF 超过下载上限 {PDF_MAX_BYTES} bytes。")
    if not payload.lstrip().startswith(b"%PDF-"):
        raise FullTextFetchError("download_failed", "下载内容不是 PDF 文件（缺少 %PDF 文件头）。")
    return payload


def trusted_ssl_context() -> ssl.SSLContext:
    """Create a verifying TLS context from the maintained certifi CA bundle."""
    return ssl.create_default_context(cafile=certifi.where())


class PublicPdfRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate each redirect target before urllib opens the next connection."""

    def __init__(self, max_redirects: int = PDF_MAX_REDIRECTS) -> None:
        super().__init__()
        self.max_redirects = max(0, max_redirects)
        self.redirect_count = 0

    def redirect_request(
        self,
        request: urllib.request.Request,
        response: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> urllib.request.Request | None:
        target_url = urllib.parse.urljoin(request.full_url, new_url)
        validate_public_http_url(target_url)
        source_scheme = urllib.parse.urlparse(request.full_url).scheme.lower()
        target_scheme = urllib.parse.urlparse(target_url).scheme.lower()
        if source_scheme == "https" and target_scheme != "https":
            raise FullTextFetchError(
                "download_failed",
                "拒绝开放 PDF 从 HTTPS 重定向到不安全协议。",
            )
        if self.redirect_count >= self.max_redirects:
            raise FullTextFetchError(
                "download_failed",
                f"开放 PDF 重定向次数超过上限 {self.max_redirects}。",
            )
        self.redirect_count += 1
        return super().redirect_request(
            request,
            response,
            code,
            message,
            headers,
            target_url,
        )


def build_pdf_opener(context: ssl.SSLContext) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        PublicPdfRedirectHandler(),
    )


def recovery_hint_for_stage(stage: str) -> str:
    if stage == "parse":
        return "上传带可复制文本层的 PDF；扫描件需要先 OCR，再重新上传。"
    if stage == "tls_verification":
        return "检查系统时间与 certifi 安装，或上传本地 PDF；不要关闭 TLS 校验。"
    return "稍后重试开放 PDF 下载，或在 Paper Reader 中上传本地 PDF。"


def parse_pdf_bytes(payload: bytes, pdf_url: str = "", source: str = "user_uploaded_pdf") -> FullTextResult:
    if len(payload) > PDF_MAX_BYTES:
        return FullTextResult(
            status="parse_failed",
            pdf_url=pdf_url,
            source=source,
            error=f"PDF 超过解析上限 {PDF_MAX_BYTES} bytes。",
            failure_stage="parse",
            recovery_hint="上传不超过大小限制的 PDF，或仅提供论文正文文本。",
        )
    if not payload.lstrip().startswith(b"%PDF-"):
        return FullTextResult(
            status="parse_failed",
            pdf_url=pdf_url,
            source=source,
            error="上传内容不是 PDF 文件（缺少 %PDF 文件头）。",
            failure_stage="validation",
            recovery_hint="重新选择有效的 PDF 文件后上传。",
        )
    try:
        text, page_count = extract_research_text_from_pdf(payload)
    except FullTextFetchError as error:
        return FullTextResult(
            status=error.status,
            pdf_url=pdf_url,
            source=source,
            error=str(error),
            failure_stage=error.failure_stage,
            recovery_hint=error.recovery_hint,
        )

    character_count = len(text)
    if character_count < PDF_MIN_TEXT_CHARS:
        return FullTextResult(
            status="parse_failed",
            pdf_url=pdf_url,
            source=source,
            page_count=page_count,
            character_count=character_count,
            error=(
                f"PDF 仅提取到 {character_count} 个正文字符，低于全文证据阈值 {PDF_MIN_TEXT_CHARS}；"
                "可能是扫描件、加密文件或文本层缺失。"
            ),
            failure_stage="parse",
            recovery_hint="上传带可复制文本层的 PDF；扫描件需要先 OCR，再重新上传。",
        )
    return FullTextResult(
        status="extracted",
        pdf_url=pdf_url,
        source=source,
        page_count=page_count,
        character_count=character_count,
        text=text,
    )


def validate_public_http_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as error:
        raise FullTextFetchError(
            "download_failed",
            "PDF URL 格式无效。",
        ) from error
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise FullTextFetchError("download_failed", "PDF URL 必须是公开的 http/https 地址。")
    if parsed.username is not None or parsed.password is not None:
        raise FullTextFetchError("download_failed", "PDF URL 不得包含用户名或密码。")
    if port is not None and not 1 <= port <= 65535:
        raise FullTextFetchError("download_failed", "PDF URL 端口无效。")
    if host in {"localhost", "localhost.localdomain", "local"} or host.endswith(".local"):
        raise FullTextFetchError("download_failed", "拒绝访问本地 PDF 地址。")
    if "%" in host:
        raise FullTextFetchError("download_failed", "拒绝访问带作用域标识的 PDF 地址。")

    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        addresses = resolve_hostname_addresses(
            host,
            port or (443 if parsed.scheme.lower() == "https" else 80),
        )
    else:
        addresses = (address,)

    for address in addresses:
        if not is_public_ip_address(address):
            raise FullTextFetchError("download_failed", "拒绝访问解析到非公网地址的 PDF URL。")


def resolve_hostname_addresses(host: str, port: int) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        records = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, OSError) as error:
        raise FullTextFetchError(
            "download_failed",
            f"无法解析开放 PDF 域名：{host}。",
        ) from error

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for family, _socket_type, _protocol, _canonical_name, socket_address in records:
        if family not in {socket.AF_INET, socket.AF_INET6} or not socket_address:
            raise FullTextFetchError("download_failed", "PDF 域名返回了不支持的地址类型。")
        address_text = str(socket_address[0]).split("%", 1)[0]
        try:
            addresses.add(ipaddress.ip_address(address_text))
        except ValueError as error:
            raise FullTextFetchError(
                "download_failed",
                "PDF 域名返回了无效 IP 地址。",
            ) from error

    if not addresses:
        raise FullTextFetchError("download_failed", "PDF 域名没有可用的 A/AAAA 记录。")
    return tuple(sorted(addresses, key=lambda address: (address.version, int(address))))


def is_public_ip_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address in BLOCKED_METADATA_ADDRESSES:
        return False
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        return False
    if not address.is_global:
        return False
    return True


def extract_research_text_from_pdf(payload: bytes) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - exercised only in incomplete installations.
        raise FullTextFetchError(
            "parse_failed",
            "当前 API 环境未安装 pypdf，无法解析已下载的 PDF。请重新安装 services/api 依赖。",
        ) from error

    try:
        reader = PdfReader(io.BytesIO(payload), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as error:  # noqa: BLE001 - pypdf exposes backend-specific exceptions.
                raise FullTextFetchError("parse_failed", "PDF 已加密，无法提取正文。") from error
        pages: list[str] = []
        page_limit = min(len(reader.pages), PDF_MAX_PAGES)
        for page in reader.pages[:page_limit]:
            try:
                pages.append(normalize_extracted_page_text(page.extract_text() or ""))
            except Exception:  # noqa: BLE001 - preserve usable pages if one page is malformed.
                pages.append("")
    except FullTextFetchError:
        raise
    except Exception as error:  # noqa: BLE001 - convert parser failures into a truthful status.
        raise FullTextFetchError("parse_failed", f"PDF 文本解析失败：{error}") from error

    return select_research_text(pages, PDF_MAX_TEXT_CHARS), len(pages)


def select_research_text(pages: list[str], max_chars: int) -> str:
    cleaned_pages = remove_repeated_page_margins(pages)
    structured_pages = structure_pdf_pages(cleaned_pages)
    nonempty = [(index, text) for index, text in enumerate(structured_pages) if text]
    if not nonempty:
        return ""

    first_page_indexes = {index for index, _text in nonempty[:2]}
    ranked = sorted(
        nonempty,
        key=lambda item: (item[0] in first_page_indexes, research_page_score(item[1]), -item[0]),
        reverse=True,
    )
    selected: list[tuple[int, str]] = []
    used = 0
    for index, text in ranked:
        page_block = f"[PDF page {index + 1}]\n{text}"
        if used >= max_chars:
            break
        remaining = max_chars - used
        selected.append((index, page_block[:remaining]))
        used += min(len(page_block), remaining)
    selected.sort(key=lambda item: item[0])
    return normalize_extracted_text("\n\n".join(text for _index, text in selected))[:max_chars]


def remove_repeated_page_margins(pages: list[str]) -> list[str]:
    """Remove repeated headers/footers without flattening the page body."""
    line_counts: dict[str, int] = {}
    page_lines: list[list[str]] = []
    for page in pages:
        lines = [normalize_inline_space(line) for line in page.splitlines() if normalize_inline_space(line)]
        page_lines.append(lines)
        candidates = {*lines[:2], *lines[-2:]}
        for line in candidates:
            key = repeated_margin_key(line)
            if key:
                line_counts[key] = line_counts.get(key, 0) + 1

    threshold = max(2, (len([lines for lines in page_lines if lines]) + 1) // 2)
    repeated = {key for key, count in line_counts.items() if count >= threshold}
    output: list[str] = []
    for lines in page_lines:
        kept = [
            line
            for index, line in enumerate(lines)
            if not (
                (index < 2 or index >= max(0, len(lines) - 2))
                and repeated_margin_key(line) in repeated
            )
        ]
        output.append("\n".join(kept))
    return output


def repeated_margin_key(line: str) -> str:
    normalized = re.sub(r"\b\d+\b", "#", normalize_inline_space(line).lower())
    if len(normalized) < 4 or len(normalized) > 140:
        return ""
    return normalized


def structure_pdf_pages(pages: list[str]) -> list[str]:
    """Annotate page text with section markers and exclude the references tail."""
    output: list[str] = []
    current_section = "front_matter"
    references_started = False
    for page in pages:
        if references_started or not page:
            output.append("")
            continue
        blocks: list[str] = []
        buffer: list[str] = []
        for line in page.splitlines():
            heading = classify_section_heading(line)
            if heading:
                if buffer:
                    blocks.append(render_section_block(current_section, buffer))
                    buffer = []
                if heading == "references":
                    references_started = True
                    break
                current_section = heading
                continue
            buffer.append(line)
        if buffer and not references_started:
            blocks.append(render_section_block(current_section, buffer))
        output.append("\n".join(block for block in blocks if block))
    return output


def render_section_block(section: str, lines: list[str]) -> str:
    body = "\n".join(line for line in lines if line).strip()
    return f"[Section: {section}]\n{body}" if body else ""


def classify_section_heading(line: str) -> str:
    normalized = normalize_inline_space(line).strip(" .:-").lower()
    if not normalized or len(normalized) > 80:
        return ""
    for section, pattern in SECTION_HEADING_PATTERNS:
        if re.fullmatch(pattern, normalized, flags=re.IGNORECASE):
            return section
    return ""


def research_page_score(text: str) -> int:
    lower = text.lower()
    return sum(weight for marker, weight in RESEARCH_PAGE_MARKERS.items() if marker in lower)


def normalize_extracted_text(value: Any) -> str:
    text = str(value or "").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", text)
    lines = [normalize_inline_space(line) for line in text.splitlines()]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def normalize_extracted_page_text(value: Any) -> str:
    return normalize_extracted_text(value)


def normalize_inline_space(value: Any) -> str:
    return re.sub(r"[ \t\f\v]+", " ", str(value or "")).strip()


def extract_page_numbers(text: str) -> list[int]:
    return [int(value) for value in dict.fromkeys(re.findall(r"\[PDF page (\d+)\]", text))]


def extract_section_names(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\[Section: ([a-z_]+)\]", text)))


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
