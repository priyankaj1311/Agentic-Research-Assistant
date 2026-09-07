from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional, Set

from pydantic import BaseModel, Field


class ResearchNote(BaseModel):
    """Compressed, cited summary produced by one sub-researcher.

    This is the ONLY artefact that leaves the researcher's isolated context.
    Raw search results, webpage content, and agent reasoning history are
    never stored here.
    """

    researcher_id: str
    subtopic: str
    summary: str  # cited markdown summary
    sources_count: int = 0
    searches_count: int = 0
    elapsed_time: float = 0.0
    status: str = "completed"  # completed | failed


class ResearchState(BaseModel):
    """Shared workflow state.

    Contains only compressed outputs — never raw research contexts.
    """

    user_query: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    research_brief: Optional[str] = None
    subtopics: List[str] = Field(default_factory=list)
    research_notes: List[ResearchNote] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    iteration: int = 0
    report: Optional[str] = None
    status: str = "started"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Counters — used for budget enforcement
    researcher_count: int = 0
    llm_call_count: int = 0
    search_count: int = 0
    orchestrator_steps: int = 0
    source_review_rounds: int = 0

    # Cross-round URL deduplication: URLs read in prior rounds are skipped by new researchers
    visited_urls: Set[str] = Field(default_factory=set)

    model_config = {"arbitrary_types_allowed": True}

    def increment_llm(self, n: int = 1) -> None:
        self.llm_call_count += n
        self.updated_at = datetime.utcnow()

    def add_note(self, note: ResearchNote) -> None:
        self.research_notes.append(note)
        self.researcher_count += 1
        self.search_count += note.searches_count
        self.updated_at = datetime.utcnow()
