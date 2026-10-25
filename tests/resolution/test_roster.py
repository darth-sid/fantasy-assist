import polars as pl

import ffassistant.resolution.roster as roster_module
from ffassistant.resolution.roster import RosterPlayer, load_fantasy_roster, render_roster


def _rosters(rows: list[dict]) -> pl.DataFrame:
    base = {"position": "WR", "status": "ACT", "team": "DAL", "week": 1}
    return pl.DataFrame([{**base, **row} for row in rows])


def _load(monkeypatch, rows: list[dict]) -> dict[str, RosterPlayer]:
    monkeypatch.setattr(roster_module, "load_rosters", lambda season: _rosters(rows))
    return load_fantasy_roster(2026)


def test_keeps_latest_row_per_player(monkeypatch):
    roster = _load(
        monkeypatch,
        [
            {"gsis_id": "00-1", "full_name": "Kirk Cousins", "team": "ATL", "week": 1},
            {"gsis_id": "00-1", "full_name": "Kirk Cousins", "team": "NYJ", "week": 9},
            {"gsis_id": "00-1", "full_name": "Kirk Cousins", "team": "MIN", "week": 4},
        ],
    )

    assert list(roster) == ["00-1"]
    assert roster["00-1"].team == "NYJ"


def test_includes_every_status(monkeypatch):
    roster = _load(
        monkeypatch,
        [
            {"gsis_id": "00-1", "full_name": "Active Guy", "status": "ACT"},
            {"gsis_id": "00-2", "full_name": "Reserve Guy", "status": "RES"},
            {"gsis_id": "00-3", "full_name": "Cut Guy", "status": "CUT"},
        ],
    )

    assert {p.status for p in roster.values()} == {"ACT", "RES", "CUT"}


def test_filters_to_fantasy_positions(monkeypatch):
    roster = _load(
        monkeypatch,
        [
            {"gsis_id": "00-1", "full_name": "Justin Jefferson", "position": "WR"},
            {"gsis_id": "00-2", "full_name": "Justin Jefferson", "position": "LB"},
            {"gsis_id": "00-3", "full_name": "Some Punter", "position": "P"},
            {"gsis_id": "00-4", "full_name": "Brandon Aubrey", "position": "K"},
        ],
    )

    assert set(roster) == {"00-1", "00-4"}


def test_lookup_by_gsis_id(monkeypatch):
    roster = _load(
        monkeypatch,
        [{"gsis_id": "00-1", "full_name": "CeeDee Lamb", "team": "DAL", "position": "WR"}],
    )

    assert roster["00-1"] == RosterPlayer(
        gsis_id="00-1", full_name="CeeDee Lamb", team="DAL", position="WR", status="ACT"
    )
    assert "00-9" not in roster


def test_render_one_line_per_player(monkeypatch):
    roster = _load(
        monkeypatch,
        [
            {"gsis_id": "00-1", "full_name": "CeeDee Lamb", "team": "DAL"},
            {"gsis_id": "00-2", "full_name": "A.J. Brown", "team": "PHI", "status": "RES"},
        ],
    )

    assert render_roster(roster).splitlines() == [
        "gsis_id | full_name | team | position | status",
        "00-2 | A.J. Brown | PHI | WR | RES",
        "00-1 | CeeDee Lamb | DAL | WR | ACT",
    ]
