import ffassistant.answering.generate as generate_module
from ffassistant.answering.generate import GeneratedAnswer, answer
from ffassistant.answering.models import Answer, PlayerInputs, ResolvedContext, SourceResult
from ffassistant.resolution.models import ValidatedRequest, ValidPlayer


def _validated() -> ValidatedRequest:
    return ValidatedRequest(
        raw_prompt="Start Lamb?",
        season=2026,
        week=7,
        scoring_format="PPR",
        players=[
            ValidPlayer(
                mention="CeeDee Lamb", player_id="00-1", full_name="CeeDee Lamb", position="WR"
            )
        ],
        rejected=[],
    )


def test_answer_runs_sources_and_returns_generated_output(monkeypatch):
    ctx = ResolvedContext(
        player_id="00-1",
        player_name="CeeDee Lamb",
        team="DAL",
        position="WR",
        season=2026,
        week=7,
        scoring_format="PPR",
    )
    empty = lambda name: SourceResult(source=name, status="empty", as_of="Week 7")
    seen = {}

    def fake_parse_structured(model, system, user_content, output_model, max_tokens):
        seen["context"] = user_content
        return GeneratedAnswer(answer="Start **Lamb**.", cited_doc_ids=[])

    monkeypatch.setattr(generate_module, "player_context", lambda player, season, week, fmt: ctx)
    monkeypatch.setattr(generate_module, "recent_stats", lambda ctx: empty("recent_stats"))
    monkeypatch.setattr(generate_module, "schedule", lambda ctx: empty("schedule"))
    monkeypatch.setattr(generate_module, "defense", lambda ctx: empty("defense"))
    monkeypatch.setattr(generate_module, "parse_structured", fake_parse_structured)

    result = answer(_validated())

    inputs = PlayerInputs(
        ctx=ctx,
        recent_stats=empty("recent_stats"),
        schedule=empty("schedule"),
        defense=empty("defense"),
    )
    assert result == Answer(answer="Start **Lamb**.", cited_doc_ids=[])
    assert seen["context"] == generate_module.render_context(_validated(), [inputs])
