from __future__ import annotations

from functools import lru_cache
from typing import Literal

from llama_index.llms.openai import OpenAI

from app.config import settings

ModelRole = Literal["scope", "orchestrator", "researcher", "page_summarizer", "writer"]

_MODEL_MAP: dict[str, str] = {
    "scope": settings.SCOPE_MODEL,
    "orchestrator": settings.ORCHESTRATOR_MODEL,
    "researcher": settings.RESEARCHER_MODEL,
    "page_summarizer": settings.PAGE_SUMMARIZER_MODEL,
    "writer": settings.WRITER_MODEL,
}


@lru_cache(maxsize=10)
def get_llm(role: ModelRole = "researcher") -> OpenAI:
    """Return a cached LLM instance for the given role."""
    model = _MODEL_MAP.get(role, settings.RESEARCHER_MODEL)
    return OpenAI(
        model=model,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.1,
    )
