from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.answering.ranking import RANKERS, RankDoc
from ffassistant.config import (
    NEWS_LOOKBACK_DAYS,
    NEWS_MAX_SUMMARY_CHARS,
    NEWS_OPPONENT_TOP_K,
    NEWS_POSITION_WORDS,
    NEWS_QUERY_OPPONENT,
    NEWS_QUERY_TEAM,
    NEWS_RANKER,
    NEWS_TEAM_TOP_K,
    NEWS_TOP_K,
)
from ffassistant.ingest.models import NewsItem, NewsTags
from ffassistant.ingest.store import iter_items, iter_tags

_ROTOWIRE_BOILERPLATE = "Visit RotoWire.com for more analysis on this update."


@dataclass
class NewsEntry:
    doc_id: str
    source: str
    published_at: str
    title: str
    summary: str
    url: str
    score: float | None = None  # ranker score; None for the player bucket


@dataclass
class NewsData:
    cutoff: str
    player: list[NewsEntry]
    team: list[NewsEntry]
    opponent: list[NewsEntry]


def _clean_summary(summary: str) -> str:
    summary = summary.removesuffix(_ROTOWIRE_BOILERPLATE).rstrip()
    if len(summary) > NEWS_MAX_SUMMARY_CHARS:
        return summary[:NEWS_MAX_SUMMARY_CHARS] + "..."
    return summary


def _entry(item: NewsItem, score: float | None = None) -> NewsEntry:
    return NewsEntry(
        doc_id=item.doc_id,
        source=item.source,
        published_at=item.published_at,
        title=item.title,
        summary=_clean_summary(item.summary),
        url=item.url,
        score=score,
    )


def news_query(ctx: ResolvedContext, opponent: str, bucket: str) -> str:
    """Fills in the team or opponent query template for this player."""
    template = {"team": NEWS_QUERY_TEAM, "opponent": NEWS_QUERY_OPPONENT}[bucket]
    return template.format(
        player=ctx.player_name,
        position_words=NEWS_POSITION_WORDS.get(ctx.position, ""),
        team=ctx.team,
        opponent=opponent,
    )


def _published(item: NewsItem) -> datetime:
    return datetime.fromisoformat(item.published_at)


def _rank_bucket(
    query: str, candidates: list[NewsItem], corpus: list[RankDoc], top_k: int
) -> list[NewsEntry]:
    by_id = {item.doc_id: item for item in candidates}
    candidate_docs = [doc for doc in corpus if doc.doc_id in by_id]
    ranked = RANKERS[NEWS_RANKER](query, candidate_docs, corpus)[:top_k]
    selected = [_entry(by_id[doc.doc_id], score) for doc, score in ranked]
    return sorted(selected, key=lambda entry: entry.published_at, reverse=True)


def news(ctx: ResolvedContext, opponent: str, cutoff: datetime) -> SourceResult[NewsData]:
    source = "news"
    as_of = cutoff.isoformat(timespec="seconds")

    try:
        tags: dict[str, NewsTags] = {entry.doc_id: entry for entry in iter_tags()}
        window_start = cutoff - timedelta(days=NEWS_LOOKBACK_DAYS)
        in_window = sorted(
            (
                (item, tags[item.doc_id])
                for item in iter_items()
                if item.doc_id in tags and window_start <= _published(item) < cutoff
            ),
            key=lambda pair: _published(pair[0]),
            reverse=True,
        )

        # Each item lands in the first bucket it qualifies for: player, then team, then opponent.
        buckets: dict[str, list[NewsItem]] = {"player": [], "team": [], "opponent": []}
        for item, item_tags in in_window:
            if ctx.player_id in item_tags.player_ids:
                buckets["player"].append(item)
            elif ctx.team in item_tags.teams:
                buckets["team"].append(item)
            elif opponent in item_tags.teams:
                buckets["opponent"].append(item)

        if not any(buckets.values()):
            return SourceResult(source=source, status="empty", as_of=as_of)

        # Term weights come from every tagged item in the window, not just one bucket's candidates.
        corpus = [
            RankDoc(item.doc_id, f"{item.title} {_clean_summary(item.summary)}", _published(item))
            for item, _ in in_window
        ]

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=NewsData(
                cutoff=as_of,
                player=[_entry(item) for item in buckets["player"][:NEWS_TOP_K]],
                team=_rank_bucket(
                    news_query(ctx, opponent, "team"), buckets["team"], corpus, NEWS_TEAM_TOP_K
                ),
                opponent=_rank_bucket(
                    news_query(ctx, opponent, "opponent"),
                    buckets["opponent"],
                    corpus,
                    NEWS_OPPONENT_TOP_K,
                ),
            ),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
