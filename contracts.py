from dataclasses import dataclass
from typing import Literal


@dataclass
class ResolvedContext:
    player_id: str
    player_name: str
    team: str
    season: int
    week: int
    scoring_format: str  # e.g. "PPR", "Standard", "Half-PPR"


@dataclass
class ContextBlock:
    source: str
    status: Literal["ok", "empty", "error"]
    content: str
    as_of: str
