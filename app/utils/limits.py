from __future__ import annotations

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BudgetExceededError(Exception):
    """Raised when a configurable budget limit is hit."""


class ResearchBudget:
    """Tracks and enforces research budget limits."""

    def __init__(self) -> None:
        self._llm_calls = 0
        self._search_calls = 0

    # ── LLM calls ─────────────────────────────────────────────────────────────
    def charge_llm(self, n: int = 1) -> None:
        self._llm_calls += n
        if self._llm_calls > settings.MAX_LLM_CALLS:
            raise BudgetExceededError(
                f"MAX_LLM_CALLS ({settings.MAX_LLM_CALLS}) exceeded "
                f"(current={self._llm_calls})"
            )

    def llm_ok(self) -> bool:
        return self._llm_calls < settings.MAX_LLM_CALLS

    # ── Search calls ──────────────────────────────────────────────────────────
    def charge_search(self, n: int = 1) -> None:
        self._search_calls += n

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def llm_calls(self) -> int:
        return self._llm_calls

    @property
    def search_calls(self) -> int:
        return self._search_calls
