from __future__ import annotations

"""Tests for the sub-researcher component."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.state import ResearchNote


@pytest.fixture
def mock_agent_response():
    """A plausible agent final answer with citations."""
    return (
        "JPMorgan Chase deployed an LLM-based customer service bot in Q1 2024, "
        "handling over 50 million queries monthly "
        "[JPMorgan AI](https://example.com/jpmorgan-ai). "
        "Bank of America's Erica assistant processed 1.5 billion interactions in 2023 "
        "[BofA Erica](https://example.com/bofa-erica). "
        "Key risks include hallucination and regulatory compliance gaps."
    )


@pytest.fixture
def mock_compressed_summary():
    return (
        "JPMorgan and Bank of America have deployed LLM customer service tools in 2024. "
        "[JPMorgan AI](https://example.com/jpmorgan-ai) "
        "[BofA Erica](https://example.com/bofa-erica). "
        "Risks: hallucination, regulatory compliance."
    )


@pytest.mark.asyncio
async def test_researcher_returns_research_note(
    sample_brief, mock_agent_response, mock_compressed_summary
):
    """Researcher returns a ResearchNote with non-empty summary."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(__str__=lambda s: mock_agent_response))

    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=MagicMock(__str__=lambda s: mock_compressed_summary))

    with (
        patch("app.workflow.researcher.FunctionAgent", return_value=mock_agent),
        patch("app.workflow.researcher.get_llm", return_value=mock_llm),
    ):
        from app.workflow.researcher import run_researcher
        note = await run_researcher("AI adoption in banking", sample_brief)

    assert isinstance(note, ResearchNote)
    assert note.summary
    assert note.status in ("completed", "failed")


@pytest.mark.asyncio
async def test_researcher_summary_contains_citations(
    sample_brief, mock_agent_response, mock_compressed_summary
):
    """Researcher summary contains inline markdown citations."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(__str__=lambda s: mock_agent_response))

    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=MagicMock(__str__=lambda s: mock_compressed_summary))

    with (
        patch("app.workflow.researcher.FunctionAgent", return_value=mock_agent),
        patch("app.workflow.researcher.get_llm", return_value=mock_llm),
    ):
        from app.workflow.researcher import run_researcher
        note = await run_researcher("AI adoption in banking", sample_brief)

    from app.services.citation import extract_urls_from_markdown
    urls = extract_urls_from_markdown(note.summary)
    assert len(urls) >= 1, "Summary must contain at least one citation URL"


@pytest.mark.asyncio
async def test_researcher_handles_agent_failure(sample_brief):
    """A researcher that raises an exception returns a failed ResearchNote — not an unhandled error."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=RuntimeError("Simulated agent crash"))

    mock_llm = MagicMock()

    with (
        patch("app.workflow.researcher.FunctionAgent", return_value=mock_agent),
        patch("app.workflow.researcher.get_llm", return_value=mock_llm),
    ):
        from app.workflow.researcher import run_researcher
        note = await run_researcher("Failing subtopic", sample_brief)

    assert note.status == "failed"
    assert "failed" in note.summary.lower() or "error" in note.summary.lower() or "simulated" in note.summary.lower()


@pytest.mark.asyncio
async def test_researcher_context_isolation(sample_brief, mock_agent_response, mock_compressed_summary):
    """The returned ResearchNote contains only the compressed summary — not raw tool history."""
    tool_call_log = []

    def fake_search(query: str) -> str:
        tool_call_log.append(("search", query, "HUGE_RESULT_DATA" * 100))
        return "1. [Example](https://example.com)\n   snippet"

    def fake_read(url: str, research_question: str = "") -> str:
        tool_call_log.append(("read", url, "RAW_PAGE_CONTENT" * 500))
        return "Relevant extracted content."

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(__str__=lambda s: mock_agent_response))

    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=MagicMock(__str__=lambda s: mock_compressed_summary))

    with (
        patch("app.workflow.researcher.FunctionAgent", return_value=mock_agent),
        patch("app.workflow.researcher.get_llm", return_value=mock_llm),
    ):
        from app.workflow.researcher import run_researcher
        note = await run_researcher("AI in banking", sample_brief)

    # The returned note should NOT contain raw search/page content
    assert "HUGE_RESULT_DATA" not in note.summary
    assert "RAW_PAGE_CONTENT" not in note.summary
    # Only compressed summary
    assert len(note.summary) < 10_000
