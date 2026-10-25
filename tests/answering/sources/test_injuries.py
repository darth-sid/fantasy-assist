import polars as pl

import ffassistant.answering.sources.injuries as injuries_module
from ffassistant.answering.models import ResolvedContext
from ffassistant.answering.sources.injuries import InjuryData, InjuryEntry, injuries

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


def _row(gsis_id, team="MIN", week=7, report_status=None, injury=None, practice=None) -> dict:
    return {
        "gsis_id": gsis_id,
        "team": team,
        "week": week,
        "report_status": report_status,
        "report_primary_injury": injury,
        "practice_status": practice,
    }


def _injuries_df(*rows: dict) -> pl.DataFrame:
    background = [
        _row("00-0000001", report_status="Out", injury="Knee", practice="Did Not Participate In Practice"),
        _row("00-0036322", week=6, report_status="Questionable", injury="Hamstring"),
        _row("00-0036322", team="DAL", week=7, report_status="Out", injury="Ankle"),
    ]
    return pl.DataFrame([*background, *rows], schema_overrides={"report_status": pl.String})


def _run(monkeypatch, df: pl.DataFrame):
    monkeypatch.setattr(injuries_module, "load_injuries", lambda season: df)
    return injuries(CTX)


def test_designated_player(monkeypatch):
    df = _injuries_df(
        _row(
            "00-0036322",
            report_status="Questionable",
            injury="Groin",
            practice="Limited Participation in Practice",
        )
    )

    result = _run(monkeypatch, df)

    assert result.status == "ok"
    assert result.data == InjuryData(
        week=7,
        entry=InjuryEntry(
            report_status="Questionable",
            primary_injury="Groin",
            practice_status="Limited Participation in Practice",
        ),
    )


def test_listed_without_designation(monkeypatch):
    df = _injuries_df(_row("00-0036322", practice="Full Participation in Practice"))

    result = _run(monkeypatch, df)

    assert result.status == "ok"
    assert result.data.entry == InjuryEntry(
        report_status=None, primary_injury=None, practice_status="Full Participation in Practice"
    )


def test_team_reported_player_absent(monkeypatch):
    result = _run(monkeypatch, _injuries_df())

    assert result.status == "ok"
    assert result.data == InjuryData(week=7, entry=None)


def test_team_with_no_rows_is_empty(monkeypatch):
    df = _injuries_df().filter(~((pl.col("team") == "MIN") & (pl.col("week") == 7)))

    result = _run(monkeypatch, df)

    assert result.status == "empty"
    assert result.source == "injuries"
    assert result.data is None


def test_error_status_when_fetch_raises(monkeypatch):
    def _raise(season):
        raise RuntimeError("network down")

    monkeypatch.setattr(injuries_module, "load_injuries", _raise)

    result = injuries(CTX)

    assert result.status == "error"
    assert result.source == "injuries"
    assert result.data is None
    assert "network down" in result.error
