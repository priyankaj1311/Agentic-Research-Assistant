from __future__ import annotations

from urllib.parse import urlparse

from app.config import settings
from app.services.llm import get_llm
from app.services.source_reader import compress_for_research, fetch_and_extract
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _is_excluded(url: str) -> bool:
    """Return True if the URL's domain matches any entry in SOURCE_EXCLUDE_DOMAINS."""
    if not settings.SOURCE_EXCLUDE_DOMAINS and not settings.SOURCE_INCLUDE_DOMAINS:
        return False
    try:
        host = urlparse(url).hostname or ""
        # Strip leading www.
        host = host.removeprefix("www.")
        if settings.SOURCE_INCLUDE_DOMAINS:
            allowed = any(host == d or host.endswith("." + d) for d in settings.SOURCE_INCLUDE_DOMAINS)
            return not allowed
        return any(host == d or host.endswith("." + d) for d in settings.SOURCE_EXCLUDE_DOMAINS)
    except Exception:
        return False


def read_url(url: str, research_question: str = "") -> str:
    """Fetch a URL (HTML or PDF), extract readable content, and compress it
    toward the research question.

    Architecture note
    -----------------
    This tool performs *question-focused compression*: a 50 000-character
    webpage is reduced to 2 000–4 000 characters of relevant information
    BEFORE being returned to the researcher agent.  Raw page content never
    enters the agent's conversation history.

    Args:
        url: The URL to fetch.
        research_question: The researcher's current sub-question, used to
            guide which parts of the page to extract.

    Returns:
        Compressed, relevant content from the page.
    """
    logger.info("Reading URL", url=url)

    if _is_excluded(url):
        logger.info("URL blocked by domain filter", url=url)
        return f"[Skipped — domain not permitted by source credibility filter: {url}]"

    raw = fetch_and_extract(url)
    if not raw:
        return f"Could not retrieve content from {url}."

    if len(raw) < 500:
        # Short page — return as-is, no need to compress
        return raw

    question = research_question or "general research"
    llm = get_llm("page_summarizer")
    compressed = compress_for_research(raw, question, url, llm)

    logger.info(
        "URL content compressed",
        url=url,
        raw_chars=len(raw),
        compressed_chars=len(compressed),
    )
    return compressed
