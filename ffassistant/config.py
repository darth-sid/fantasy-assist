"""Typed settings loaded from config.yaml; loaded once at each entry point and passed down."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

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
    judge_model: str


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


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path = CONFIG_PATH, overrides: Sequence[Path] = ()) -> Config:
    """Reads a config, deep-merges each override file over it in order, and validates the result."""
    data = _read(path)
    for override in overrides:
        data = _merge(data, _read(override))
    return Config.model_validate(data)
