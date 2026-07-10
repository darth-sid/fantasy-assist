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
