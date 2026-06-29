from __future__ import annotations

import traceback
from typing import Literal

import nflreadpy
import polars as pl

from contracts import ContextBlock, ResolvedContext

# Stat columns rendered per position group.
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


def _stat_line(row: dict, cols: list[str]) -> str:
    parts = []
    for col in cols:
        val = row.get(col)
        if val is None:
            continue
        label = {
            "completions": "cmp", "attempts": "att",
            "passing_yards": "pass yds", "passing_tds": "pass TD",
            "passing_interceptions": "INT",
            "carries": "car", "rushing_yards": "rush yds", "rushing_tds": "rush TD",
            "receptions": "rec", "targets": "tgt",
            "receiving_yards": "rec yds", "receiving_tds": "rec TD",
            "fg_made": "FGM", "fg_att": "FGA", "pat_made": "XPM",
        }.get(col, col)
        parts.append(f"{val} {label}")
    return ", ".join(parts) if parts else "—"


def recent_stats(ctx: ResolvedContext, last_n: int | None = None) -> ContextBlock:
    """
    Fetch the full regular-season game log for ctx.player_id in ctx.season.

    last_n: when set, caps output to the most recent N games (parked knob).
    """
    source = "recent_stats"
    as_of = f"Week {ctx.week}"

    try:
        df: pl.DataFrame = nflreadpy.load_player_stats(
            seasons=ctx.season, summary_level="week"
        )

        player_df = (
            df.filter(
                (pl.col("player_id") == ctx.player_id)
                & (pl.col("season_type") == "REG")
            )
            .sort("week")
        )

        if player_df.is_empty():
            return ContextBlock(
                source=source,
                status="empty",
                content=f"RECENT STATS: no regular-season games found for {ctx.player_name} in {ctx.season}.",
                as_of=as_of,
            )

        if last_n is not None:
            player_df = player_df.tail(last_n)

        # Determine stat columns from position.
        position = player_df["position"][0] if "position" in player_df.columns else None
        stat_cols = _POSITION_COLS.get(position or "", _DEFAULT_COLS)

        n_games = len(player_df)
        scope = f"last {last_n} games" if last_n is not None else "full season"
        lines = [
            f"RECENT STATS ({scope} · {ctx.scoring_format} · as of Week {ctx.week})"
        ]

        for row in player_df.to_dicts():
            opp = row.get("opponent_team", "?")
            wk = row.get("week", "?")
            lines.append(f"  Wk {wk:<2} vs {opp:<3} — {_stat_line(row, stat_cols)}")

        lines.append(f"  ({n_games} games)")

        return ContextBlock(
            source=source,
            status="ok",
            content="\n".join(lines),
            as_of=as_of,
        )

    except Exception:
        return ContextBlock(
            source=source,
            status="error",
            content=f"RECENT STATS: fetch failed.\n{traceback.format_exc()}",
            as_of=as_of,
        )
