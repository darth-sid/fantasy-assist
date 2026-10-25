from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

ScoringFormat = Literal["PPR", "Half-PPR", "Standard"]


class ExtractedPlayer(BaseModel):
    mention: str
    player_id: str | None


class ExtractedRequest(BaseModel):
    players: list[ExtractedPlayer]
    week: int | None
    scoring_format: str | None


@dataclass
class ValidPlayer:
    mention: str
    player_id: str
    full_name: str
    position: str


@dataclass
class RejectedMention:
    mention: str
    reason: str


@dataclass
class ValidatedRequest:
    raw_prompt: str
    season: int
    week: int
    scoring_format: ScoringFormat
    players: list[ValidPlayer]
    rejected: list[RejectedMention]


class RequestValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors
