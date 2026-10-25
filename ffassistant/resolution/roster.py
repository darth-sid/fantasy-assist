from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from ffassistant.clients.nflreadpy_client import load_rosters

FANTASY_POSITIONS = ["QB", "RB", "WR", "TE", "K"]


@dataclass
class RosterPlayer:
    gsis_id: str
    full_name: str
    team: str
    position: str
    status: str


def load_fantasy_roster(season: int) -> dict[str, RosterPlayer]:
    """One entry per gsis_id from its latest roster row, every status included."""
    rosters = load_rosters(season).filter(
        pl.col("position").is_in(FANTASY_POSITIONS) & pl.col("gsis_id").is_not_null()
    )
    latest = rosters.sort("week").group_by("gsis_id").last().sort("full_name", "gsis_id")
    return {
        row["gsis_id"]: RosterPlayer(
            gsis_id=row["gsis_id"],
            full_name=row["full_name"],
            team=row["team"],
            position=row["position"],
            status=row["status"],
        )
        for row in latest.to_dicts()
    }


def render_roster(roster: dict[str, RosterPlayer]) -> str:
    lines = ["gsis_id | full_name | team | position | status"]
    lines.extend(
        f"{p.gsis_id} | {p.full_name} | {p.team} | {p.position} | {p.status}"
        for p in roster.values()
    )
    return "\n".join(lines)
