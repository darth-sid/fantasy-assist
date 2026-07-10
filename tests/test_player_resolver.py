import polars as pl
import pytest

import resolution.player_resolver as player_resolver_module
from resolution.player_resolver import (
    AmbiguousPlayerNameError,
    PlayerNotFoundError,
    resolve_from_player,
)


def _rosters(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_resolves_single_roster_row(monkeypatch):
    df = _rosters(
        [{"full_name": "Justin Jefferson", "gsis_id": "00-0036322", "team": "MIN", "week": 1}]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    ctx = resolve_from_player("Justin Jefferson", season=2023, week=12, scoring_format="PPR")

    assert ctx.player_id == "00-0036322"
    assert ctx.team == "MIN"
    assert ctx.player_name == "Justin Jefferson"


def test_lookup_is_case_and_whitespace_insensitive(monkeypatch):
    df = _rosters(
        [{"full_name": "Justin Jefferson", "gsis_id": "00-0036322", "team": "MIN", "week": 1}]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    ctx = resolve_from_player("  JUSTIN jefferson  ", season=2023, week=12, scoring_format="PPR")

    assert ctx.player_id == "00-0036322"


def test_picks_team_as_of_target_week_across_a_trade(monkeypatch):
    df = _rosters(
        [
            {"full_name": "Test Player", "gsis_id": "00-1111111", "team": "TEAMA", "week": 1},
            {"full_name": "Test Player", "gsis_id": "00-1111111", "team": "TEAMB", "week": 9},
        ]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    assert resolve_from_player("Test Player", season=2023, week=5, scoring_format="PPR").team == "TEAMA"
    assert resolve_from_player("Test Player", season=2023, week=9, scoring_format="PPR").team == "TEAMB"
    assert resolve_from_player("Test Player", season=2023, week=20, scoring_format="PPR").team == "TEAMB"


def test_falls_back_to_earliest_row_when_target_week_predates_all_rows(monkeypatch):
    df = _rosters(
        [{"full_name": "Test Player", "gsis_id": "00-1111111", "team": "TEAMA", "week": 9}]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    assert resolve_from_player("Test Player", season=2023, week=1, scoring_format="PPR").team == "TEAMA"


def test_raises_not_found_for_unknown_name(monkeypatch):
    df = _rosters(
        [{"full_name": "Justin Jefferson", "gsis_id": "00-0036322", "team": "MIN", "week": 1}]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    with pytest.raises(PlayerNotFoundError):
        resolve_from_player("Not A Real Player", season=2023, week=1, scoring_format="PPR")


def test_raises_ambiguous_for_name_collision(monkeypatch):
    df = _rosters(
        [
            {"full_name": "Lamar Jackson", "gsis_id": "00-AAAAAAA", "team": "BAL", "week": 1},
            {"full_name": "Lamar Jackson", "gsis_id": "00-BBBBBBB", "team": "NYJ", "week": 1},
        ]
    )
    monkeypatch.setattr(player_resolver_module, "load_rosters", lambda season: df)

    with pytest.raises(AmbiguousPlayerNameError):
        resolve_from_player("Lamar Jackson", season=2023, week=1, scoring_format="PPR")
