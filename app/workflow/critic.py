from __future__ import annotations

from typing import List

from llama_index.core.program import LLMTextCompletionProgram

from app.models.schemas import CoverageAssessment
from app.models.state import ResearchNote
from app.services.llm import get_llm
from app.utils.logging import get_logger

logger = get_logger(__name__)

_CRITIC_PROMPT = """\
You are a rigorous research quality analyst.

Your task: assess whether the collected research notes adequately answer the
research brief, and identify any important gaps.

──────────────────────────────────────────────────────────────────────────────
RESEARCH BRIEF
──────────────────────────────────────────────────────────────────────────────
{research_brief}

──────────────────────────────────────────────────────────────────────────────
COLLECTED RESEARCH NOTES ({notes_count} summaries)
──────────────────────────────────────────────────────────────────────────────
{notes_text}

──────────────────────────────────────────────────────────────────────────────
ASSESSMENT INSTRUCTIONS
──────────────────────────────────────────────────────────────────────────────
1. Determine whether the notes collectively answer all major dimensions of the
   research brief.
2. List only MAJOR gaps — information that is critically missing and would
   substantially change the findings. Do NOT invent peripheral sub-questions
   or opportunities for minor deeper specialisation.
   Frame each gap as a concrete research question a researcher could investigate.
3. If coverage is sufficient, set sufficient=True and leave gaps empty.

SUFFICIENCY THRESHOLD (apply these rules before setting sufficient):
- Mark sufficient=True when the main research question is substantially answered
  with concrete evidence across the key dimensions of the brief.
- A report is sufficient when a professional analyst could write a useful,
  evidence-based answer from it — exhaustive coverage is NOT required.
- If 70%+ of the key dimensions are well covered with cited evidence, mark
  as sufficient=True even if niche angles remain unexplored.
- Only mark sufficient=False when a core dimension of the research brief is
  absent or critically thin (no concrete data, no real-world examples).
- Gaps should represent MAJOR missing coverage, not minor nuance.
"""


def _format_notes(notes: List[ResearchNote]) -> str:
    parts = []
    for i, note in enumerate(notes, 1):
        parts.append(
            f"--- Summary {i}: {note.subtopic} ---\n{note.summary}\n"
        )
    return "\n".join(parts)


async def assess_coverage(
    research_brief: str,
    notes: List[ResearchNote],
) -> CoverageAssessment:
    """Use an LLM to assess whether the research notes sufficiently cover the brief.

    Input to the LLM: research brief + compressed notes only.
    Raw researcher histories are never passed here.
    """
    if not notes:
        return CoverageAssessment(
            sufficient=False,
            gaps=["No research has been conducted yet."],
            reasoning="No notes available.",
        )

    llm = get_llm("orchestrator")
    program = LLMTextCompletionProgram.from_defaults(
        output_cls=CoverageAssessment,
        llm=llm,
        prompt_template_str=_CRITIC_PROMPT,
        verbose=False,
    )

    notes_text = _format_notes(notes)
    assessment: CoverageAssessment = await program.acall(
        research_brief=research_brief,
        notes_text=notes_text,
        notes_count=len(notes),
    )

    logger.info(
        "Coverage assessed",
        sufficient=assessment.sufficient,
        gaps_count=len(assessment.gaps),
        reasoning=assessment.reasoning[:100],
    )
    return assessment
