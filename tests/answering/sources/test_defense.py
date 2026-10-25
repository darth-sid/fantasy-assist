import polars as pl
import pytest

import ffassistant.answering.sources.defense as defense_module
from ffassistant.answering.models import ResolvedContext
from ffassistant.answering.sources.defense import DefenseRow, defense

CTX = ResolvedContext(
    player_id="00-0036322",
    player_name="Justin Jefferson",
    team="MIN",
    position="WR",
    season=2026,
    week=7,
    scoring_format="PPR",
)


def _stats_df(rows: list[dict]) -> pl.DataFrame:
    base = {
        "season_type": "REG",
        "position": "WR",
        "opponent_team": "BAL",
        "week": 1,
        "fantasy_points": 0.0,
        "fantasy_points_ppr": 0.0,
    }
    return pl.DataFrame([{**base, **row} for row in rows])


def _patch(monkeypatch, df: pl.DataFrame) -> None:
    monkeypatch.setattr(defense_module, "load_player_stats", lambda season, summary_level: df)


def _rows_by_team(result) -> dict[str, DefenseRow]:
    return {row.team: row for row in result.data.rows}


def test_sums_players_on_one_defense_within_a_game(monkeypatch):
    _patch(
        monkeypatch,
        _stats_df(
            [
                {"week": 1, "fantasy_points": 10.0, "fantasy_points_ppr": 15.0},
                {"week": 1, "fantasy_points": 4.0, "fantasy_points_ppr": 7.0},
            ]
        ),
    )

    result = defense(CTX)

    assert result.status == "ok"
    assert result.source == "defense"
    assert result.data.position == "WR"
    assert _rows_by_team(result)["BAL"] == DefenseRow(team="BAL", games=1, standard_pg=14.0, ppr_pg=22.0)


def test_averages_each_defense_over_its_games(monkeypatch):
    _patch(
        monkeypatch,
        _stats_df(
            [
                {"week": 1, "fantasy_points": 10.0, "fantasy_points_ppr": 15.0},
                {"week": 1, "fantasy_points": 4.0, "fantasy_points_ppr": 7.0},
                {"week": 2, "fantasy_points": 6.0, "fantasy_points_ppr": 8.0},
                {"week": 1, "opponent_team": "SF", "fantasy_points": 9.0, "fantasy_points_ppr": 12.0},
            ]
        ),
    )

    rows = _rows_by_team(defense(CTX))

    assert rows["BAL"] == DefenseRow(team="BAL", games=2, standard_pg=10.0, ppr_pg=15.0)
    assert rows["SF"] == DefenseRow(team="SF", games=1, standard_pg=9.0, ppr_pg=12.0)


def test_excludes_games_at_or_after_target_week(monkeypatch):
    _patch(
        monkeypatch,
        _stats_df(
            [
                {"week": 6, "fantasy_points": 10.0, "fantasy_points_ppr": 10.0},
                {"week": 7, "fantasy_points": 50.0, "fantasy_points_ppr": 50.0},
                {"week": 8, "fantasy_points": 50.0, "fantasy_points_ppr": 50.0},
            ]
        ),
    )

    rows = _rows_by_team(defense(CTX))

    assert rows["BAL"].games == 1
    assert rows["BAL"].standard_pg == pytest.approx(10.0)


def test_filters_to_player_position_and_regular_season(monkeypatch):
    _patch(
        monkeypatch,
        _stats_df(
            [
                {"week": 1, "fantasy_points": 10.0, "fantasy_points_ppr": 10.0},
                {"week": 1, "position": "RB", "fantasy_points": 30.0, "fantasy_points_ppr": 30.0},
                {"week": 2, "season_type": "POST", "fantasy_points": 30.0, "fantasy_points_ppr": 30.0},
            ]
        ),
    )

    rows = _rows_by_team(defense(CTX))

    assert rows["BAL"] == DefenseRow(team="BAL", games=1, standard_pg=10.0, ppr_pg=10.0)


def test_empty_when_no_games_before_target_week(monkeypatch):
    _patch(monkeypatch, _stats_df([{"week": 7}]))

    result = defense(CTX)

    assert result.status == "empty"
    assert result.data is None


def test_error_status_when_fetch_raises(monkeypatch):
    def _raise(season, summary_level):
        raise RuntimeError("network down")

    monkeypatch.setattr(defense_module, "load_player_stats", _raise)

    result = defense(CTX)

    assert result.status == "error"
    assert result.data is None
    assert "network down" in result.error
