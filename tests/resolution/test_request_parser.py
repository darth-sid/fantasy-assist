import pytest

import ffassistant.resolution.request_parser as request_parser_module
from ffassistant.clients.anthropic_client import ExtractedRequest
from ffassistant.config import CURRENT_WEEK
from ffassistant.resolution.request_parser import NoPlayersFoundError, parse_request


def test_explicit_values_pass_through_unchanged(monkeypatch):
    extracted = ExtractedRequest(player_names=["CeeDee Lamb"], week=8, scoring_format="Standard")
    monkeypatch.setattr(request_parser_module, "extract_request", lambda prompt: extracted)

    result = parse_request("some prompt")

    assert result.player_names == ["CeeDee Lamb"]
    assert result.week == 8
    assert result.scoring_format == "Standard"
    assert result.raw_prompt == "some prompt"


def test_week_defaults_to_current_week_when_none(monkeypatch):
    extracted = ExtractedRequest(player_names=["CeeDee Lamb"], week=None, scoring_format="PPR")
    monkeypatch.setattr(request_parser_module, "extract_request", lambda prompt: extracted)

    result = parse_request("some prompt")

    assert result.week == CURRENT_WEEK


def test_scoring_format_defaults_to_ppr_when_none(monkeypatch):
    extracted = ExtractedRequest(player_names=["CeeDee Lamb"], week=8, scoring_format=None)
    monkeypatch.setattr(request_parser_module, "extract_request", lambda prompt: extracted)

    result = parse_request("some prompt")

    assert result.scoring_format == "PPR"


def test_raises_when_no_players_found(monkeypatch):
    extracted = ExtractedRequest(player_names=[], week=None, scoring_format=None)
    monkeypatch.setattr(request_parser_module, "extract_request", lambda prompt: extracted)

    with pytest.raises(NoPlayersFoundError):
        parse_request("some prompt")
