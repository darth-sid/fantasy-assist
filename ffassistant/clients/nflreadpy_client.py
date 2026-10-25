from __future__ import annotations

from typing import Literal

import nflreadpy
import polars as pl


def load_player_stats(
    season: int, summary_level: Literal["week", "reg", "post", "reg+post"] = "week"
) -> pl.DataFrame:
    return nflreadpy.load_player_stats(seasons=season, summary_level=summary_level)


def load_rosters(season: int) -> pl.DataFrame:
    return nflreadpy.load_rosters(seasons=season)


def load_schedules(season: int) -> pl.DataFrame:
    return nflreadpy.load_schedules(seasons=season)


def load_injuries(season: int) -> pl.DataFrame:
    return nflreadpy.load_injuries(seasons=season)


def get_current_week() -> int:
    # Schedule-based; use_date=True assumes a first-Thursday-of-September kickoff and is wrong for 2026.
    return nflreadpy.get_current_week()
