from __future__ import annotations

"""Tests for citation preservation through the research pipeline."""

import pytest

from app.services.citation import (
    citations_survived,
    count_citations,
    extract_urls_from_markdown,
)
from app.models.state import ResearchNote


# ── Citation extraction ───────────────────────────────────────────────────────

class TestCitationExtraction:

    def test_extracts_inline_markdown_links(self):
        text = (
            "JPMorgan deployed AI [JPMorgan Report](https://example.com/jpmorgan). "
            "Risks discussed in [Accenture Study](https://example.com/acn-study)."
        )
        urls = extract_urls_from_markdown(text)
        assert "https://example.com/jpmorgan" in urls
        assert "https://example.com/acn-study" in urls
        assert len(urls) == 2

    def test_empty_text_returns_empty_list(self):
        assert extract_urls_from_markdown("") == []

    def test_plain_text_no_citations(self):
        assert extract_urls_from_markdown("No links here at all.") == []

    def test_count_citations(self):
        text = "[A](https://a.com) and [B](https://b.com) and [C](https://c.com)"
        assert count_citations(text) == 3


# ── Citation survival through pipeline ───────────────────────────────────────

class TestCitationSurvival:

    def test_citation_from_note_survives_in_report(self, sample_notes):
        """URLs cited in researcher summaries must appear in the final report."""
        # Simulate a final report that incorporates the note citations
        final_report = """# Research Report

## Executive Summary

Major banks have adopted generative AI for customer service.
JPMorgan Chase and Bank of America are leading adopters
[JPMorgan AI Report](https://example.com/jp-ai).

## Key Findings

- Banks deploy LLM chatbots for first-line customer queries
- Regulatory risk is a top concern [Accenture Banking AI](https://example.com/acn)

## Sources

- [JPMorgan AI Report](https://example.com/jp-ai)
- [Accenture Banking AI](https://example.com/acn)
"""
        combined_notes = "\n".join(n.summary for n in sample_notes)
        assert citations_survived(combined_notes, final_report)

    def test_citation_loss_detected(self, sample_notes):
        """If citations are stripped from the report, detection works."""
        report_without_citations = "Banks have adopted AI. Various risks exist."
        combined_notes = "\n".join(n.summary for n in sample_notes)
        assert not citations_survived(combined_notes, report_without_citations)

    def test_no_url_invented_beyond_research_sources(self):
        """All URLs in the final report should come from researcher summaries."""
        note = ResearchNote(
            researcher_id="abc",
            subtopic="AI in banking",
            summary="[Real Source](https://real.example.com/source) found relevant.",
            sources_count=1,
            searches_count=1,
        )
        report_urls = extract_urls_from_markdown(
            "Here is [Real Source](https://real.example.com/source) info."
        )
        source_urls = extract_urls_from_markdown(note.summary)

        invented = [u for u in report_urls if u not in source_urls]
        assert len(invented) == 0, f"Report contains invented URLs: {invented}"

    def test_multiple_notes_citations_aggregated(self, sample_notes):
        """Citations from multiple researcher notes all appear in the final report."""
        report = (
            "AI adoption: [JPMorgan AI Report](https://example.com/jp-ai). "
            "Risks: [Accenture Banking AI](https://example.com/acn). "
        )
        for note in sample_notes:
            note_urls = extract_urls_from_markdown(note.summary)
            assert any(
                url in report for url in note_urls
            ), f"Citation from note '{note.subtopic}' not found in report"
