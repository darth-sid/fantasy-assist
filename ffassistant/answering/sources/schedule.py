from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.clients.nflreadpy_client import load_schedules

_EASTERN = ZoneInfo("America/New_York")


@dataclass
class ScheduleWeek:
    week: int
    opponent: str | None  # None means bye
    home: bool | None
    played: bool
    kickoff: str | None  # ISO 8601 UTC; None on a bye


@dataclass
class ScheduleData:
    team: str
    weeks: list[ScheduleWeek]


def _kickoff(gameday: str, gametime: str | None) -> str:
    local = datetime.fromisoformat(f"{gameday}T{gametime or '00:00'}").replace(tzinfo=_EASTERN)
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def schedule(ctx: ResolvedContext) -> SourceResult[ScheduleData]:
    source = "schedule"
    as_of = f"Week {ctx.week}"

    try:
        df: pl.DataFrame = load_schedules(ctx.season)

        team_df = df.filter(
            (pl.col("game_type") == "REG")
            & ((pl.col("home_team") == ctx.team) | (pl.col("away_team") == ctx.team))
            & (pl.col("week") <= ctx.week)
        )

        if team_df.is_empty():
            return SourceResult(source=source, status="empty", as_of=as_of)

        games = {row["week"]: row for row in team_df.to_dicts()}
        weeks = []
        for week in range(1, ctx.week + 1):
            game = games.get(week)
            if game is None:
                weeks.append(
                    ScheduleWeek(week=week, opponent=None, home=None, played=False, kickoff=None)
                )
                continue
            home = game["home_team"] == ctx.team
            weeks.append(
                ScheduleWeek(
                    week=week,
                    opponent=game["away_team"] if home else game["home_team"],
                    home=home,
                    played=game["result"] is not None,
                    kickoff=_kickoff(game["gameday"], game["gametime"]),
                )
            )

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=ScheduleData(team=ctx.team, weeks=weeks),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
