from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ffassistant.clients.nflreadpy_client import load_player_stats
from ffassistant.contracts import ResolvedContext, SourceResult


@dataclass
class DefenseRow:
    team: str
    games: int
    standard_pg: float
    ppr_pg: float


@dataclass
class DefenseData:
    position: str
    rows: list[DefenseRow]


def defense(ctx: ResolvedContext) -> SourceResult[DefenseData]:
    """League table of fantasy points each defense allowed to ctx.position, games strictly before ctx.week."""
    source = "defense"
    as_of = f"Week {ctx.week}"

    try:
        df: pl.DataFrame = load_player_stats(ctx.season, summary_level="week")

        position_df = df.filter(
            (pl.col("season_type") == "REG")
            & (pl.col("week") < ctx.week)
            & (pl.col("position") == ctx.position)
        )

        if position_df.is_empty():
            return SourceResult(source=source, status="empty", as_of=as_of)

        per_game = position_df.group_by("opponent_team", "week").agg(
            pl.col("fantasy_points").sum(),
            pl.col("fantasy_points_ppr").sum(),
        )
        per_team = (
            per_game.group_by("opponent_team")
            .agg(
                pl.len().alias("games"),
                pl.col("fantasy_points").mean().alias("standard_pg"),
                pl.col("fantasy_points_ppr").mean().alias("ppr_pg"),
            )
            .sort("opponent_team")
        )

        rows = [
            DefenseRow(
                team=row["opponent_team"],
                games=row["games"],
                standard_pg=row["standard_pg"],
                ppr_pg=row["ppr_pg"],
            )
            for row in per_team.to_dicts()
        ]

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=DefenseData(position=ctx.position, rows=rows),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
