from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.answering.ranking import RANKERS, RankDoc, Ranker
from ffassistant.config import Config, NewsConfig
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


def _clean_summary(summary: str, max_chars: int) -> str:
    summary = summary.removesuffix(_ROTOWIRE_BOILERPLATE).rstrip()
    if len(summary) > max_chars:
        return summary[:max_chars] + "..."
    return summary


def _entry(item: NewsItem, max_chars: int, score: float | None = None) -> NewsEntry:
    return NewsEntry(
        doc_id=item.doc_id,
        source=item.source,
        published_at=item.published_at,
        title=item.title,
        summary=_clean_summary(item.summary, max_chars),
        url=item.url,
        score=score,
    )


def news_query(ctx: ResolvedContext, opponent: str, bucket: str, cfg: NewsConfig) -> str:
    """Fills in the team or opponent query template for this player."""
    template = {"team": cfg.query_team, "opponent": cfg.query_opponent}[bucket]
    return template.format(
        player=ctx.player_name,
        position_words=cfg.position_words.get(ctx.position, ""),
        team=ctx.team,
        opponent=opponent,
    )


def _published(item: NewsItem) -> datetime:
    return datetime.fromisoformat(item.published_at)


def _rank_bucket(
    ranker: Ranker, query: str, candidates: list[NewsItem], top_k: int, max_chars: int
) -> list[NewsEntry]:
    by_id = {item.doc_id: item for item in candidates}
    candidate_docs = [doc for doc in ranker.corpus if doc.doc_id in by_id]
    ranked = ranker.rank(query, candidate_docs)[:top_k]
    selected = [_entry(by_id[doc.doc_id], max_chars, score) for doc, score in ranked]
    return sorted(selected, key=lambda entry: entry.published_at, reverse=True)


def news(
    ctx: ResolvedContext,
    opponent: str,
    cutoff: datetime,
    cfg: Config,
    fetched_before: datetime | None = None,
) -> SourceResult[NewsData]:
    source = "news"
    as_of = cutoff.isoformat(timespec="seconds")
    news_cfg, max_chars = cfg.news, cfg.news.max_summary_chars

    try:
        tags: dict[str, NewsTags] = {entry.doc_id: entry for entry in iter_tags(cfg.news_dir)}
        window_start = cutoff - timedelta(days=news_cfg.lookback_days)
        in_window = sorted(
            (
                (item, tags[item.doc_id])
                for item in iter_items(cfg.news_dir)
                if item.doc_id in tags
                and window_start <= _published(item) < cutoff
                # Pins the corpus to what had been collected by then, e.g. for repeatable evals.
                and (fetched_before is None or datetime.fromisoformat(item.fetched_at) < fetched_before)
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
            RankDoc(
                item.doc_id,
                f"{item.title} {_clean_summary(item.summary, max_chars)}",
                _published(item),
            )
            for item, _ in in_window
        ]
        ranker = RANKERS[news_cfg.ranker](corpus)

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=NewsData(
                cutoff=as_of,
                player=[_entry(item, max_chars) for item in buckets["player"][: news_cfg.top_k]],
                team=_rank_bucket(
                    ranker,
                    news_query(ctx, opponent, "team", news_cfg),
                    buckets["team"],
                    news_cfg.team_top_k,
                    max_chars,
                ),
                opponent=_rank_bucket(
                    ranker,
                    news_query(ctx, opponent, "opponent", news_cfg),
                    buckets["opponent"],
                    news_cfg.opponent_top_k,
                    max_chars,
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
