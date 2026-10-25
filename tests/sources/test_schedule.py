import polars as pl

import ffassistant.sources.schedule as schedule_module
from ffassistant.contracts import ResolvedContext
from ffassistant.sources.schedule import ScheduleWeek, schedule

CTX = ResolvedContext(
    player_id="00-0036322",
    player_name="Justin Jefferson",
    team="MIN",
    position="WR",
    season=2026,
    week=7,
    scoring_format="PPR",
)


def _schedules_df() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"game_type": "REG", "week": 1, "home_team": "MIN", "away_team": "CHI", "result": 7},
            {"game_type": "REG", "week": 2, "home_team": "ATL", "away_team": "MIN", "result": -3},
            {"game_type": "REG", "week": 3, "home_team": "MIN", "away_team": "CIN", "result": 10},
            {"game_type": "REG", "week": 4, "home_team": "MIA", "away_team": "MIN", "result": 4},
            {"game_type": "REG", "week": 5, "home_team": "MIN", "away_team": "CLE", "result": 1},
            {"game_type": "REG", "week": 6, "home_team": "SF", "away_team": "MIN", "result": None},
            {"game_type": "REG", "week": 7, "home_team": "MIN", "away_team": "IND", "result": None},
            {"game_type": "REG", "week": 8, "home_team": "DET", "away_team": "MIN", "result": None},
            {"game_type": "REG", "week": 3, "home_team": "DAL", "away_team": "NYG", "result": 3},
            {"game_type": "WC", "week": 19, "home_team": "MIN", "away_team": "GB", "result": None},
        ]
    )


def _weeks(monkeypatch, df: pl.DataFrame) -> dict[int, ScheduleWeek]:
    monkeypatch.setattr(schedule_module, "load_schedules", lambda season: df)
    result = schedule(CTX)
    assert result.status == "ok"
    assert result.data is not None
    assert result.data.team == "MIN"
    return {week.week: week for week in result.data.weeks}


def test_one_entry_per_week_through_target_week(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert sorted(weeks) == [1, 2, 3, 4, 5, 6, 7]


def test_played_home_game(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[1] == ScheduleWeek(week=1, opponent="CHI", home=True, played=True)


def test_played_away_game(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[4] == ScheduleWeek(week=4, opponent="MIA", home=False, played=True)


def test_bye_week(monkeypatch):
    df = _schedules_df().filter(pl.col("week") != 5)

    weeks = _weeks(monkeypatch, df)

    assert weeks[5] == ScheduleWeek(week=5, opponent=None, home=None, played=False)


def test_unplayed_upcoming_week(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[7] == ScheduleWeek(week=7, opponent="IND", home=True, played=False)


def test_unplayed_past_week(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[6] == ScheduleWeek(week=6, opponent="SF", home=False, played=False)


def test_error_status_when_fetch_raises(monkeypatch):
    def _raise(season):
        raise RuntimeError("network down")

    monkeypatch.setattr(schedule_module, "load_schedules", _raise)

    result = schedule(CTX)

    assert result.status == "error"
    assert result.source == "schedule"
    assert result.data is None
    assert result.error is not None
    assert "network down" in result.error
