from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ffassistant.clients.nflreadpy_client import load_schedules
from ffassistant.contracts import ResolvedContext, SourceResult


@dataclass
class ScheduleWeek:
    week: int
    opponent: str | None  # None means bye
    home: bool | None
    played: bool


@dataclass
class ScheduleData:
    team: str
    weeks: list[ScheduleWeek]


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
                weeks.append(ScheduleWeek(week=week, opponent=None, home=None, played=False))
                continue
            home = game["home_team"] == ctx.team
            weeks.append(
                ScheduleWeek(
                    week=week,
                    opponent=game["away_team"] if home else game["home_team"],
                    home=home,
                    played=game["result"] is not None,
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
