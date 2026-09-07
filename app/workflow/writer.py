from __future__ import annotations

from typing import List

from app.models.state import ResearchNote
from app.services.llm import get_llm

_WRITER_PROMPT = """\
You are a senior research analyst producing a formal research report.

You have been given:
1. A research brief describing the investigation scope
2. A collection of cited research summaries from specialist researchers

Your task: synthesise these into one structured, professional Markdown report.

──────────────────────────────────────────────────────────────────────────────
RESEARCH BRIEF
──────────────────────────────────────────────────────────────────────────────
{research_brief}

──────────────────────────────────────────────────────────────────────────────
RESEARCH NOTES ({notes_count} summaries)
──────────────────────────────────────────────────────────────────────────────
{notes_text}

──────────────────────────────────────────────────────────────────────────────
REPORT REQUIREMENTS
──────────────────────────────────────────────────────────────────────────────
1. Structure the report with these sections:
   - # [Descriptive Report Title]
   - ## Executive Summary  (2–3 paragraphs)
   - ## 1. [Topic] … ## N. [Topic]  (one section per major finding)
   - ## Key Findings  (bulleted list, 5–10 items)
   - ## Conclusion  (1–2 paragraphs)
   - ## Sources  (bulleted list of all cited sources)

2. Use inline citations throughout: [Source Name](URL)
   Preserve all citations exactly as they appear in the research notes.
   Do NOT invent new URLs.

3. Synthesise content from ALL {notes_count} research summaries provided.
   Do not focus only on the most-frequently cited sources — later summaries
   may contain critical findings on ethics, ROI, regional data, failure cases,
   or emerging trends. Each distinct subtopic should appear in the report.

4. Deduplicate sources in the ## Sources section: list each URL exactly once.

5. In the ## Key Findings section, each bullet MUST contain a specific,
   concrete claim: a named organisation, a percentage, a monetary figure, a
   year, or a named technology. Generic topic labels ("AI improves efficiency")
   are not acceptable. Aim for 7–10 bullets.

6. Remain grounded in the supplied notes. Do not introduce unsupported facts
   from your own knowledge.

7. Write in a professional, analytical tone.

Return ONLY the Markdown report.
"""


def _format_notes(notes: List[ResearchNote]) -> str:
    parts = []
    for i, note in enumerate(notes, 1):
        status = "" if note.status == "completed" else f" [{note.status.upper()}]"
        parts.append(
            f"### Summary {i}: {note.subtopic}{status}\n\n{note.summary}"
        )
    return "\n\n---\n\n".join(parts)


async def write_final_report(
    research_brief: str,
    notes: List[ResearchNote],
) -> str:
    """Synthesise compressed research notes into a structured cited Markdown report.

    Receives: research brief + compressed notes ONLY.
    Never receives: raw search results, raw webpage content, or agent histories.
    """
    llm = get_llm("writer")
    notes_text = _format_notes(notes)

    prompt = _WRITER_PROMPT.format(
        research_brief=research_brief,
        notes_text=notes_text,
        notes_count=len(notes),
    )

    response = await llm.acomplete(prompt)
    return str(response).strip()
