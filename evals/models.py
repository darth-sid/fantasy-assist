"""Records the eval tools read and write, one JSON object per line."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalSample(BaseModel):
    """One player to retrieve news for, pinned to a season, week, and corpus snapshot."""

    id: str
    season: int
    week: int
    as_of: str  # generation time (ISO 8601 UTC); news is cut off and frozen at it
    gsis_id: str
    full_name: str
    position: str


class Retrieved(BaseModel):
    """What one config retrieved for a sample: its status and selected doc_ids per bucket."""

    status: str
    error: str | None = None
    player: list[str] = []
    team: list[str] = []
    opponent: list[str] = []


class Judgment(BaseModel):
    """One blind A/B judgment of a player's retrieved news, with what each side showed."""

    sample_id: str
    a_config: str
    b_config: str
    cutoff: str
    a: Retrieved
    b: Retrieved
    left: Literal["a", "b"] | None  # None when both configs retrieved the same items
    choice: Literal["left", "right", "tie", "identical"]
    winner: Literal["a", "b", "tie"]
