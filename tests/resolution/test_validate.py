import pytest

import ffassistant.config as config
import ffassistant.resolution.validate as validate_module
from ffassistant.config import DEFAULT_SCORING_FORMAT, SEASON
from ffassistant.resolution.models import (
    ExtractedPlayer,
    ExtractedRequest,
    RejectedMention,
    RequestValidationError,
    ValidPlayer,
)
from ffassistant.resolution.roster import RosterPlayer
from ffassistant.resolution.validate import validate

CURRENT_WEEK = 11

ROSTER = {
    "00-1": RosterPlayer(
        gsis_id="00-1", full_name="CeeDee Lamb", team="DAL", position="WR", status="ACT"
    ),
    "00-2": RosterPlayer(
        gsis_id="00-2", full_name="A.J. Brown", team="PHI", position="WR", status="RES"
    ),
}


@pytest.fixture(autouse=True)
def _roster(monkeypatch):
    monkeypatch.setattr(validate_module, "load_fantasy_roster", lambda season: ROSTER)


def _extracted(players=None, week=7, scoring_format="PPR") -> ExtractedRequest:
    if players is None:
        players = [("CeeDee Lamb", "00-1")]
    return ExtractedRequest(
        players=[ExtractedPlayer(mention=m, player_id=pid) for m, pid in players],
        week=week,
        scoring_format=scoring_format,
    )


def _errors(extracted: ExtractedRequest) -> list[str]:
    with pytest.raises(RequestValidationError) as exc_info:
        validate(extracted, "prompt", CURRENT_WEEK)
    return exc_info.value.errors


def test_valid_request():
    extracted = _extracted(players=[("AJ Brown", "00-2")], week=9, scoring_format="Half-PPR")
    result = validate(extracted, "AJ?", CURRENT_WEEK)

    assert result.raw_prompt == "AJ?"
    assert result.season == SEASON
    assert result.week == 9
    assert result.scoring_format == "Half-PPR"
    assert result.players == [
        ValidPlayer(mention="AJ Brown", player_id="00-2", full_name="A.J. Brown", position="WR")
    ]
    assert result.rejected == []


def test_defaults_week_and_scoring_format():
    result = validate(_extracted(week=None, scoring_format=None), "prompt", CURRENT_WEEK)

    assert result.week == CURRENT_WEEK
    assert result.scoring_format == DEFAULT_SCORING_FORMAT


def test_default_week_is_the_passed_in_current_week():
    assert validate(_extracted(week=None), "prompt", 3).week == 3
    assert validate(_extracted(week=None), "prompt", 14).week == 14


def test_config_has_no_current_week_pin():
    assert not hasattr(config, "CURRENT_WEEK")


def test_no_players_raises():
    errors = _errors(_extracted(players=[]))

    assert errors == ["no players found in the request"]


@pytest.mark.parametrize("week", [0, 19, 25, -1])
def test_week_outside_regular_season_raises(week):
    errors = _errors(_extracted(week=week))

    assert errors == [f"week {week} is outside the regular season (1 to 18)"]


@pytest.mark.parametrize("week", [1, 18])
def test_week_bounds_are_inclusive(week):
    assert validate(_extracted(week=week), "prompt", CURRENT_WEEK).week == week


def test_unknown_scoring_format_raises():
    errors = _errors(_extracted(scoring_format="Six-Point Passing TD"))

    assert len(errors) == 1
    assert "'Six-Point Passing TD'" in errors[0]


def test_request_level_errors_are_collected_together():
    errors = _errors(_extracted(players=[], week=25, scoring_format="ppr"))

    assert len(errors) == 3


def test_null_player_id_is_rejected_others_answered():
    result = validate(
        _extracted(players=[("CeeDee Lamb", "00-1"), ("Puka Nakua", None)]), "p", CURRENT_WEEK
    )

    assert [p.player_id for p in result.players] == ["00-1"]
    assert result.rejected == [RejectedMention(mention="Puka Nakua", reason="no matching player found")]


def test_hallucinated_player_id_is_rejected():
    result = validate(
        _extracted(players=[("CeeDee Lamb", "00-1"), ("Joe Nobody", "00-999")]), "p", CURRENT_WEEK
    )

    assert [p.player_id for p in result.players] == ["00-1"]
    assert result.rejected == [RejectedMention(mention="Joe Nobody", reason="unknown player id")]


def test_duplicate_player_id_keeps_first_silently():
    result = validate(
        _extracted(players=[("CeeDee", "00-1"), ("CeeDee Lamb", "00-1")]), "p", CURRENT_WEEK
    )

    assert [p.mention for p in result.players] == ["CeeDee"]
    assert result.rejected == []


def test_all_mentions_rejected_raises():
    errors = _errors(_extracted(players=[("Puka Nakua", None), ("Joe Nobody", "00-999")]))

    assert errors == [
        'could not resolve "Puka Nakua": no matching player found',
        'could not resolve "Joe Nobody": unknown player id',
    ]
