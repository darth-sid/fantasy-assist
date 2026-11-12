from datetime import datetime, timezone

import ffassistant.answering.generate as generate_module
from ffassistant.answering.generate import GeneratedAnswer, answer, gather_inputs, news_cutoff
from ffassistant.answering.models import (
    Answer,
    Citation,
    PlayerInputs,
    ResolvedContext,
    SourceResult,
)
from ffassistant.answering.sources.news import NewsData, NewsEntry
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from ffassistant.clients.llm_client import StructuredResponse
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


CTX = ResolvedContext(
    player_id="00-1",
    player_name="CeeDee Lamb",
    team="DAL",
    position="WR",
    roster_status="ACT",
    season=2026,
    week=7,
    scoring_format="PPR",
)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, generate):
        self.generate_structured = generate


def _schedule(kickoff: str | None, opponent: str | None = "IND") -> SourceResult[ScheduleData]:
    byes = [
        ScheduleWeek(week=w, opponent=None, home=None, played=False, kickoff=None)
        for w in range(1, 7)
    ]
    target = ScheduleWeek(week=7, opponent=opponent, home=True, played=False, kickoff=kickoff)
    return SourceResult(
        source="schedule",
        status="ok",
        as_of="Week 7",
        data=ScheduleData(team="DAL", weeks=[*byes, target]),
    )


def test_cutoff_is_now_before_kickoff():
    assert news_cutoff(_schedule("2026-10-25T17:00:00+00:00"), 7, NOW) == NOW


def test_cutoff_is_kickoff_after_kickoff():
    kickoff = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)

    assert news_cutoff(_schedule(kickoff.isoformat()), 7, NOW) == kickoff


def test_no_cutoff_on_bye():
    assert news_cutoff(_schedule(None, opponent=None), 7, NOW) is None


def test_no_cutoff_when_schedule_fails():
    failed = SourceResult(source="schedule", status="error", as_of="Week 7", error="boom")

    assert news_cutoff(failed, 7, NOW) is None


def _stub_sources(monkeypatch, sched, news_calls: list) -> None:
    empty = lambda name: SourceResult(source=name, status="empty", as_of="Week 7")

    def fake_news(ctx, cutoff):
        news_calls.append(cutoff)
        return empty("news")

    monkeypatch.setattr(generate_module, "player_context", lambda player, season, week, fmt: CTX)
    monkeypatch.setattr(generate_module, "recent_stats", lambda ctx: empty("recent_stats"))
    monkeypatch.setattr(generate_module, "schedule", lambda ctx: sched)
    monkeypatch.setattr(generate_module, "defense", lambda ctx: empty("defense"))
    monkeypatch.setattr(generate_module, "injuries", lambda ctx: empty("injuries"))
    monkeypatch.setattr(generate_module, "news", fake_news)


def test_gather_inputs_fetches_news_with_cutoff(monkeypatch):
    calls = []
    _stub_sources(monkeypatch, _schedule("2026-10-25T17:00:00+00:00"), calls)

    [inputs] = gather_inputs(_validated(), now=NOW)

    assert calls == [NOW]
    assert inputs.news.source == "news"


def test_gather_inputs_skips_news_on_bye(monkeypatch):
    calls = []
    _stub_sources(monkeypatch, _schedule(None, opponent=None), calls)

    [inputs] = gather_inputs(_validated(), now=NOW)

    assert calls == []
    assert inputs.news is None


def test_gather_inputs_skips_news_when_schedule_fails(monkeypatch):
    calls = []
    failed = SourceResult(source="schedule", status="error", as_of="Week 7", error="boom")
    _stub_sources(monkeypatch, failed, calls)

    [inputs] = gather_inputs(_validated(), now=NOW)

    assert calls == []
    assert inputs.news is None


def test_hallucinated_cited_ids_are_dropped(monkeypatch):
    _stub_sources(monkeypatch, _schedule("2026-10-25T17:00:00+00:00"), [])
    entry = NewsEntry(
        doc_id="real",
        source="rotowire",
        published_at="2026-10-19T15:00:00+00:00",
        title="CeeDee Lamb: Practices fully",
        summary="",
        url="https://example.com/real",
    )
    news_result = SourceResult(
        source="news",
        status="ok",
        as_of=NOW.isoformat(),
        data=NewsData(cutoff=NOW.isoformat(), items=[entry]),
    )
    monkeypatch.setattr(generate_module, "news", lambda ctx, cutoff: news_result)
    reply = StructuredResponse(
        parsed=GeneratedAnswer(answer="Start.", cited_doc_ids=["fake", "real"]), usage=None
    )
    monkeypatch.setattr(
        generate_module, "get_llm_client", lambda: FakeClient(lambda **kwargs: reply)
    )

    result = answer(_validated(), now=NOW)

    assert result.citations == [
        Citation(
            doc_id="real",
            title="CeeDee Lamb: Practices fully",
            published_at="2026-10-19T15:00:00+00:00",
            url="https://example.com/real",
        )
    ]


def test_answer_runs_sources_and_returns_generated_output(monkeypatch):
    ctx = CTX
    empty = lambda name: SourceResult(source=name, status="empty", as_of="Week 7")
    seen = {}

    def fake_generate(model, system, user_content, output_model, max_tokens):
        seen["context"] = user_content
        return StructuredResponse(
            parsed=GeneratedAnswer(answer="Start **Lamb**.", cited_doc_ids=[]), usage=None
        )

    monkeypatch.setattr(generate_module, "player_context", lambda player, season, week, fmt: ctx)
    monkeypatch.setattr(generate_module, "recent_stats", lambda ctx: empty("recent_stats"))
    monkeypatch.setattr(generate_module, "schedule", lambda ctx: empty("schedule"))
    monkeypatch.setattr(generate_module, "defense", lambda ctx: empty("defense"))
    monkeypatch.setattr(generate_module, "injuries", lambda ctx: empty("injuries"))
    monkeypatch.setattr(generate_module, "get_llm_client", lambda: FakeClient(fake_generate))

    result = answer(_validated())

    inputs = PlayerInputs(
        ctx=ctx,
        recent_stats=empty("recent_stats"),
        schedule=empty("schedule"),
        defense=empty("defense"),
        injuries=empty("injuries"),
        news=None,
    )
    assert result == Answer(answer="Start **Lamb**.", citations=[])
    assert seen["context"] == generate_module.render_context(_validated(), [inputs])
