from __future__ import annotations

import re
from typing import List


_CITATION_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")


def extract_urls_from_markdown(text: str) -> List[str]:
    """Return all URLs embedded as markdown inline citations in *text*."""
    return [url for _, url in _CITATION_PATTERN.findall(text)]


def count_citations(text: str) -> int:
    return len(_CITATION_PATTERN.findall(text))


def citations_survived(source_text: str, final_report: str) -> bool:
    """Return True if at least one URL from *source_text* appears in *final_report*."""
    urls = extract_urls_from_markdown(source_text)
    if not urls:
        return False
    return any(url in final_report for url in urls)
