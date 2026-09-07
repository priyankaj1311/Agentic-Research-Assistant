from __future__ import annotations

"""
Architecture diagram
─────────────────────────────────────────────────────────────────────────────

StartEvent(user_query)
        │
        ▼ scope()
ScopeCompleteEvent(research_brief)
        │
        ▼ plan()
PlanReviewEvent(subtopics, brief)         ← HITL checkpoint 1: edit plan
        │
        ▼ review_plan()
ResearchEvent(subtopics, brief, iteration=1, accumulated_notes=[])
        │
        ▼ run_research()            ← also receives ResearchEvent from review_sources()
CoverageEvent(accumulated_notes, brief, iteration)
        │
        ▼ assess_and_route()
        ├── [gaps exist & limits not hit]
        │       └── ResearchEvent(gap_subtopics, ..., iteration+1, accumulated_notes)
        │               │
        │               └──► run_research()  ← iterative loop
        │
        └── [sufficient OR max iterations / orchestrator steps reached]
                └── SourceReviewEvent(notes, brief, iteration)  ← HITL checkpoint 2
                        │
                        ▼ review_sources()
                        ├── [no exclusions OR sufficient after re-assess]
                        │       └── WriteEvent(notes, brief)
                        │               │
                        │               ▼ write()
                        │           StopEvent(result=report)
                        │
                        └── [insufficient after exclusions]
                                └── ResearchEvent(gap_subtopics, ..., iteration+1)
                                        │
                                        └──► run_research() ← gap fill loop
                                                (excluded URLs blocked via visited_urls)

Context-isolation guarantee
─────────────────────────────────────────────────────────────────────────────
- Each researcher runs in an isolated coroutine with its own FunctionAgent.
- Only ResearchNote.summary (compressed cited text) enters CoverageEvent.
- The orchestrator and writer NEVER receive raw search results, webpage
  content, or researcher conversation histories.
- SharedState in Context holds compressed notes only.
"""

import asyncio
from typing import List, Union

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from app.config import settings
from app.models.state import ResearchNote, ResearchState
from app.services.citation import extract_urls_from_markdown
from app.utils.logging import get_logger
from app.workflow.critic import assess_coverage
from app.workflow.hitl import (
    recompress_without_sources,
    review_plan_hitl,
    review_sources_hitl,
)
from app.workflow.orchestrator import run_parallel_researchers
from app.workflow.planner import create_research_brief, plan_subtopics
from app.workflow.writer import write_final_report

logger = get_logger(__name__)


# ── Events ────────────────────────────────────────────────────────────────────

class ScopeCompleteEvent(Event):
    research_brief: str


class PlanReviewEvent(Event):
    """Carries the generated subtopics to the HITL plan-review checkpoint."""
    subtopics: List[str]
    research_brief: str


class ResearchEvent(Event):
    """Carries the subtopics to research in the next round."""
    subtopics: List[str]
    research_brief: str
    iteration: int
    accumulated_notes: List[ResearchNote]


class CoverageEvent(Event):
    """Carries all accumulated notes into the coverage assessment."""
    accumulated_notes: List[ResearchNote]
    research_brief: str
    iteration: int


class SourceReviewEvent(Event):
    """Carries accumulated notes to the HITL source-review checkpoint."""
    accumulated_notes: List[ResearchNote]
    research_brief: str
    iteration: int


class WriteEvent(Event):
    notes: List[ResearchNote]
    research_brief: str


# ── Workflow ──────────────────────────────────────────────────────────────────

class ResearchWorkflow(Workflow):
    """LlamaIndex Workflow implementing the full agentic research pipeline."""

    # ── Step 1: Scope ─────────────────────────────────────────────────────────

    @step
    async def scope(self, ctx: Context, ev: StartEvent) -> ScopeCompleteEvent:
        user_query: str = ev.get("user_query", "")
        if not user_query:
            raise ValueError("StartEvent must contain 'user_query'")

        logger.info("Research run started", query=user_query[:120])

        state = ResearchState(user_query=user_query)
        await ctx.store.set("state", state)

        research_brief = await create_research_brief(user_query)
        state.research_brief = research_brief
        state.increment_llm()
        await ctx.store.set("state", state)

        logger.info("Research brief created", run_id=state.run_id)
        return ScopeCompleteEvent(research_brief=research_brief)

    # ── Step 2: Plan ──────────────────────────────────────────────────────────

    @step
    async def plan(self, ctx: Context, ev: ScopeCompleteEvent) -> PlanReviewEvent:
        state: ResearchState = await ctx.store.get("state")

        subtopics = await plan_subtopics(ev.research_brief)
        state.subtopics = subtopics
        state.increment_llm()
        await ctx.store.set("state", state)

        logger.info("Subtopics generated", subtopics=subtopics)

        return PlanReviewEvent(
            subtopics=subtopics,
            research_brief=ev.research_brief,
        )

    # ── Step 3: HITL — Plan review ────────────────────────────────────────────

    @step
    async def review_plan(self, ctx: Context, ev: PlanReviewEvent) -> ResearchEvent:
        approved = await review_plan_hitl(ev.subtopics)

        state: ResearchState = await ctx.store.get("state")
        state.subtopics = approved
        await ctx.store.set("state", state)

        logger.info("Research plan approved", count=len(approved))

        return ResearchEvent(
            subtopics=approved,
            research_brief=ev.research_brief,
            iteration=1,
            accumulated_notes=[],
        )

    # ── Step 4: Research (runs both initial and gap rounds) ───────────────────

    @step
    async def run_research(self, ctx: Context, ev: ResearchEvent) -> CoverageEvent:
        state: ResearchState = await ctx.store.get("state")

        # Budget guard: compute how many researchers the remaining LLM budget can afford.
        calls_remaining = settings.MAX_LLM_CALLS - state.llm_call_count
        max_affordable = max(1, calls_remaining // settings.MAX_RESEARCHER_STEPS)

        if calls_remaining <= 0:
            logger.warning("LLM budget reached, skipping research round")
            return CoverageEvent(
                accumulated_notes=ev.accumulated_notes,
                research_brief=ev.research_brief,
                iteration=ev.iteration,
            )

        subtopics = ev.subtopics[:max_affordable]
        if len(subtopics) < len(ev.subtopics):
            logger.warning(
                "Researcher count capped by LLM budget",
                requested=len(ev.subtopics),
                allowed=len(subtopics),
                llm_calls_used=state.llm_call_count,
            )

        logger.info(
            "Researchers launched",
            iteration=ev.iteration,
            count=len(subtopics),
        )

        new_notes = await run_parallel_researchers(
            subtopics, ev.research_brief, state,
            visited_urls=frozenset(state.visited_urls),
        )

        for note in new_notes:
            state.add_note(note)
            state.increment_llm(settings.MAX_RESEARCHER_STEPS)
            if note.status == "completed":
                state.visited_urls.update(extract_urls_from_markdown(note.summary))

        all_notes = ev.accumulated_notes + new_notes
        await ctx.store.set("state", state)

        logger.info(
            "Research round complete",
            iteration=ev.iteration,
            new_notes=len(new_notes),
            total_notes=len(all_notes),
            llm_calls_est=state.llm_call_count,
        )

        return CoverageEvent(
            accumulated_notes=all_notes,
            research_brief=ev.research_brief,
            iteration=ev.iteration,
        )

    # ── Step 5: Assess coverage → route to more research or source review ─────

    @step
    async def assess_and_route(
        self, ctx: Context, ev: CoverageEvent
    ) -> Union[ResearchEvent, SourceReviewEvent]:
        state: ResearchState = await ctx.store.get("state")

        # Hard stop on iteration limit
        if ev.iteration >= settings.MAX_RESEARCH_ITERATIONS:
            logger.info(
                "Max research iterations reached",
                iteration=ev.iteration,
                limit=settings.MAX_RESEARCH_ITERATIONS,
            )
            state.status = "reviewing"
            await ctx.store.set("state", state)
            return SourceReviewEvent(
                accumulated_notes=ev.accumulated_notes,
                research_brief=ev.research_brief,
                iteration=ev.iteration,
            )

        # Secondary safety cap on total orchestrator decisions
        if state.orchestrator_steps >= settings.MAX_ORCHESTRATOR_STEPS:
            logger.info(
                "Max orchestrator steps reached",
                orchestrator_steps=state.orchestrator_steps,
                limit=settings.MAX_ORCHESTRATOR_STEPS,
            )
            state.status = "reviewing"
            await ctx.store.set("state", state)
            return SourceReviewEvent(
                accumulated_notes=ev.accumulated_notes,
                research_brief=ev.research_brief,
                iteration=ev.iteration,
            )

        state.orchestrator_steps += 1
        assessment = await assess_coverage(ev.research_brief, ev.accumulated_notes)
        state.gaps = assessment.gaps
        state.iteration = ev.iteration + 1
        state.increment_llm()
        await ctx.store.set("state", state)

        logger.info(
            "Coverage assessment complete",
            sufficient=assessment.sufficient,
            gaps=assessment.gaps,
            iteration=ev.iteration,
        )

        if assessment.sufficient or not assessment.gaps:
            logger.info("Coverage sufficient — proceeding to source review")
            state.status = "reviewing"
            await ctx.store.set("state", state)
            return SourceReviewEvent(
                accumulated_notes=ev.accumulated_notes,
                research_brief=ev.research_brief,
                iteration=ev.iteration,
            )

        logger.info(
            "Additional research triggered",
            gaps_count=len(assessment.gaps),
            next_iteration=ev.iteration + 1,
        )
        return ResearchEvent(
            subtopics=assessment.gaps,
            research_brief=ev.research_brief,
            iteration=ev.iteration + 1,
            accumulated_notes=ev.accumulated_notes,
        )

    # ── Step 6: HITL — Source review ──────────────────────────────────────────

    @step
    async def review_sources(
        self, ctx: Context, ev: SourceReviewEvent
    ) -> Union[WriteEvent, ResearchEvent]:
        state: ResearchState = await ctx.store.get("state")
        state.source_review_rounds += 1
        await ctx.store.set("state", state)

        # Safety: hard cap on source-review loops — force write if limit hit
        if state.source_review_rounds > settings.MAX_SOURCE_REVIEW_ROUNDS:
            logger.warning(
                "Max source-review rounds exceeded — forcing synthesis",
                rounds=state.source_review_rounds,
                limit=settings.MAX_SOURCE_REVIEW_ROUNDS,
            )
            return WriteEvent(
                notes=ev.accumulated_notes,
                research_brief=ev.research_brief,
            )

        excluded, force_write = await review_sources_hitl(
            ev.accumulated_notes,
            round_num=state.source_review_rounds,
            max_rounds=settings.MAX_SOURCE_REVIEW_ROUNDS,
        )

        # User forced synthesis — skip re-assessment
        if force_write or not excluded:
            if excluded:
                # Still re-compress even on force-write so excluded URLs
                # don't appear in the report Sources section
                state.visited_urls.update(excluded)
                notes = await recompress_without_sources(ev.accumulated_notes, excluded)
                state.increment_llm(
                    sum(1 for n in ev.accumulated_notes
                        if any(u in n.summary for u in excluded))
                )
                await ctx.store.set("state", state)
            else:
                notes = ev.accumulated_notes
            return WriteEvent(notes=notes, research_brief=ev.research_brief)

        # Block excluded URLs from future research rounds
        state.visited_urls.update(excluded)

        # Re-compress affected notes to genuinely remove excluded content
        cleaned_notes = await recompress_without_sources(ev.accumulated_notes, excluded)
        state.increment_llm(
            sum(1 for n in ev.accumulated_notes
                if any(u in n.summary for u in excluded))
        )

        # Re-assess coverage with the cleaned notes
        assessment = await assess_coverage(ev.research_brief, cleaned_notes)
        state.increment_llm()
        await ctx.store.set("state", state)

        logger.info(
            "Post-exclusion coverage assessment",
            sufficient=assessment.sufficient,
            gaps_count=len(assessment.gaps),
        )

        if assessment.sufficient or not assessment.gaps:
            return WriteEvent(notes=cleaned_notes, research_brief=ev.research_brief)

        # Coverage insufficient — trigger targeted gap fill
        logger.info(
            "Coverage insufficient after source exclusions — gap fill triggered",
            gaps=assessment.gaps,
        )
        return ResearchEvent(
            subtopics=assessment.gaps,
            research_brief=ev.research_brief,
            iteration=ev.iteration + 1,
            accumulated_notes=cleaned_notes,
        )

    # ── Step 7: Write final report ────────────────────────────────────────────

    @step
    async def write(self, ctx: Context, ev: WriteEvent) -> StopEvent:
        state: ResearchState = await ctx.store.get("state")

        logger.info("Final synthesis started", notes_count=len(ev.notes))

        report = await write_final_report(ev.research_brief, ev.notes)
        state.report = report
        state.status = "completed"
        state.increment_llm()
        await ctx.store.set("state", state)

        logger.info(
            "Report generated",
            run_id=state.run_id,
            chars=len(report),
            llm_calls=state.llm_call_count,
            searches=state.search_count,
            researchers=state.researcher_count,
        )

        return StopEvent(result=report)
