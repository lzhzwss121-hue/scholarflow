from __future__ import annotations

import io
import ipaddress
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

import certifi


# Direction Review fetches at most 10 papers. A 6-second per-file timeout with
# five workers keeps the added PDF phase to roughly two waves (< 15 seconds)
# under ordinary timeout behavior, below the web client's 30-second API budget.
PDF_TIMEOUT_SECONDS = float(os.getenv("SCHOLARFLOW_PDF_TIMEOUT_SECONDS", "6"))
PDF_MAX_BYTES = int(os.getenv("SCHOLARFLOW_PDF_MAX_BYTES", str(20 * 1024 * 1024)))
PDF_MAX_PAGES = int(os.getenv("SCHOLARFLOW_PDF_MAX_PAGES", "80"))
PDF_MAX_TEXT_CHARS = int(os.getenv("SCHOLARFLOW_PDF_MAX_TEXT_CHARS", "50000"))
PDF_MIN_TEXT_CHARS = int(os.getenv("SCHOLARFLOW_PDF_MIN_TEXT_CHARS", "1200"))
PDF_FETCH_WORKERS = max(1, min(6, int(os.getenv("SCHOLARFLOW_PDF_FETCH_WORKERS", "5"))))
PDF_AUTO_FETCH_ENABLED = os.getenv("SCHOLARFLOW_AUTO_FETCH_PDF", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


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
    status: str
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
        return self.status == "extracted" and self.character_count >= PDF_MIN_TEXT_CHARS and bool(self.text)

    def to_provenance(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("text", None)
        data["page_numbers"] = extract_page_numbers(self.text)
        data["section_names"] = extract_section_names(self.text)
        return data


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
        status="extracted",
        source="user_provided",
        character_count=len(normalized),
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
        with urllib.request.urlopen(
            request,
            timeout=PDF_TIMEOUT_SECONDS,
            context=trusted_ssl_context(),
        ) as response:
            final_url = response.geturl()
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
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FullTextFetchError("download_failed", "PDF URL 必须是公开的 http/https 地址。")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise FullTextFetchError("download_failed", "拒绝访问本地 PDF 地址。")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if not address.is_global:
        raise FullTextFetchError("download_failed", "拒绝访问非公网 PDF 地址。")


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
