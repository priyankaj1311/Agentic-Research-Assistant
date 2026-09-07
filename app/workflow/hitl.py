from __future__ import annotations

import asyncio
import sys
from typing import List, Tuple

from app.models.state import ResearchNote
from app.services.citation import extract_urls_from_markdown
from app.services.llm import get_llm
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SEP = "═" * 70

_RECOMPRESS_PROMPT = """\
You are editing a research summary to remove specific sources.

Original summary:
{summary}

Remove ALL content attributed to these sources:
{excluded_list}

Rules:
- Remove all inline citations to these URLs (e.g. [Name](url))
- Remove any facts, statistics, or claims that are ONLY sourced from these
  URLs (if the same fact is also supported by a remaining source, keep it
  with the remaining citation)
- Preserve all other content and citations exactly as written

Return ONLY the revised summary. If nothing remains after removal, return:
[No content remaining after source exclusion]
"""


async def _readline(prompt: str = "") -> str:
    """Read one line from stdin without blocking the event loop."""
    if prompt:
        print(prompt, end="", flush=True)
    return await asyncio.to_thread(sys.stdin.readline)


# ── Plan review ───────────────────────────────────────────────────────────────

async def review_plan_hitl(subtopics: List[str]) -> List[str]:
    """Pause and let the user review and edit the research plan.

    Returns the approved (possibly modified) list of subtopics.
    """
    subtopics = list(subtopics)

    while True:
        print(f"\n{_SEP}")
        print("  RESEARCH PLAN REVIEW")
        print(_SEP)
        print(f"  {len(subtopics)} subtopic(s) will be researched in parallel:\n")
        for i, t in enumerate(subtopics, 1):
            print(f"  {i:>3}  {t}")
        print()
        print("  Commands:  [Enter]=approve   add   edit <n>   remove <n>")
        print()

        raw = (await _readline("> ")).strip()

        if not raw:
            break

        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "add":
            text = (await _readline("  New subtopic: ")).strip()
            if text:
                subtopics.append(text)
                print(f"  Added: {text}")

        elif cmd == "edit":
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(subtopics):
                    text = (await _readline(f"  Replace [{idx + 1}] with: ")).strip()
                    if text:
                        subtopics[idx] = text
                        print(f"  Subtopic {idx + 1} updated.")
                else:
                    print(f"  Invalid index. Choose 1–{len(subtopics)}.")
            except ValueError:
                print("  Usage: edit <number>")

        elif cmd == "remove":
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(subtopics):
                    removed = subtopics.pop(idx)
                    print(f"  Removed: {removed}")
                    if not subtopics:
                        print("  Warning: no subtopics left — adding a default.")
                        subtopics.append("General overview of the research question")
                else:
                    print(f"  Invalid index. Choose 1–{len(subtopics)}.")
            except ValueError:
                print("  Usage: remove <number>")

        else:
            print(f"  Unknown command '{raw}'. Try: add  edit <n>  remove <n>")

    logger.info("Plan approved by user", subtopics=subtopics)
    return subtopics


# ── Source review ─────────────────────────────────────────────────────────────

async def review_sources_hitl(
    notes: List[ResearchNote],
    round_num: int,
    max_rounds: int,
) -> Tuple[List[str], bool]:
    """Pause and let the user review cited sources before synthesis.

    Returns:
        (excluded_urls, force_write)
        - excluded_urls: list of URLs the user wants removed
        - force_write: True if the user typed 'write' to bypass re-assessment
    """
    # Build deduplicated URL list with subtopic cross-references
    url_subtopics: dict[str, list[str]] = {}
    for note in notes:
        for url in extract_urls_from_markdown(note.summary):
            if url not in url_subtopics:
                url_subtopics[url] = []
            label = note.subtopic[:55] + ("…" if len(note.subtopic) > 55 else "")
            if label not in url_subtopics[url]:
                url_subtopics[url].append(label)

    all_urls = list(url_subtopics.keys())

    print(f"\n{_SEP}")
    print(
        f"  SOURCE REVIEW  (round {round_num} of {max_rounds})"
        f"  —  {len(all_urls)} source(s) from {len(notes)} research note(s)"
    )
    print(_SEP)

    if round_num >= max_rounds:
        print()
        print("  ! Final source-review round. After this the report is generated")
        print("    automatically with the remaining sources.")

    if not all_urls:
        print("\n  No cited URLs found in research notes.")
        _ = await _readline("\n  Press Enter to continue > ")
        return [], False

    print()
    for i, url in enumerate(all_urls, 1):
        print(f"  {i:>3}  {url}")
        refs = " · ".join(url_subtopics[url])
        print(f"         → {refs}")

    print()
    print("  Commands:  [Enter]=approve all   exclude <n,n,...>   write=force synthesis now")
    print()

    excluded_urls: List[str] = []

    while True:
        raw = (await _readline("> ")).strip()

        if not raw:
            break

        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "write":
            logger.info("User forced synthesis", excluded_count=len(excluded_urls))
            return excluded_urls, True

        elif cmd == "exclude":
            try:
                indices = [int(x.strip()) - 1 for x in arg.split(",") if x.strip()]
                for idx in indices:
                    if 0 <= idx < len(all_urls):
                        url = all_urls[idx]
                        if url not in excluded_urls:
                            excluded_urls.append(url)
                            print(f"  Excluded [{idx + 1}]: {url}")
                        else:
                            print(f"  Already excluded [{idx + 1}].")
                    else:
                        print(f"  Invalid index {idx + 1}. Choose 1–{len(all_urls)}.")
                print()
            except ValueError:
                print("  Usage: exclude <n,n,...>  e.g.  exclude 2,5,7")

        else:
            print(f"  Unknown command '{raw}'. Try: exclude <n,...>  write")

    if excluded_urls:
        logger.info("Sources excluded by user", count=len(excluded_urls))
    else:
        logger.info("All sources approved by user")

    return excluded_urls, False


# ── Note re-compression ───────────────────────────────────────────────────────

async def recompress_without_sources(
    notes: List[ResearchNote],
    excluded_urls: List[str],
) -> List[ResearchNote]:
    """Re-compress notes that cite excluded URLs to genuinely remove their content.

    Notes with no overlap are returned unchanged. For each affected note, a
    single page_summarizer LLM call produces a new summary that strips all
    content attributed to the excluded sources.
    """
    if not excluded_urls:
        return notes

    excluded_set = set(excluded_urls)
    llm = get_llm("page_summarizer")
    result: List[ResearchNote] = []

    for note in notes:
        cited = set(extract_urls_from_markdown(note.summary))
        overlap = cited & excluded_set

        if not overlap:
            result.append(note)
            continue

        excluded_list = "\n".join(f"  - {u}" for u in overlap)
        prompt = _RECOMPRESS_PROMPT.format(
            summary=note.summary,
            excluded_list=excluded_list,
        )

        try:
            response = await llm.acomplete(prompt)
            new_summary = str(response).strip() or note.summary
        except Exception as exc:
            logger.warning(
                "Re-compression failed, keeping original summary",
                subtopic=note.subtopic[:60],
                error=str(exc),
            )
            new_summary = note.summary

        logger.info(
            "Note re-compressed after source exclusion",
            subtopic=note.subtopic[:60],
            excluded_count=len(overlap),
            before_chars=len(note.summary),
            after_chars=len(new_summary),
        )

        result.append(note.model_copy(update={"summary": new_summary}))

    return result
