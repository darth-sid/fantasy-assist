import ffassistant.resolution.extract as extract_module
from ffassistant.config import CURRENT_WEEK, PARSER_MODEL, SEASON
from ffassistant.resolution.extract import extract
from ffassistant.resolution.models import ExtractedPlayer, ExtractedRequest
from ffassistant.resolution.roster import RosterPlayer

ROSTER = {
    "00-1": RosterPlayer(
        gsis_id="00-1", full_name="CeeDee Lamb", team="DAL", position="WR", status="ACT"
    ),
}
PARSED = ExtractedRequest(
    players=[ExtractedPlayer(mention="CeeDee Lam", player_id="00-1")],
    week=7,
    scoring_format="PPR",
)


def _run(monkeypatch) -> tuple[ExtractedRequest, dict]:
    calls = {}

    def fake_parse_structured(model, system, user_content, output_model, max_tokens):
        calls.update(model=model, system=system, user_content=user_content, output_model=output_model)
        return PARSED

    monkeypatch.setattr(extract_module, "load_fantasy_roster", lambda season: ROSTER)
    monkeypatch.setattr(extract_module, "parse_structured", fake_parse_structured)
    return extract("CeeDee Lam this week?"), calls


def test_returns_parsed_output(monkeypatch):
    result, calls = _run(monkeypatch)

    assert result == PARSED
    assert calls["output_model"] is ExtractedRequest
    assert calls["model"] == PARSER_MODEL
    assert calls["user_content"] == "CeeDee Lam this week?"


def test_system_blocks_include_season_and_current_week(monkeypatch):
    _, calls = _run(monkeypatch)

    text = "\n".join(block["text"] for block in calls["system"])
    assert f"Season: {SEASON}" in text
    assert f"Current week: {CURRENT_WEEK}" in text


def test_roster_is_its_own_cached_block(monkeypatch):
    _, calls = _run(monkeypatch)

    roster_blocks = [b for b in calls["system"] if "00-1 | CeeDee Lamb | DAL | WR | ACT" in b["text"]]
    assert len(roster_blocks) == 1
    assert roster_blocks[0]["cache_control"] == {"type": "ephemeral"}
