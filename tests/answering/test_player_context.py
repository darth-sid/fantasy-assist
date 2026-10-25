import polars as pl

import ffassistant.answering.player_context as player_context_module
from ffassistant.answering.player_context import player_context
from ffassistant.resolution.models import ValidPlayer

PLAYER = ValidPlayer(
    mention="Kirk", player_id="00-0031408", full_name="Kirk Cousins", position="QB"
)


def _rosters(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame([{"position": "QB", "full_name": "Kirk Cousins", **row} for row in rows])


def _patch(monkeypatch, df):
    monkeypatch.setattr(player_context_module, "load_rosters", lambda season: df)


def test_builds_context_from_valid_player(monkeypatch):
    _patch(monkeypatch, _rosters([{"gsis_id": "00-0031408", "team": "ATL", "week": 1}]))

    ctx = player_context(PLAYER, season=2026, week=7, scoring_format="Half-PPR")

    assert ctx.player_id == "00-0031408"
    assert ctx.player_name == "Kirk Cousins"
    assert ctx.position == "QB"
    assert ctx.team == "ATL"
    assert (ctx.season, ctx.week, ctx.scoring_format) == (2026, 7, "Half-PPR")


def test_team_is_latest_row_at_or_before_target_week(monkeypatch):
    _patch(
        monkeypatch,
        _rosters(
            [
                {"gsis_id": "00-0031408", "team": "ATL", "week": 1},
                {"gsis_id": "00-0031408", "team": "MIN", "week": 5},
                {"gsis_id": "00-0031408", "team": "NYJ", "week": 12},
                {"gsis_id": "00-9999999", "team": "SEA", "week": 6},
            ]
        ),
    )

    assert player_context(PLAYER, 2026, 4, "PPR").team == "ATL"
    assert player_context(PLAYER, 2026, 5, "PPR").team == "MIN"
    assert player_context(PLAYER, 2026, 11, "PPR").team == "MIN"
    assert player_context(PLAYER, 2026, 12, "PPR").team == "NYJ"


def test_falls_back_to_earliest_row_when_none_before_target_week(monkeypatch):
    _patch(
        monkeypatch,
        _rosters(
            [
                {"gsis_id": "00-0031408", "team": "NYJ", "week": 12},
                {"gsis_id": "00-0031408", "team": "MIN", "week": 9},
            ]
        ),
    )

    assert player_context(PLAYER, 2026, 3, "PPR").team == "MIN"
