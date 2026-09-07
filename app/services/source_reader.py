from __future__ import annotations

import io
from typing import Optional
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.logging import get_logger
from app.utils.retry import sync_retry

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _is_pdf(url: str, content_type: str) -> bool:
    return url.lower().endswith(".pdf") or "application/pdf" in content_type


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as exc:
        logger.warning("PDF extraction failed", error=str(exc))
        return ""


def _extract_html_text(html: str) -> str:
    text = trafilatura.extract(
        html,
        include_links=False,
        include_images=False,
        no_fallback=False,
    )
    if text:
        return text

    # Fallback to BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def fetch_and_extract(url: str) -> Optional[str]:
    """Fetch a URL and extract readable text. Returns None on failure."""

    def _do_fetch() -> Optional[str]:
        with httpx.Client(timeout=30, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if _is_pdf(url, content_type):
                return _extract_pdf_text(resp.content)
            return _extract_html_text(resp.text)

    try:
        return sync_retry(_do_fetch, max_retries=settings.MAX_RETRIES, base_delay=0.5, exceptions=(Exception,))
    except Exception as exc:
        logger.warning("Failed to fetch URL", url=url, error=str(exc))
        return None


def compress_for_research(
    raw_content: str,
    research_question: str,
    url: str,
    llm,  # LLM instance
) -> str:
    """Summarise raw webpage/PDF content focused on the research question.

    Returns 2000–4000 chars of relevant information — far less than the full page.
    """
    truncated = raw_content[: settings.MAX_CONTENT_LENGTH]

    prompt = (
        "You are extracting relevant information from a source for a research task.\n\n"
        f"Research question: {research_question}\n\n"
        f"Source URL: {url}\n\n"
        "Source content:\n"
        f"{truncated}\n\n"
        "Extract ONLY information relevant to the research question.\n"
        "Be concise (aim for 2000–4000 characters).\n"
        "Include specific facts, data points, and key claims.\n"
        "If you cite a specific claim, indicate it came from this source.\n"
        "Ignore irrelevant content.\n"
    )

    try:
        response = llm.complete(prompt)
        return str(response)
    except Exception as exc:
        logger.warning("Page compression LLM call failed", url=url, error=str(exc))
        # Return a hard-truncated fallback
        return raw_content[:4000]
