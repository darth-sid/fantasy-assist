import polars as pl

import sources.recent_stats as recent_stats_module
from contracts import ResolvedContext
from sources.recent_stats import recent_stats

CTX = ResolvedContext(
    player_id="00-0036322",
    player_name="Justin Jefferson",
    team="MIN",
    season=2023,
    week=12,
    scoring_format="PPR",
)


def _stats_df(rows: list[dict]) -> pl.DataFrame:
    base = {
        "player_id": "00-0036322",
        "season_type": "REG",
        "position": "WR",
        "opponent_team": "DAL",
        "receptions": 0,
        "targets": 0,
        "receiving_yards": 0,
        "receiving_tds": 0,
        "fantasy_points": 0.0,
        "fantasy_points_ppr": 0.0,
    }
    return pl.DataFrame([{**base, **row} for row in rows])


def test_ok_status_sorts_by_week_and_reports_all_games(monkeypatch):
    df = _stats_df(
        [
            {"week": 2, "opponent_team": "PHI", "receptions": 7},
            {"week": 1, "opponent_team": "TB", "receptions": 9},
        ]
    )
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX)

    assert result.status == "ok"
    assert result.source == "recent_stats"
    assert result.data is not None
    assert [game.week for game in result.data.games] == [1, 2]
    assert len(result.data.games) == 2


def test_last_n_caps_to_most_recent_games(monkeypatch):
    df = _stats_df([{"week": w} for w in range(1, 6)])
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX, last_n=2)

    assert result.data is not None
    assert [game.week for game in result.data.games] == [4, 5]


def test_game_stats_carry_position_relevant_columns(monkeypatch):
    df = _stats_df([{"week": 1, "receptions": 7, "targets": 9, "receiving_yards": 88, "receiving_tds": 1}])
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX)

    assert result.data is not None
    assert result.data.position == "WR"
    game = result.data.games[0]
    assert game.opponent == "DAL"
    assert game.stats["receptions"] == 7
    assert game.stats["receiving_yards"] == 88


def test_game_stats_carry_fantasy_points_regardless_of_position(monkeypatch):
    df = _stats_df(
        [{"week": 1, "position": "QB", "fantasy_points": 20.5, "fantasy_points_ppr": 21.5}]
    )
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX)

    assert result.data is not None
    assert result.data.games[0].stats["fantasy_points"] == 20.5
    assert result.data.games[0].stats["fantasy_points_ppr"] == 21.5


def test_excludes_games_at_or_after_target_week(monkeypatch):
    df = _stats_df([{"week": w} for w in [10, 11, 12, 13]])
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX)

    assert result.data is not None
    assert [game.week for game in result.data.games] == [10, 11]


def test_filters_out_other_players_and_non_regular_season(monkeypatch):
    df = _stats_df(
        [
            {"week": 1, "player_id": "someone-else"},
            {"week": 2, "season_type": "POST"},
        ]
    )
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    result = recent_stats(CTX)

    assert result.status == "empty"
    assert result.data is None


def test_error_status_when_fetch_raises(monkeypatch):
    def _raise(season, summary_level):
        raise RuntimeError("network down")

    monkeypatch.setattr(recent_stats_module, "load_player_stats", _raise)

    result = recent_stats(CTX)

    assert result.status == "error"
    assert result.data is None
    assert result.error is not None
    assert "network down" in result.error
