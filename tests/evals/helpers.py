"""Shared fakes for the eval tests: two samples and a stubbed retrieval keyed by ranker."""

from datetime import datetime, timezone

import evals.pairs as pairs_module
from evals.models import EvalSample
from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.answering.sources.news import NewsData, NewsEntry
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from tests.helpers import CFG, with_news

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
CFG_B = with_news(ranker="recency")
SAMPLES = [
    EvalSample(season=CFG.season, week=11, as_of=NOW.isoformat(), gsis_id="00-1", full_name="Joe Burrow", position="QB"),
    EvalSample(season=CFG.season, week=11, as_of=NOW.isoformat(), gsis_id="00-2", full_name="Ja'Marr Chase", position="WR"),
]


def entry(doc_id: str) -> NewsEntry:
    return NewsEntry(
        doc_id=doc_id, source="espn", published_at="2026-11-18T15:00:00+00:00",
        title=f"Title {doc_id}", summary="", url=f"https://x/{doc_id}",
    )


def news_result(team_ids: list[str]) -> SourceResult[NewsData]:
    data = NewsData(cutoff=NOW.isoformat(), player=[], team=[entry(d) for d in team_ids], opponent=[])
    return SourceResult(source="news", status="ok", as_of=NOW.isoformat(), data=data)


def stub_retrieval(monkeypatch, team_ids_by_ranker: dict[str, list[str]]) -> None:
    def fake_context(player, season, week, fmt):
        return ResolvedContext(
            player_id=player.player_id, player_name=player.full_name, team="CIN",
            position=player.position, roster_status="ACT", season=season, week=week,
            scoring_format=fmt,
        )

    target = ScheduleWeek(week=11, opponent="PIT", home=True, played=False, kickoff="2026-11-22T18:00:00+00:00")
    sched = SourceResult(source="schedule", status="ok", as_of="Week 11", data=ScheduleData(team="CIN", weeks=[target]))
    monkeypatch.setattr(pairs_module, "player_context", fake_context)
    monkeypatch.setattr(pairs_module, "schedule", lambda ctx: sched)
    def fake_news(ctx, opp, cutoff, cfg, fetched_before):
        assert fetched_before == NOW
        return news_result(team_ids_by_ranker[cfg.news.ranker])

    monkeypatch.setattr(pairs_module, "news", fake_news)
