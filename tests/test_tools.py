from __future__ import annotations

"""Tests for the Tavily search and ReadURL tools."""

import pytest
from unittest.mock import MagicMock, patch


# ── Tavily search ─────────────────────────────────────────────────────────────

class TestTavilySearch:

    def test_returns_formatted_results(self):
        mock_results = [
            {"title": "AI in Banking", "url": "https://example.com/ai-banking", "content": "Banks adopt AI."},
            {"title": "Risks of AI", "url": "https://example.com/risks", "content": "Hallucination risks."},
        ]
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": mock_results}

        with patch("app.tools.tavily_search._get_client", return_value=mock_client):
            from app.tools.tavily_search import search_web
            result = search_web("AI in banking")

        assert "AI in Banking" in result
        assert "https://example.com/ai-banking" in result
        assert "Risks of AI" in result

    def test_handles_tavily_failure_gracefully(self):
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("Network error")

        with patch("app.tools.tavily_search._get_client", return_value=mock_client):
            from app.tools.tavily_search import search_web
            result = search_web("query that will fail")

        assert "failed" in result.lower() or "error" in result.lower()

    def test_returns_no_results_message(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}

        with patch("app.tools.tavily_search._get_client", return_value=mock_client):
            from app.tools.tavily_search import search_web
            result = search_web("obscure query")

        assert "no results" in result.lower()

    def test_snippet_truncated_to_300_chars(self):
        long_content = "x" * 1000
        mock_results = [
            {"title": "Test", "url": "https://example.com", "content": long_content}
        ]
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": mock_results}

        with patch("app.tools.tavily_search._get_client", return_value=mock_client):
            from app.tools.tavily_search import search_web
            result = search_web("test query")

        # The snippet in the output should be ≤300 chars
        snippet_part = result.split("\n   ")[1] if "\n   " in result else result
        assert len(snippet_part) <= 300


# ── ReadURL ───────────────────────────────────────────────────────────────────

class TestReadURL:

    def test_compresses_large_page(self):
        """Large raw content is compressed before returning to researcher."""
        raw = "relevant financial AI information. " * 3000  # ~100k chars
        compressed = "Compressed: AI used in banking for customer service [Source](https://example.com)."

        mock_llm = MagicMock()
        mock_llm.complete = MagicMock(
            return_value=MagicMock(__str__=lambda s: compressed)
        )

        with (
            patch("app.tools.read_url.fetch_and_extract", return_value=raw),
            patch("app.tools.read_url.get_llm", return_value=mock_llm),
        ):
            from app.tools.read_url import read_url
            result = read_url("https://example.com/article", research_question="AI banking")

        assert len(result) < len(raw), "Result should be shorter than raw content"
        assert "Compressed" in result

    def test_returns_error_message_on_fetch_failure(self):
        with patch("app.tools.read_url.fetch_and_extract", return_value=None):
            from app.tools.read_url import read_url
            result = read_url("https://broken-url.example.com")

        assert "could not" in result.lower() or "failed" in result.lower() or "retrieve" in result.lower()

    def test_short_page_returned_without_compression(self):
        """A page shorter than 500 chars is returned as-is."""
        short_content = "Short page content."

        mock_llm = MagicMock()

        with (
            patch("app.tools.read_url.fetch_and_extract", return_value=short_content),
            patch("app.tools.read_url.get_llm", return_value=mock_llm),
        ):
            from app.tools.read_url import read_url
            result = read_url("https://example.com/short", research_question="test")

        # LLM should not have been called for very short content
        mock_llm.complete.assert_not_called()
        assert result == short_content


# ── Think / Reflect ───────────────────────────────────────────────────────────

class TestReflect:

    def test_reflect_returns_structured_output(self):
        from app.tools.think import reflect
        result = reflect(
            what_learned="Banks are adopting LLMs",
            what_evidence="JPMorgan report [Source](https://example.com)",
            what_missing="European bank data",
            next_action="Search for European bank AI deployments",
        )
        assert "What I've learned" in result
        assert "Evidence collected" in result
        assert "Still missing" in result
        assert "Next action" in result
        assert "European bank" in result
