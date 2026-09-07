from __future__ import annotations

import pytest


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_query() -> str:
    return (
        "How is generative AI changing customer service in banking, "
        "what technologies are being adopted, what are the major risks, "
        "and which banks have publicly deployed these solutions?"
    )


@pytest.fixture
def sample_brief() -> str:
    return """## Research Brief

This investigation covers the adoption of generative AI in banking customer service.

### Key Dimensions
- Technologies adopted (LLMs, chatbots, voice AI)
- Use cases (customer service, fraud detection, onboarding)
- Major risks (hallucination, compliance, data privacy)
- Specific bank deployments and public announcements

### Constraints
Focus on 2023–2025, global scope with emphasis on large retail banks.

### Expected Outputs
A comprehensive overview of AI adoption trends, technology stack, identified
risks, and named institutions with live deployments.
"""


@pytest.fixture
def sample_notes():
    from app.models.state import ResearchNote
    return [
        ResearchNote(
            researcher_id="abc12345",
            subtopic="Generative AI adoption in banking",
            summary=(
                "Major banks including JPMorgan Chase and Bank of America have "
                "deployed LLM-based customer service assistants in 2024 "
                "[JPMorgan AI Report](https://example.com/jp-ai). "
                "Goldman Sachs uses AI for internal knowledge management."
            ),
            sources_count=3,
            searches_count=2,
            status="completed",
        ),
        ResearchNote(
            researcher_id="def67890",
            subtopic="Risks of AI in banking",
            summary=(
                "Hallucination and regulatory non-compliance are the top risks cited "
                "by industry analysts [Accenture Banking AI](https://example.com/acn). "
                "The EU AI Act imposes specific requirements on financial AI systems."
            ),
            sources_count=4,
            searches_count=3,
            status="completed",
        ),
    ]
