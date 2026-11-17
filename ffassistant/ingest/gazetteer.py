"""Roster and team name lookups for finding player and team mentions in news text."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import polars as pl

from ffassistant.clients.nflreadpy_client import load_rosters, load_teams

_CURLY_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_NAME_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv)$")


def name_key(text: str) -> str:
    """Normalizes a name or text for matching: lowercase, no periods, no trailing suffix."""
    key = text.lower().translate(_CURLY_QUOTES).replace(".", "")
    key = re.sub(r"\s+", " ", key).strip()
    return _NAME_SUFFIX.sub("", key)


@dataclass
class Gazetteer:
    """Player and team name keys, matched as whole words in text."""

    players: dict[str, list[tuple[str, str]]]  # name key -> [(gsis_id, team)]; several on a name clash
    teams: dict[str, str]  # alias name key -> team abbreviation
    _pattern: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Longest first, so "parker washington" is consumed as a player before "washington" can match a team.
        keys = sorted(set(self.players) | set(self.teams), key=len, reverse=True)
        alternation = "|".join(re.escape(key) for key in keys) or r"(?!)"
        self._pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")

    def find(self, text: str) -> list[str]:
        """Returns the name keys mentioned in text, in order; overlaps go to the longer key."""
        return self._pattern.findall(name_key(text))


def _players(rosters: pl.DataFrame) -> dict[str, list[tuple[str, str]]]:
    latest = (
        rosters.filter(pl.col("gsis_id").is_not_null())
        .sort("week")
        .group_by("gsis_id", maintain_order=True)
        .last()
        .sort("gsis_id")
    )
    players: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in latest.iter_rows(named=True):
        players[name_key(row["full_name"])].append((row["gsis_id"], row["team"]))
    return dict(players)


def _teams(teams: pl.DataFrame, current: set[str]) -> dict[str, str]:
    # load_teams also lists relocated franchises (OAK, SD, STL) and a duplicate Rams row (LAR).
    rows = [row for row in teams.iter_rows(named=True) if row["team_abbr"] in current]
    cities = {
        row["team_abbr"]: row["team_name"].removesuffix(row["team_nick"]).strip() for row in rows
    }
    city_counts = Counter(cities.values())
    aliases = {}
    for row in rows:
        abbr = row["team_abbr"]
        aliases[name_key(row["team_name"])] = abbr
        aliases[name_key(row["team_nick"])] = abbr
        if city_counts[cities[abbr]] == 1:
            aliases[name_key(cities[abbr])] = abbr
    return aliases


def load_gazetteer(season: int) -> Gazetteer:
    """Builds the gazetteer from the season's roster (every position) and current teams."""
    rosters = load_rosters(season)
    current = set(rosters["team"].drop_nulls().unique().to_list())
    return Gazetteer(players=_players(rosters), teams=_teams(load_teams(), current))
