from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ResearchBrief(BaseModel):
    """Structured output of the Scope Agent."""

    summary: str = Field(description="One-paragraph description of what needs to be investigated")
    dimensions: List[str] = Field(description="Key dimensions or sub-questions to address")
    constraints: Optional[str] = Field(
        default=None,
        description="Time period, geography, industry, or other constraints"
    )
    expected_outputs: str = Field(
        description="What a complete, useful final answer must contain"
    )


class SubtopicPlan(BaseModel):
    """Structured output of the Research Planner."""

    subtopics: List[str] = Field(
        description="Focused, non-overlapping subtopics for individual researchers"
    )
    rationale: str = Field(description="Why these subtopics cover the brief")


class CoverageAssessment(BaseModel):
    """Structured output of the Coverage Critic."""

    sufficient: bool = Field(description="Whether the current notes answer the research brief")
    gaps: List[str] = Field(
        description="Specific information still missing (empty if sufficient)"
    )
    reasoning: str = Field(description="Brief explanation of the assessment")
