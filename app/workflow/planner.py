from __future__ import annotations

from typing import List

from llama_index.core.program import LLMTextCompletionProgram

from app.models.schemas import ResearchBrief, SubtopicPlan
from app.services.llm import get_llm
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────────

_SCOPE_PROMPT = """\
You are an expert research analyst. A user has submitted a complex research question.
Your task is to produce a focused research brief that will guide a team of researchers.

User question:
{user_query}

Produce a structured research brief that covers:
1. What needs to be investigated (summary)
2. The key dimensions or sub-questions to address
3. Relevant constraints (time period, geography, industry, etc.) if applicable
4. What a complete, useful final answer must contain

Be concise but thorough. The brief will be used to coordinate multiple researchers.
"""

_PLAN_PROMPT = """\
You are a research planning expert. Based on the research brief below, decompose the
investigation into {num_subtopics} focused, non-overlapping subtopics.

Each subtopic should:
- Be specific enough to guide an individual researcher
- Address a distinct aspect of the overall question
- Together, cover the full scope of the brief

Research Brief:
{research_brief}

Return a list of subtopics and a brief rationale for the decomposition.
"""


async def create_research_brief(user_query: str) -> str:
    """Convert a user question into a structured research brief (plain text)."""
    llm = get_llm("scope")
    program = LLMTextCompletionProgram.from_defaults(
        output_cls=ResearchBrief,
        llm=llm,
        prompt_template_str=_SCOPE_PROMPT,
        verbose=False,
    )

    brief: ResearchBrief = await program.acall(user_query=user_query)

    # Serialise to a readable text block that later steps can parse naturally
    parts = [f"## Research Brief\n\n{brief.summary}"]
    if brief.dimensions:
        dims = "\n".join(f"- {d}" for d in brief.dimensions)
        parts.append(f"### Key Dimensions\n{dims}")
    if brief.constraints:
        parts.append(f"### Constraints\n{brief.constraints}")
    parts.append(f"### Expected Outputs\n{brief.expected_outputs}")

    text = "\n\n".join(parts)
    logger.info("Research brief created", dimensions=len(brief.dimensions))
    return text


async def plan_subtopics(research_brief: str, num_subtopics: int = 5) -> List[str]:
    """Break a research brief into focused subtopics for parallel research."""
    llm = get_llm("orchestrator")
    program = LLMTextCompletionProgram.from_defaults(
        output_cls=SubtopicPlan,
        llm=llm,
        prompt_template_str=_PLAN_PROMPT,
        verbose=False,
    )

    plan: SubtopicPlan = await program.acall(
        research_brief=research_brief,
        num_subtopics=num_subtopics,
    )

    subtopics = [s.strip() for s in plan.subtopics if s.strip()]
    logger.info("Subtopics planned", count=len(subtopics), rationale=plan.rationale[:80])
    return subtopics
