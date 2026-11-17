import polars as pl

import ffassistant.ingest.gazetteer as gazetteer_module
from ffassistant.ingest.gazetteer import load_gazetteer, name_key


def _rosters() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"gsis_id": "00-1", "full_name": "Josh Allen", "position": "QB", "team": "BUF", "week": 10},
            {"gsis_id": "00-2", "full_name": "Josh Allen", "position": "LB", "team": "JAX", "week": 10},
            {"gsis_id": "00-3", "full_name": "Sauce Gardner", "position": "CB", "team": "NYJ", "week": 9},
            {"gsis_id": "00-3", "full_name": "Sauce Gardner", "position": "CB", "team": "IND", "week": 10},
            {"gsis_id": "00-4", "full_name": "Joe Thuney", "position": "OL", "team": "CHI", "week": 10},
            {"gsis_id": "00-5", "full_name": "Marvin Harrison Jr.", "position": "WR", "team": "ARI", "week": 10},
            {"gsis_id": None, "full_name": "No Id", "position": "WR", "team": "ARI", "week": 10},
            {"gsis_id": "00-6", "full_name": "Filler", "position": "WR", "team": "WAS", "week": 10},
            {"gsis_id": "00-7", "full_name": "Filler", "position": "WR", "team": "NYG", "week": 10},
            {"gsis_id": "00-8", "full_name": "Filler", "position": "WR", "team": "LA", "week": 10},
            {"gsis_id": "00-9", "full_name": "Filler", "position": "WR", "team": "LAC", "week": 10},
        ]
    )


def _teams() -> pl.DataFrame:
    rows = [
        ("ARI", "Arizona Cardinals", "Cardinals"),
        ("BUF", "Buffalo Bills", "Bills"),
        ("CHI", "Chicago Bears", "Bears"),
        ("IND", "Indianapolis Colts", "Colts"),
        ("JAX", "Jacksonville Jaguars", "Jaguars"),
        ("LA", "Los Angeles Rams", "Rams"),
        ("LAC", "Los Angeles Chargers", "Chargers"),
        ("LAR", "Los Angeles Rams", "Rams"),
        ("NYG", "New York Giants", "Giants"),
        ("NYJ", "New York Jets", "Jets"),
        ("STL", "St. Louis Rams", "Rams"),
        ("WAS", "Washington Commanders", "Commanders"),
    ]
    return pl.DataFrame(
        [{"team_abbr": a, "team_name": n, "team_nick": k} for a, n, k in rows]
    )


def _gazetteer(monkeypatch):
    monkeypatch.setattr(gazetteer_module, "load_rosters", lambda season: _rosters())
    monkeypatch.setattr(gazetteer_module, "load_teams", _teams)
    return load_gazetteer(2026)


def test_every_position_is_included(monkeypatch):
    players = _gazetteer(monkeypatch).players

    assert players["joe thuney"] == [("00-4", "CHI")]


def test_latest_roster_row_per_player(monkeypatch):
    assert _gazetteer(monkeypatch).players["sauce gardner"] == [("00-3", "IND")]


def test_name_clash_maps_to_every_player(monkeypatch):
    assert _gazetteer(monkeypatch).players["josh allen"] == [("00-1", "BUF"), ("00-2", "JAX")]


def test_player_keys_drop_suffix(monkeypatch):
    assert _gazetteer(monkeypatch).players["marvin harrison"] == [("00-5", "ARI")]


def test_team_name_and_nickname_are_aliases(monkeypatch):
    teams = _gazetteer(monkeypatch).teams

    assert teams["washington commanders"] == "WAS"
    assert teams["commanders"] == "WAS"


def test_city_alias_only_when_unique(monkeypatch):
    teams = _gazetteer(monkeypatch).teams

    assert teams["washington"] == "WAS"
    assert "new york" not in teams
    assert "los angeles" not in teams


def test_abbreviations_are_not_aliases(monkeypatch):
    teams = _gazetteer(monkeypatch).teams

    assert "was" not in teams and "buf" not in teams


def test_only_current_teams(monkeypatch):
    teams = _gazetteer(monkeypatch).teams

    assert teams["rams"] == "LA"
    assert "st louis rams" not in teams
    assert "LAR" not in teams.values()


def test_name_key():
    assert name_key("A.J. Brown") == name_key("AJ Brown") == "aj brown"
    assert name_key("Marvin Harrison Jr.") == "marvin harrison"
    assert name_key("Ja’Marr  Chase") == "ja'marr chase"
