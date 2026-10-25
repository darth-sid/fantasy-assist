from __future__ import annotations

import polars as pl

from ffassistant.answering.models import ResolvedContext
from ffassistant.clients.nflreadpy_client import load_rosters
from ffassistant.resolution.models import ValidPlayer


def player_context(
    player: ValidPlayer, season: int, week: int, scoring_format: str
) -> ResolvedContext:
    """Team is taken from the roster row with the latest week <= `week`, falling
    back to the earliest known row if none qualify."""
    rows = load_rosters(season).filter(pl.col("gsis_id") == player.player_id).sort("week")
    prior = rows.filter(pl.col("week") <= week)
    row = prior.row(-1, named=True) if not prior.is_empty() else rows.row(0, named=True)

    return ResolvedContext(
        player_id=player.player_id,
        player_name=player.full_name,
        team=row["team"],
        position=player.position,
        season=season,
        week=week,
        scoring_format=scoring_format,
    )
