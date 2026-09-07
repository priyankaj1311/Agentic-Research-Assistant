from __future__ import annotations

from typing import List

from tavily import TavilyClient

from app.config import settings
from app.utils.logging import get_logger
from app.utils.retry import sync_retry

logger = get_logger(__name__)

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return _client


def search_web(query: str, max_results: int | None = None) -> str:
    """Search the web using Tavily.

    Returns a formatted string listing title, URL, and a brief snippet for
    each result — ready for the researcher agent to read and decide which
    sources to explore further.

    Args:
        query: Search query.
        max_results: Override for maximum results (uses config default).

    Returns:
        Formatted search results string.
    """
    n = max_results or settings.MAX_SEARCH_RESULTS

    def _do_search() -> list:
        client = _get_client()
        kwargs: dict = dict(
            query=query,
            max_results=n,
            include_raw_content=False,
            include_answer=False,
        )
        if settings.SOURCE_EXCLUDE_DOMAINS:
            kwargs["exclude_domains"] = settings.SOURCE_EXCLUDE_DOMAINS
        if settings.SOURCE_INCLUDE_DOMAINS:
            kwargs["include_domains"] = settings.SOURCE_INCLUDE_DOMAINS
        resp = client.search(**kwargs)
        return resp.get("results", [])

    try:
        results: List[dict] = sync_retry(
            _do_search,
            max_retries=settings.MAX_RETRIES,
            base_delay=1.0,
            exceptions=(Exception,),
        )
    except Exception as exc:
        logger.error("Tavily search failed", query=query[:80], error=str(exc))
        return f"Search failed: {exc}"

    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = (r.get("content") or r.get("snippet") or "")[:300]
        lines.append(f"{i}. [{title}]({url})\n   {snippet}")

    logger.info("Search completed", query=query[:80], results=len(results))
    return "\n\n".join(lines)
