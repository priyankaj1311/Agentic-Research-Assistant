from __future__ import annotations

import asyncio
from typing import List, Optional

from app.config import settings
from app.models.state import ResearchNote, ResearchState
from app.workflow.researcher import run_researcher
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def run_parallel_researchers(
    subtopics: List[str],
    research_brief: str,
    state: ResearchState,
    visited_urls: frozenset = frozenset(),
) -> List[ResearchNote]:
    """Launch up to MAX_CONCURRENT_RESEARCHERS researchers in parallel.

    - Uses a semaphore to cap concurrency.
    - A failed researcher logs an error but does NOT terminate the run.
    - Returns only the completed ResearchNote objects (compressed summaries).
    """
    if not subtopics:
        return []

    sem = asyncio.Semaphore(settings.MAX_CONCURRENT_RESEARCHERS)

    async def _bounded(subtopic: str) -> Optional[ResearchNote]:
        async with sem:
            try:
                return await run_researcher(subtopic, research_brief, visited_urls)
            except Exception as exc:
                logger.error(
                    "Researcher raised unhandled exception",
                    subtopic=subtopic[:80],
                    error=str(exc),
                )
                return ResearchNote(
                    researcher_id="failed",
                    subtopic=subtopic,
                    summary=f"[Research failed for this subtopic: {exc}]",
                    status="failed",
                )

    tasks = [_bounded(st) for st in subtopics]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    notes: List[ResearchNote] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error("gather() caught exception", error=str(result))
        elif result is not None:
            notes.append(result)

    successful = sum(1 for n in notes if n.status == "completed")
    logger.info(
        "Parallel research round complete",
        total=len(subtopics),
        successful=successful,
        failed=len(notes) - successful,
    )
    return notes
