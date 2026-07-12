from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from clients.nflreadpy_client import load_player_stats
from contracts import ResolvedContext, SourceResult

# Stat columns relevant per position group.
_POSITION_COLS: dict[str, list[str]] = {
    "QB": [
        "completions", "attempts", "passing_yards", "passing_tds",
        "passing_interceptions", "carries", "rushing_yards", "rushing_tds",
    ],
    "RB": [
        "carries", "rushing_yards", "rushing_tds",
        "receptions", "targets", "receiving_yards", "receiving_tds",
    ],
    "WR": ["receptions", "targets", "receiving_yards", "receiving_tds"],
    "TE": ["receptions", "targets", "receiving_yards", "receiving_tds"],
    "K": ["fg_made", "fg_att", "pat_made"],
}
_DEFAULT_COLS = ["receptions", "targets", "receiving_yards", "receiving_tds",
                 "carries", "rushing_yards", "rushing_tds"]


@dataclass
class GameLine:
    week: int
    opponent: str
    stats: dict[str, float]


@dataclass
class RecentStatsData:
    position: str | None
    games: list[GameLine]


def recent_stats(ctx: ResolvedContext, last_n: int | None = None) -> SourceResult[RecentStatsData]:
    """last_n caps output to the most recent N games; unset fetches the full season."""
    source = "recent_stats"
    as_of = f"Week {ctx.week}"

    try:
        df: pl.DataFrame = load_player_stats(ctx.season, summary_level="week")

        player_df = (
            df.filter(
                (pl.col("player_id") == ctx.player_id)
                & (pl.col("season_type") == "REG")
            )
            .sort("week")
        )

        if player_df.is_empty():
            return SourceResult(source=source, status="empty", as_of=as_of)

        if last_n is not None:
            player_df = player_df.tail(last_n)

        position = player_df["position"][0] if "position" in player_df.columns else None
        stat_cols = _POSITION_COLS.get(position or "", _DEFAULT_COLS)

        games = [
            GameLine(
                week=row["week"],
                opponent=row.get("opponent_team", "?"),
                stats={col: row[col] for col in stat_cols if row.get(col) is not None},
            )
            for row in player_df.to_dicts()
        ]

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=RecentStatsData(position=position, games=games),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
