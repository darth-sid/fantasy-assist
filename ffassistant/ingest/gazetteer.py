"""Roster and team name lookups for finding player and team mentions in news text."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import polars as pl

from ffassistant.clients.nflreadpy_client import load_rosters, load_teams

_CURLY_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_NAME_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv)$")


def _clean(text: str) -> str:
    text = text.translate(_CURLY_QUOTES).replace(".", "")
    return re.sub(r"\s+", " ", text).strip()


def name_key(text: str) -> str:
    """Normalizes a name for matching: lowercase, no periods, no trailing suffix."""
    return _NAME_SUFFIX.sub("", _clean(text).lower())


@dataclass
class Mentions:
    """What a text mentions: candidate players per name, and named teams."""

    players: list[list[tuple[str, str]]]  # one candidate list per player-name mention
    teams: set[str]


@dataclass
class Gazetteer:
    """Player names (any case) and team aliases (exact case), matched as whole words."""

    players: dict[str, list[tuple[str, str]]]  # name key -> [(gsis_id, team)]; several on a name clash
    teams: dict[str, str]  # alias, case preserved ("Raiders") -> team abbreviation
    _pattern: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Longest first, so "Parker Washington" is consumed as a player before "Washington" can match a team.
        keys = sorted(set(self.players) | set(self.teams), key=len, reverse=True)
        # Team aliases are case-sensitive so "bills" or "jets" as ordinary words don't match.
        alternation = "|".join(
            f"(?-i:{re.escape(key)})" if key in self.teams else re.escape(key) for key in keys
        )
        self._pattern = re.compile(rf"(?<!\w)(?:{alternation or '(?!)'})(?!\w)", re.IGNORECASE)

    def find(self, text: str) -> Mentions:
        """Returns the players and teams mentioned in text; overlaps go to the longer name."""
        mentions = Mentions(players=[], teams=set())
        for match in self._pattern.findall(_clean(text)):
            if match in self.teams:
                mentions.teams.add(self.teams[match])
            if (candidates := self.players.get(name_key(match))) is not None:
                mentions.players.append(candidates)
        return mentions


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
        aliases[_clean(row["team_name"])] = abbr
        aliases[_clean(row["team_nick"])] = abbr
        if city_counts[cities[abbr]] == 1:
            aliases[_clean(cities[abbr])] = abbr
    return aliases


def load_gazetteer(season: int) -> Gazetteer:
    """Builds the gazetteer from the season's roster (every position) and current teams."""
    rosters = load_rosters(season)
    current = set(rosters["team"].drop_nulls().unique().to_list())
    return Gazetteer(players=_players(rosters), teams=_teams(load_teams(), current))
