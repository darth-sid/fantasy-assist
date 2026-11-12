import ffassistant.resolution.extract as extract_module
from ffassistant.clients.llm_client import StructuredResponse, TokenUsage
from ffassistant.config import PARSER_MODEL, SEASON
from ffassistant.resolution.extract import extract
from ffassistant.resolution.models import ExtractedPlayer, ExtractedRequest
from ffassistant.resolution.roster import RosterPlayer

CURRENT_WEEK = 11

ROSTER = {
    "00-1": RosterPlayer(
        gsis_id="00-1", full_name="CeeDee Lamb", team="DAL", position="WR", status="ACT"
    ),
}
PARSED = ExtractedRequest(
    players=[
        ExtractedPlayer(mention="CeeDee Lam", player_id="00-1"),
        ExtractedPlayer(mention="Joe Nobody", player_id=None),
    ],
    week=7,
    scoring_format=None,
)
USAGE = TokenUsage(input_tokens=40, output_tokens=30, cache_write_tokens=0, cache_read_tokens=21132)


class FakeClient:
    def __init__(self, calls: dict):
        self.calls = calls

    def generate_structured(self, model, system, user_content, output_model, max_tokens):
        self.calls.update(
            model=model, system=system, user_content=user_content, output_model=output_model
        )
        return StructuredResponse(parsed=PARSED, usage=USAGE)


def _run(monkeypatch, debug: bool = False) -> tuple[ExtractedRequest, dict]:
    calls = {}

    monkeypatch.setattr(extract_module, "load_fantasy_roster", lambda season: ROSTER)
    monkeypatch.setattr(extract_module, "get_llm_client", lambda: FakeClient(calls))
    return extract("CeeDee Lam this week?", CURRENT_WEEK, debug=debug), calls


def test_returns_parsed_output(monkeypatch):
    result, calls = _run(monkeypatch)

    assert result == PARSED
    assert calls["output_model"] is ExtractedRequest
    assert calls["model"] == PARSER_MODEL
    assert calls["user_content"] == "CeeDee Lam this week?"


def test_system_blocks_use_passed_in_current_week(monkeypatch):
    _, calls = _run(monkeypatch)

    text = "\n".join(block.text for block in calls["system"])
    assert f"Season: {SEASON}" in text
    assert f"Current week: {CURRENT_WEEK}" in text
    assert f'"next week" = {CURRENT_WEEK + 1}' in text


def test_roster_is_its_own_cached_block(monkeypatch):
    _, calls = _run(monkeypatch)

    cached = [b for b in calls["system"] if b.cache]
    assert len(cached) == 1
    assert "00-1 | CeeDee Lamb | DAL | WR | ACT" in cached[0].text


def test_debug_prints_extraction_and_cache_usage(monkeypatch, capsys):
    _run(monkeypatch, debug=True)

    lines = capsys.readouterr().out.splitlines()
    assert '"CeeDee Lam" -> 00-1' in lines
    assert '"Joe Nobody" -> null' in lines
    assert "week: 7" in lines
    assert "scoring_format: null" in lines
    assert "cache_write_tokens=0, cache_read_tokens=21132" in lines


def test_no_debug_output_by_default(monkeypatch, capsys):
    _run(monkeypatch)

    assert capsys.readouterr().out == ""
