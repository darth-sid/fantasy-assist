"""Typed settings loaded from config.yaml; loaded once at each entry point and passed down."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config.yaml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMConfig(_Section):
    """Which provider and models the LLM touch points use."""

    provider: str
    parser_model: str
    answer_model: str


class IngestConfig(_Section):
    """Feeds the collector polls, keyed by source name."""

    feeds: dict[str, str]


class NewsConfig(_Section):
    """News retrieval knobs: caps, window, ranker, and query templates."""

    top_k: int
    team_top_k: int
    opponent_top_k: int
    lookback_days: int
    max_summary_chars: int
    ranker: str
    query_team: str
    query_opponent: str
    position_words: dict[str, str]


class Config(_Section):
    """All settings; sections can be passed down on their own."""

    season: int
    default_scoring_format: str
    news_dir: Path
    llm: LLMConfig
    ingest: IngestConfig
    news: NewsConfig

    @field_validator("news_dir")
    @classmethod
    def _from_repo_root(cls, path: Path) -> Path:
        # Resolved against the repo root so cron/launchd runs find the same files from any cwd.
        return REPO_ROOT / path


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Reads and validates a config file; unknown or missing keys raise."""
    return Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
