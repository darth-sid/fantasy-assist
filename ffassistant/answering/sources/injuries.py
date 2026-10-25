from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.clients.nflreadpy_client import load_injuries


@dataclass
class InjuryEntry:
    report_status: str | None  # None means listed without a game designation
    primary_injury: str | None
    practice_status: str | None


@dataclass
class InjuryData:
    week: int
    entry: InjuryEntry | None  # None means the team has a report and the player is not on it


def injuries(ctx: ResolvedContext) -> SourceResult[InjuryData]:
    source = "injuries"
    as_of = f"Week {ctx.week}"

    try:
        df: pl.DataFrame = load_injuries(ctx.season)

        team_df = df.filter((pl.col("week") == ctx.week) & (pl.col("team") == ctx.team))

        # A team with no rows hasn't reported yet (or is on bye), so absence says nothing about the player.
        if team_df.is_empty():
            return SourceResult(source=source, status="empty", as_of=as_of)

        player_rows = team_df.filter(pl.col("gsis_id") == ctx.player_id)
        entry = None
        if not player_rows.is_empty():
            row = player_rows.row(0, named=True)
            entry = InjuryEntry(
                report_status=row["report_status"],
                primary_injury=row["report_primary_injury"],
                practice_status=row["practice_status"],
            )

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=InjuryData(week=ctx.week, entry=entry),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
