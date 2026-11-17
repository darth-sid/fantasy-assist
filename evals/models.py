"""Records the eval tools read and write, one JSON object per line."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvalSample(BaseModel):
    """One player to retrieve news for, pinned to a season and week."""

    id: str
    season: int
    week: int
    gsis_id: str
    full_name: str
    position: str


class Judgment(BaseModel):
    """One blind A/B judgment of a player's retrieved news."""

    sample_id: str
    a_config: str
    b_config: str
    left: Literal["a", "b"] | None  # None when both configs retrieved the same items
    choice: Literal["left", "right", "tie", "identical"]
    winner: Literal["a", "b", "tie"]
