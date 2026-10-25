from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    # The sources import ResolvedContext/SourceResult from here, so a runtime import would be circular.
    from ffassistant.answering.sources.defense import DefenseData
    from ffassistant.answering.sources.injuries import InjuryData
    from ffassistant.answering.sources.recent_stats import RecentStatsData
    from ffassistant.answering.sources.schedule import ScheduleData


@dataclass
class ResolvedContext:
    player_id: str
    player_name: str
    team: str
    position: str
    roster_status: str
    season: int
    week: int
    scoring_format: str  # "PPR", "Standard", or "Half-PPR"


@dataclass
class SourceResult[T]:
    source: str
    status: Literal["ok", "empty", "error"]
    as_of: str
    data: T | None = None
    error: str | None = None  # populated on status="error"


@dataclass
class PlayerInputs:
    ctx: ResolvedContext
    recent_stats: SourceResult[RecentStatsData]
    schedule: SourceResult[ScheduleData]
    defense: SourceResult[DefenseData]
    injuries: SourceResult[InjuryData]


@dataclass
class Answer:
    answer: str  # markdown
    cited_doc_ids: list[str]
