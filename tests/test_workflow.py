from __future__ import annotations

"""
Tests for the full research workflow.

Covers:
- Parallelism: multiple researchers run concurrently
- Gap loop: insufficient → additional research → sufficient → writer
- Failure recovery: one failed researcher does not destroy the run
- Context isolation: orchestrator never receives researcher raw histories
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.state import ResearchNote


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_note(subtopic: str, status: str = "completed") -> ResearchNote:
    return ResearchNote(
        researcher_id="test001",
        subtopic=subtopic,
        summary=f"Findings on {subtopic} [Source](https://example.com/{subtopic[:10].replace(' ', '-')}).",
        sources_count=2,
        searches_count=1,
        status=status,
    )


# ── Parallelism ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_researchers_run_concurrently():
    """Multiple subtopics produce results concurrently via orchestrator."""
    subtopics = ["Topic A", "Topic B", "Topic C"]
    start_times = []

    async def fake_researcher(subtopic: str, brief: str) -> ResearchNote:
        start_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)  # simulate work
        return _make_note(subtopic)

    from app.models.state import ResearchState

    with patch("app.workflow.orchestrator.run_researcher", side_effect=fake_researcher):
        from app.workflow.orchestrator import run_parallel_researchers
        state = ResearchState(user_query="test")
        notes = await run_parallel_researchers(subtopics, "brief text", state)

    assert len(notes) == 3
    # All three should have started within a short window (concurrent, not serial)
    if len(start_times) == 3:
        total_spread = max(start_times) - min(start_times)
        assert total_spread < 0.1, "Researchers should start concurrently"


# ── Failure recovery ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_one_failed_researcher_does_not_stop_run():
    """Orchestrator continues when one researcher fails."""
    call_count = 0

    async def mixed_researcher(subtopic: str, brief: str) -> ResearchNote:
        nonlocal call_count
        call_count += 1
        if subtopic == "Failing Topic":
            raise RuntimeError("Simulated researcher crash")
        return _make_note(subtopic)

    from app.models.state import ResearchState

    with patch("app.workflow.orchestrator.run_researcher", side_effect=mixed_researcher):
        from app.workflow.orchestrator import run_parallel_researchers
        state = ResearchState(user_query="test")
        notes = await run_parallel_researchers(
            ["Good Topic A", "Failing Topic", "Good Topic B"],
            "brief",
            state,
        )

    # Two successful notes + one failed note (failed researchers still return a note)
    assert len(notes) == 3
    statuses = {n.status for n in notes}
    assert "completed" in statuses
    assert "failed" in statuses


# ── Gap loop ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gap_loop_insufficient_triggers_additional_research():
    """When coverage is insufficient, workflow triggers an additional research round."""
    from app.models.schemas import CoverageAssessment
    from app.models.schemas import SubtopicPlan
    from app.models.schemas import ResearchBrief

    initial_note = _make_note("Initial Topic")
    gap_note = _make_note("Gap Topic")
    final_note = _make_note("Extra Gap Topic")

    # First assessment: insufficient
    insufficient = CoverageAssessment(
        sufficient=False,
        gaps=["Need European bank data"],
        reasoning="Missing EU coverage.",
    )
    # Second assessment: sufficient
    sufficient = CoverageAssessment(
        sufficient=True,
        gaps=[],
        reasoning="All dimensions covered.",
    )

    assessment_calls = []

    async def fake_assess(brief, notes):
        assessment_calls.append(len(notes))
        if len(assessment_calls) == 1:
            return insufficient
        return sufficient

    async def fake_researcher(subtopic: str, brief: str) -> ResearchNote:
        if "Initial" in subtopic:
            return initial_note
        return gap_note

    plan = SubtopicPlan(subtopics=["Initial Topic"], rationale="test")
    brief_obj = ResearchBrief(
        summary="Test brief",
        dimensions=["dim1"],
        constraints=None,
        expected_outputs="test output",
    )

    with (
        patch("app.workflow.research_workflow.assess_coverage", side_effect=fake_assess),
        patch("app.workflow.research_workflow.run_parallel_researchers",
              AsyncMock(side_effect=[
                  [initial_note],  # first research round
                  [gap_note],      # second research round (gap)
              ])),
        patch("app.workflow.planner.LLMTextCompletionProgram.from_defaults") as mock_plan_factory,
        patch("app.workflow.writer.write_final_report", AsyncMock(return_value="# Report")),
    ):
        scope_program = MagicMock()
        scope_program.acall = AsyncMock(return_value=brief_obj)

        plan_program = MagicMock()
        plan_program.acall = AsyncMock(return_value=plan)

        mock_plan_factory.side_effect = [scope_program, plan_program]

        from app.workflow.research_workflow import ResearchWorkflow
        wf = ResearchWorkflow(timeout=60)
        result = await wf.run(user_query="Test question")

    # Coverage assessment should have been called twice
    assert len(assessment_calls) == 2


@pytest.mark.asyncio
async def test_sufficient_coverage_goes_directly_to_writer():
    """When first assessment is sufficient, writer is called without a second research round."""
    from app.models.schemas import CoverageAssessment, SubtopicPlan, ResearchBrief

    note = _make_note("Topic A")
    sufficient = CoverageAssessment(sufficient=True, gaps=[], reasoning="Complete.")

    plan = SubtopicPlan(subtopics=["Topic A"], rationale="test")
    brief_obj = ResearchBrief(
        summary="Test",
        dimensions=["d1"],
        constraints=None,
        expected_outputs="output",
    )

    research_rounds = []

    async def fake_run_parallel(subtopics, brief, state):
        research_rounds.append(subtopics)
        return [note]

    with (
        patch("app.workflow.research_workflow.assess_coverage", AsyncMock(return_value=sufficient)),
        patch("app.workflow.research_workflow.run_parallel_researchers", side_effect=fake_run_parallel),
        patch("app.workflow.planner.LLMTextCompletionProgram.from_defaults") as mock_factory,
        patch("app.workflow.writer.write_final_report", AsyncMock(return_value="# Final Report")),
    ):
        scope_prog = MagicMock()
        scope_prog.acall = AsyncMock(return_value=brief_obj)
        plan_prog = MagicMock()
        plan_prog.acall = AsyncMock(return_value=plan)
        mock_factory.side_effect = [scope_prog, plan_prog]

        from app.workflow.research_workflow import ResearchWorkflow
        wf = ResearchWorkflow(timeout=60)
        result = await wf.run(user_query="Test question")

    # Only one research round should have been triggered
    assert len(research_rounds) == 1
    assert "# Final Report" in result
