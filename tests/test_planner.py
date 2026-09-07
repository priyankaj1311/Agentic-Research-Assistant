from __future__ import annotations

"""Tests for the research planner (scope + subtopic generation)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import ResearchBrief, SubtopicPlan


@pytest.mark.asyncio
async def test_create_research_brief_returns_string(sample_query):
    """Scope agent returns a non-empty research brief string."""
    mock_brief = ResearchBrief(
        summary="Investigation of generative AI in banking customer service.",
        dimensions=[
            "Technologies adopted",
            "Use cases",
            "Risks",
            "Named bank deployments",
        ],
        constraints="2023–2025, global focus",
        expected_outputs="Named banks, technologies, risks, and deployment details.",
    )

    with patch(
        "app.workflow.planner.LLMTextCompletionProgram.from_defaults"
    ) as mock_factory:
        mock_program = MagicMock()
        mock_program.acall = AsyncMock(return_value=mock_brief)
        mock_factory.return_value = mock_program

        from app.workflow.planner import create_research_brief
        brief = await create_research_brief(sample_query)

    assert isinstance(brief, str)
    assert len(brief) > 50
    assert "Technologies adopted" in brief


@pytest.mark.asyncio
async def test_plan_subtopics_returns_multiple_focused_topics(sample_brief):
    """Planner decomposes a broad brief into multiple non-overlapping subtopics."""
    mock_plan = SubtopicPlan(
        subtopics=[
            "Generative AI chatbots in retail banking customer service",
            "Regulatory risks and compliance challenges for bank AI",
            "Named bank deployments of LLM-based customer service tools",
            "Data privacy and hallucination risks in financial AI",
            "Voice AI and omnichannel AI adoption in banking",
        ],
        rationale="Covers technology, risk, and deployment dimensions.",
    )

    with patch(
        "app.workflow.planner.LLMTextCompletionProgram.from_defaults"
    ) as mock_factory:
        mock_program = MagicMock()
        mock_program.acall = AsyncMock(return_value=mock_plan)
        mock_factory.return_value = mock_program

        from app.workflow.planner import plan_subtopics
        subtopics = await plan_subtopics(sample_brief)

    assert len(subtopics) >= 3, "Expected at least 3 subtopics for a complex question"
    assert all(isinstance(s, str) for s in subtopics)
    # Topics should be distinct
    assert len(set(subtopics)) == len(subtopics), "Subtopics should be non-overlapping"


@pytest.mark.asyncio
async def test_plan_subtopics_no_empty_entries(sample_brief):
    """Planner strips empty strings from returned subtopics."""
    mock_plan = SubtopicPlan(
        subtopics=["Topic A", "  ", "Topic B", ""],
        rationale="Test plan",
    )

    with patch(
        "app.workflow.planner.LLMTextCompletionProgram.from_defaults"
    ) as mock_factory:
        mock_program = MagicMock()
        mock_program.acall = AsyncMock(return_value=mock_plan)
        mock_factory.return_value = mock_program

        from app.workflow.planner import plan_subtopics
        subtopics = await plan_subtopics(sample_brief)

    assert all(s.strip() for s in subtopics), "All subtopics should be non-empty"
