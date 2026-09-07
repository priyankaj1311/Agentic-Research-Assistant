from __future__ import annotations

import asyncio
import time
import uuid
from typing import List

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool

from app.config import settings
from app.models.state import ResearchNote
from app.services.llm import get_llm
from app.tools.read_url import read_url
from app.tools.tavily_search import search_web
from app.tools.think import reflect
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── System prompt template ────────────────────────────────────────────────────

_RESEARCHER_SYSTEM_PROMPT = """\
You are a focused, autonomous research agent.

Your assignment: {subtopic}

Research context:
{research_brief}

──────────────────────────────────────────────────────────────────────────────
SOURCE QUALITY GUIDANCE
──────────────────────────────────────────────────────────────────────────────
Prefer high-credibility sources. In descending order of preference:
1. Academic / peer-reviewed papers (arxiv, journals, university publications)
2. Established news organisations (Reuters, FT, WSJ, Bloomberg, BBC)
3. Major consulting / research reports (McKinsey, PwC, Deloitte, Gartner, BCG)
4. Official regulatory or government publications
5. Industry analysts and established trade press
6. Company official press releases or investor relations pages

Treat personal blogs, social media, and vendor marketing pages as secondary
sources only — use them to find leads, not as primary evidence.
──────────────────────────────────────────────────────────────────────────────
HOW TO WORK
──────────────────────────────────────────────────────────────────────────────
1. Use search_web to find relevant sources.
2. Evaluate the search results — choose the most promising URLs.
3. Use read_url to read a specific source in depth.
   Always pass your subtopic as the research_question argument.
4. Use reflect to organise what you have learned and decide what to do next.
5. Repeat steps 1–4 until you have sufficient evidence.
6. When ready, write your FINAL ANSWER.

──────────────────────────────────────────────────────────────────────────────
FINAL ANSWER FORMAT (mandatory)
──────────────────────────────────────────────────────────────────────────────
Your final answer MUST be a markdown research summary that:
- Addresses the subtopic thoroughly
- Includes inline citations in format [Source Name](https://actual-url.com)
- Only cites URLs you actually retrieved during this research session
- Is 300–800 words
- Contains specific facts, data, and key claims

Do NOT invent URLs. Only cite sources you visited.
──────────────────────────────────────────────────────────────────────────────
"""

# ── Compression prompt ────────────────────────────────────────────────────────

_COMPRESS_PROMPT = """\
You are compressing a research agent's final answer into a concise, cited summary.

Subtopic: {subtopic}

Agent answer:
{agent_answer}

Produce a research summary (400–800 words) that:
1. Captures the key findings with specific detail
2. Preserves ALL inline citations exactly as written ([Source](URL))
3. Retains ALL numerical data, percentages, statistics, monetary figures, and
   named organisations — do not generalise or drop specific numbers
4. Removes redundancy and filler prose
5. Is suitable for passing to a senior analyst who will synthesise multiple such summaries

Return ONLY the summary — no preamble.
"""


async def run_researcher(
    subtopic: str,
    research_brief: str,
    visited_urls: frozenset = frozenset(),
) -> ResearchNote:
    """Run one isolated sub-researcher for *subtopic*.

    Context isolation guarantee
    ---------------------------
    All search results, webpage content, tool call histories, and intermediate
    reasoning produced inside this function are local to this coroutine's
    scope.  Only the compressed cited summary is returned to the caller.
    """
    researcher_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()
    searches_count = 0
    sources_count = 0

    logger.info(
        "Researcher started",
        researcher_id=researcher_id,
        subtopic=subtopic[:80],
    )

    # ── Build researcher-scoped tool closures ─────────────────────────────────
    # Each closure captures private counters — nothing leaks outside.

    def _search(query: str) -> str:
        nonlocal searches_count
        searches_count += 1
        return search_web(query)

    def _read(url: str, research_question: str = "") -> str:
        nonlocal sources_count
        if url in visited_urls:
            return f"[Skipped — already researched in a previous round: {url}]"
        sources_count += 1
        q = research_question or subtopic
        return read_url(url, research_question=q)

    tools = [
        FunctionTool.from_defaults(
            fn=_search,
            name="search_web",
            description=(
                "Search the web for information. Returns numbered results with "
                "title, URL, and a brief snippet.  Call this first."
            ),
        ),
        FunctionTool.from_defaults(
            fn=_read,
            name="read_url",
            description=(
                "Read a specific URL and extract information relevant to the "
                "research question.  Pass the URL and your current subtopic as "
                "research_question."
            ),
        ),
        FunctionTool.from_defaults(
            fn=reflect,
            name="reflect",
            description=(
                "Pause to organise your findings and decide your next action. "
                "Call this after gathering some evidence."
            ),
        ),
    ]

    # ── Create isolated FunctionAgent ────────────────────────────────────────
    llm = get_llm("researcher")
    system_prompt = _RESEARCHER_SYSTEM_PROMPT.format(
        subtopic=subtopic,
        research_brief=research_brief,
    )

    agent = FunctionAgent(
        tools=tools,
        llm=llm,
        system_prompt=system_prompt,
        verbose=False,
    )

    # ── Run the agentic loop ──────────────────────────────────────────────────
    initial_message = (
        f"Research this topic thoroughly and produce a cited markdown summary:\n\n"
        f"{subtopic}"
    )

    status = "completed"
    summary = ""
    try:
        response = await agent.run(
            initial_message,
            max_iterations=settings.MAX_RESEARCHER_STEPS,
        )
        raw_answer = str(response)

        # ── Compress: keep summary short, preserve citations ──────────────────
        # This is the final compression step before the summary leaves the
        # researcher's isolated context.
        compress_llm = get_llm("page_summarizer")
        compress_prompt = _COMPRESS_PROMPT.format(
            subtopic=subtopic,
            agent_answer=raw_answer,
        )
        compressed = compress_llm.complete(compress_prompt)
        summary = str(compressed).strip()

        if not summary:
            summary = raw_answer[:2000]

    except Exception as exc:
        logger.error(
            "Researcher failed",
            researcher_id=researcher_id,
            subtopic=subtopic[:80],
            error=str(exc),
        )
        summary = f"Research failed for '{subtopic}': {exc}"
        status = "failed"

    elapsed = time.monotonic() - start_time

    logger.info(
        "Researcher completed",
        researcher_id=researcher_id,
        subtopic=subtopic[:80],
        searches=searches_count,
        sources=sources_count,
        elapsed_secs=round(elapsed, 1),
        status=status,
        summary_chars=len(summary),
    )

    # ── Return ONLY the compressed cited summary ──────────────────────────────
    # Everything else (agent memory, tool results, page content) is now out of
    # scope and will be garbage-collected.
    return ResearchNote(
        researcher_id=researcher_id,
        subtopic=subtopic,
        summary=summary,
        sources_count=sources_count,
        searches_count=searches_count,
        elapsed_time=elapsed,
        status=status,
    )
