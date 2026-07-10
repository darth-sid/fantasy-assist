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

    block = recent_stats(CTX)

    assert block.status == "ok"
    assert block.source == "recent_stats"
    wk1_idx = block.content.index("Wk 1")
    wk2_idx = block.content.index("Wk 2")
    assert wk1_idx < wk2_idx
    assert "(2 games)" in block.content


def test_last_n_caps_to_most_recent_games(monkeypatch):
    df = _stats_df([{"week": w} for w in range(1, 6)])
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    block = recent_stats(CTX, last_n=2)

    assert "(2 games)" in block.content
    assert "Wk 4" in block.content
    assert "Wk 5" in block.content
    assert "Wk 1" not in block.content


def test_filters_out_other_players_and_non_regular_season(monkeypatch):
    df = _stats_df(
        [
            {"week": 1, "player_id": "someone-else"},
            {"week": 2, "season_type": "POST"},
        ]
    )
    monkeypatch.setattr(recent_stats_module, "load_player_stats", lambda season, summary_level: df)

    block = recent_stats(CTX)

    assert block.status == "empty"
    assert CTX.player_name in block.content


def test_error_status_when_fetch_raises(monkeypatch):
    def _raise(season, summary_level):
        raise RuntimeError("network down")

    monkeypatch.setattr(recent_stats_module, "load_player_stats", _raise)

    block = recent_stats(CTX)

    assert block.status == "error"
    assert "fetch failed" in block.content
