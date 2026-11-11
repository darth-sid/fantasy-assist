import polars as pl

import ffassistant.answering.sources.schedule as schedule_module
from ffassistant.answering.models import ResolvedContext
from ffassistant.answering.sources.schedule import ScheduleWeek, schedule

CTX = ResolvedContext(
    player_id="00-0036322",
    player_name="Justin Jefferson",
    team="MIN",
    position="WR",
    roster_status="ACT",
    season=2026,
    week=7,
    scoring_format="PPR",
)


def _game(week, home_team, away_team, result, game_type="REG", gameday=None, gametime="13:00"):
    return {
        "game_type": game_type,
        "week": week,
        "home_team": home_team,
        "away_team": away_team,
        "result": result,
        "gameday": gameday or f"2026-10-{week + 10:02d}",
        "gametime": gametime,
    }


def _schedules_df() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _game(1, "MIN", "CHI", 7),
            _game(2, "ATL", "MIN", -3),
            _game(3, "MIN", "CIN", 10),
            _game(4, "MIA", "MIN", 4),
            _game(5, "MIN", "CLE", 1),
            _game(6, "SF", "MIN", None),
            _game(7, "MIN", "IND", None),
            _game(8, "DET", "MIN", None),
            _game(3, "DAL", "NYG", 3),
            _game(19, "MIN", "GB", None, game_type="WC"),
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

    assert weeks[1] == ScheduleWeek(
        week=1, opponent="CHI", home=True, played=True, kickoff="2026-10-11T17:00:00+00:00"
    )


def test_played_away_game(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[4] == ScheduleWeek(
        week=4, opponent="MIA", home=False, played=True, kickoff="2026-10-14T17:00:00+00:00"
    )


def test_bye_week(monkeypatch):
    df = _schedules_df().filter(pl.col("week") != 5)

    weeks = _weeks(monkeypatch, df)

    assert weeks[5] == ScheduleWeek(week=5, opponent=None, home=None, played=False, kickoff=None)


def test_unplayed_upcoming_week(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[7] == ScheduleWeek(
        week=7, opponent="IND", home=True, played=False, kickoff="2026-10-17T17:00:00+00:00"
    )


def test_unplayed_past_week(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df())

    assert weeks[6] == ScheduleWeek(
        week=6, opponent="SF", home=False, played=False, kickoff="2026-10-16T17:00:00+00:00"
    )


def _kickoff_for_week_7(monkeypatch, gameday: str, gametime: str | None) -> str | None:
    df = _schedules_df().filter(pl.col("week") != 7)
    df = pl.concat([df, pl.DataFrame([_game(7, "MIN", "IND", None, gameday=gameday, gametime=gametime)])])
    return _weeks(monkeypatch, df)[7].kickoff


def test_kickoff_converts_eastern_daylight_time_to_utc(monkeypatch):
    assert _kickoff_for_week_7(monkeypatch, "2026-10-25", "13:00") == "2026-10-25T17:00:00+00:00"


def test_kickoff_converts_eastern_standard_time_to_utc(monkeypatch):
    assert _kickoff_for_week_7(monkeypatch, "2026-11-08", "13:00") == "2026-11-08T18:00:00+00:00"


def test_kickoff_evening_game_rolls_into_next_utc_day(monkeypatch):
    assert _kickoff_for_week_7(monkeypatch, "2026-11-09", "20:15") == "2026-11-10T01:15:00+00:00"


def test_kickoff_null_gametime_uses_eastern_midnight(monkeypatch):
    assert _kickoff_for_week_7(monkeypatch, "2026-11-08", None) == "2026-11-08T05:00:00+00:00"


def test_kickoff_null_on_bye(monkeypatch):
    weeks = _weeks(monkeypatch, _schedules_df().filter(pl.col("week") != 5))

    assert weeks[5].kickoff is None


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
