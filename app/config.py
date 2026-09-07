from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── API keys ──────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key")
    TAVILY_API_KEY: str = Field(..., description="Tavily API key")

    # ── Model roles ───────────────────────────────────────────────────────────
    SCOPE_MODEL: str = "gpt-4o"
    ORCHESTRATOR_MODEL: str = "gpt-4o"
    RESEARCHER_MODEL: str = "gpt-4o-mini"
    PAGE_SUMMARIZER_MODEL: str = "gpt-4o-mini"
    WRITER_MODEL: str = "gpt-4o"

    # ── Budget / safety limits ────────────────────────────────────────────────
    MAX_RESEARCH_ITERATIONS: int = 2
    MAX_CONCURRENT_RESEARCHERS: int = 5
    MAX_ORCHESTRATOR_STEPS: int = 8
    MAX_RESEARCHER_STEPS: int = 20
    MAX_SEARCH_RESULTS: int = 10
    MAX_CONTENT_LENGTH: int = 50000
    MAX_LLM_CALLS: int = 200
    MAX_RETRIES: int = 3
    MAX_SOURCE_REVIEW_ROUNDS: int = 3

    # ── Source credibility filtering ─────────────────────────────────────────
    # Domains excluded from Tavily search results and blocked in read_url.
    # Add vendor blogs, social platforms, or paywalled sites as needed.
    SOURCE_EXCLUDE_DOMAINS: List[str] = Field(
        default=[
            "reddit.com",
            "quora.com",
            "blogspot.com",
            "tumblr.com",
            "pinterest.com",
            "facebook.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
        ]
    )
    # Optional allowlist — if non-empty, ONLY these domains are searched.
    # Leave empty to allow all domains (minus the exclude list above).
    SOURCE_INCLUDE_DOMAINS: List[str] = Field(default=[])

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


settings = Settings()
