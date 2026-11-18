from datetime import datetime, timezone

import polars as pl
import pytest

from evals.generate import player_weights, sample_players, teams_playing
from ffassistant.resolution.roster import RosterPlayer

AS_OF = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)


def _player(gsis_id: str, status: str = "ACT", team: str = "KC") -> RosterPlayer:
    return RosterPlayer(gsis_id=gsis_id, full_name=f"Player {gsis_id}", team=team, position="WR", status=status)


ROSTER = {g: _player(g) for g in ("a", "b", "c")} | {
    "res": _player("res", status="RES"),
    "bye": _player("bye", team="BUF"),
}


def _stats(rows: list[tuple[str, int, float, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows, schema=["player_id", "week", "fantasy_points_ppr", "season_type"], orient="row"
    )


def test_weights_are_squared_ppr_per_game_before_the_week():
    stats = _stats([
        ("a", 1, 10.0, "REG"), ("a", 2, 20.0, "REG"),
        ("a", 5, 99.0, "REG"),  # at the target week: excluded
        ("b", 1, 4.9, "REG"),  # under the floor: excluded
        ("res", 1, 30.0, "REG"),  # not active: excluded
        ("bye", 1, 30.0, "REG"),  # team on a bye: excluded
        ("c", 1, 8.0, "POST"),  # not regular season: excluded
    ])

    assert player_weights(ROSTER, stats, week=5, playing={"KC"}, min_ppg=5.0) == {"a": 225.0}


def test_teams_playing_leaves_out_bye_teams():
    schedules = pl.DataFrame(
        [("REG", 5, "KC", "LV"), ("REG", 6, "BUF", "MIA"), ("POST", 5, "SF", "DAL")],
        schema=["game_type", "week", "home_team", "away_team"],
        orient="row",
    )

    assert teams_playing(schedules, 5) == {"KC", "LV"}


def test_same_seed_same_samples():
    weights = {"a": 1.0, "b": 2.0, "c": 3.0}

    first = sample_players(ROSTER, weights, 2026, 11, n=3, seed=7, as_of=AS_OF)

    assert first == sample_players(ROSTER, weights, 2026, 11, n=3, seed=7, as_of=AS_OF)
    assert [s.gsis_id for s in first] != [
        s.gsis_id for s in sample_players(ROSTER, weights, 2026, 11, n=3, seed=8, as_of=AS_OF)
    ]


def test_samples_are_distinct_and_carry_the_week():
    samples = sample_players(ROSTER, {"a": 1.0, "b": 5.0, "c": 1.0}, 2026, 11, n=3, seed=1, as_of=AS_OF)

    assert sorted(s.gsis_id for s in samples) == ["a", "b", "c"]
    assert {(s.season, s.week, s.as_of) for s in samples} == {(2026, 11, "2026-11-17T09:00:00+00:00")}
    assert samples[0].full_name == ROSTER[samples[0].gsis_id].full_name


def test_unweighted_players_are_never_drawn():
    samples = sample_players(ROSTER, {"a": 1.0, "b": 1.0}, 2026, 11, n=2, seed=3, as_of=AS_OF)

    assert {s.gsis_id for s in samples} == {"a", "b"}


def test_more_samples_than_eligible_players_raises():
    with pytest.raises(ValueError, match="only 1"):
        sample_players(ROSTER, {"a": 1.0}, 2026, 11, n=2, seed=0, as_of=AS_OF)
