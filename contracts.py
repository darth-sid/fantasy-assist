from dataclasses import dataclass
from typing import Literal


@dataclass
class ParsedRequest:
    raw_prompt: str
    player_names: list[str]
    week: int
    scoring_format: str


@dataclass
class ResolvedContext:
    player_id: str
    player_name: str
    team: str
    season: int
    week: int
    scoring_format: str  # e.g. "PPR", "Standard", "Half-PPR"


@dataclass
class SourceResult[T]:
    source: str
    status: Literal["ok", "empty", "error"]
    as_of: str
    data: T | None = None
    error: str | None = None  # populated on status="error"


@dataclass
class Answer:
    answer: str  # markdown
    cited_doc_ids: list[str]


FeatureVector = dict[str, float]
