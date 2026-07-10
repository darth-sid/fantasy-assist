from __future__ import annotations

import polars as pl

from clients.nflreadpy_client import load_rosters
from contracts import ResolvedContext


class PlayerNotFoundError(Exception):
    """No roster row matches the given name in that season."""


class AmbiguousPlayerNameError(Exception):
    """The name matches more than one distinct player (gsis_id) in that season."""


def _build_name_index(rosters: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Group roster rows by lowercased full_name."""
    keyed = rosters.with_columns(pl.col("full_name").str.to_lowercase().alias("_name_key"))
    partitioned = keyed.partition_by("_name_key", as_dict=True)
    return {name_key: group for (name_key,), group in partitioned.items()}


def resolve_from_player(name: str, season: int, week: int, scoring_format: str) -> ResolvedContext:
    """Team is taken from the roster row with the latest week <= `week`, falling
    back to the earliest known row if none qualify."""
    rosters = load_rosters(season)
    index = _build_name_index(rosters)

    matches = index.get(name.strip().lower())
    if matches is None:
        raise PlayerNotFoundError(f"No player found matching {name!r} in {season}.")

    distinct_ids = matches["gsis_id"].unique().to_list()
    if len(distinct_ids) > 1:
        raise AmbiguousPlayerNameError(
            f"{name!r} matches multiple players in {season}: {distinct_ids}"
        )

    prior = matches.filter(pl.col("week") <= week).sort("week")
    if not prior.is_empty():
        row = prior.row(-1, named=True)  # latest known status at/before the target week
    else:
        row = matches.sort("week").row(0, named=True)  # earliest known row, as fallback

    return ResolvedContext(
        player_id=row["gsis_id"],
        player_name=row["full_name"],
        team=row["team"],
        season=season,
        week=week,
        scoring_format=scoring_format,
    )
