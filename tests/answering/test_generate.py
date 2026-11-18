from datetime import datetime, timezone

import ffassistant.answering.generate as generate_module
from ffassistant.answering.generate import GeneratedAnswer, answer, gather_inputs
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
from tests.helpers import CFG, with_news


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
        self.generate = generate

    def query(self, request):
        return self.generate(
            model=request.model,
            system=request.system,
            user_content=request.user_content,
            output_model=request.output_model,
            max_tokens=request.max_tokens,
        )


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


def _stub_sources(monkeypatch, sched, news_calls: list) -> None:
    empty = lambda name: SourceResult(source=name, status="empty", as_of="Week 7")

    def fake_news(ctx, opponent, cutoff, cfg):
        news_calls.append((opponent, cutoff))
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

    [inputs] = gather_inputs(_validated(), CFG, now=NOW)

    assert calls == [("IND", NOW)]
    assert inputs.news.source == "news"


def test_gather_inputs_skips_news_on_bye(monkeypatch):
    calls = []
    _stub_sources(monkeypatch, _schedule(None, opponent=None), calls)

    [inputs] = gather_inputs(_validated(), CFG, now=NOW)

    assert calls == []
    assert inputs.news is None


def test_gather_inputs_skips_news_when_schedule_fails(monkeypatch):
    calls = []
    failed = SourceResult(source="schedule", status="error", as_of="Week 7", error="boom")
    _stub_sources(monkeypatch, failed, calls)

    [inputs] = gather_inputs(_validated(), CFG, now=NOW)

    assert calls == []
    assert inputs.news is None


def test_citations_come_from_every_bucket_and_hallucinated_ids_are_dropped(monkeypatch):
    _stub_sources(monkeypatch, _schedule("2026-10-25T17:00:00+00:00"), [])
    def entry(doc_id: str) -> NewsEntry:
        return NewsEntry(
            doc_id=doc_id,
            source="rotowire",
            published_at="2026-10-19T15:00:00+00:00",
            title=f"Title {doc_id}",
            summary="",
            url=f"https://example.com/{doc_id}",
        )

    data = NewsData(
        cutoff=NOW.isoformat(), player=[entry("p")], team=[entry("t")], opponent=[entry("o")]
    )
    news_result = SourceResult(source="news", status="ok", as_of=NOW.isoformat(), data=data)
    monkeypatch.setattr(generate_module, "news", lambda ctx, opponent, cutoff, cfg: news_result)
    reply = StructuredResponse(
        parsed=GeneratedAnswer(answer="Start.", cited_doc_ids=["o", "fake", "p", "t"]), usage=None
    )
    monkeypatch.setattr(
        generate_module, "get_llm_client", lambda llm: FakeClient(lambda **kwargs: reply)
    )

    result = answer(_validated(), CFG, now=NOW)

    assert [citation.doc_id for citation in result.citations] == ["o", "p", "t"]
    assert result.citations[0] == Citation(
        doc_id="o",
        title="Title o",
        published_at="2026-10-19T15:00:00+00:00",
        url="https://example.com/o",
    )


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
    monkeypatch.setattr(generate_module, "get_llm_client", lambda llm: FakeClient(fake_generate))

    result = answer(_validated(), CFG)

    inputs = PlayerInputs(
        ctx=ctx,
        recent_stats=empty("recent_stats"),
        schedule=empty("schedule"),
        defense=empty("defense"),
        injuries=empty("injuries"),
        news=None,
    )
    assert result == Answer(answer="Start **Lamb**.", citations=[])
    assert seen["context"] == generate_module.render_context(_validated(), [inputs], CFG)


def test_debug_prints_news_ranking_block(monkeypatch, capsys):
    _stub_sources(monkeypatch, _schedule("2026-10-25T17:00:00+00:00"), [])

    def entry(doc_id: str, score: float, day: int) -> NewsEntry:
        return NewsEntry(
            doc_id=doc_id,
            source="espn",
            published_at=f"2026-10-{day:02d}T15:00:00+00:00",
            title=f"Title {doc_id}",
            summary="",
            url=f"https://example.com/{doc_id}",
            score=score,
        )

    data = NewsData(
        cutoff=NOW.isoformat(),
        player=[],
        team=[entry("newer-low", 1.5, 19), entry("older-high", 4.25, 15)],
        opponent=[],
    )
    news_result = SourceResult(source="news", status="ok", as_of=NOW.isoformat(), data=data)
    monkeypatch.setattr(generate_module, "news", lambda ctx, opponent, cutoff, cfg: news_result)
    monkeypatch.setattr(generate_module, "news_query", lambda ctx, opp, bucket, cfg: f"q-{bucket}-{opp}")
    reply = StructuredResponse(parsed=GeneratedAnswer(answer="ok", cited_doc_ids=[]), usage=None)
    monkeypatch.setattr(generate_module, "get_llm_client", lambda llm: FakeClient(lambda **kw: reply))

    answer(_validated(), with_news(ranker="bm25"), debug=True, now=NOW)

    out = capsys.readouterr().out
    block = out[out.index("--- News ranking ---") : out.index("--- Answer context ---")]
    assert block.splitlines() == [
        "--- News ranking ---",
        "## CeeDee Lamb (DAL)",
        "DAL team news (bm25): q-team-IND",
        "  4.25  2026-10-15  Title older-high",
        "  1.50  2026-10-19  Title newer-low",
        "Opponent (IND) news (bm25): q-opponent-IND",
        "  (none selected)",
        "--------------------",
        "",
    ]


def test_debug_ranking_block_notes_unfetched_news(monkeypatch, capsys):
    _stub_sources(monkeypatch, _schedule(None, opponent=None), [])
    reply = StructuredResponse(parsed=GeneratedAnswer(answer="ok", cited_doc_ids=[]), usage=None)
    monkeypatch.setattr(generate_module, "get_llm_client", lambda llm: FakeClient(lambda **kw: reply))

    answer(_validated(), CFG, debug=True, now=NOW)

    assert "## CeeDee Lamb (DAL)\nnews: not fetched\n" in capsys.readouterr().out
