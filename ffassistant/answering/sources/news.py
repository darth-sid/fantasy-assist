from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.config import (
    NEWS_LOOKBACK_DAYS,
    NEWS_MAX_SUMMARY_CHARS,
    NEWS_OPPONENT_TOP_K,
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


def _entry(item: NewsItem) -> NewsEntry:
    return NewsEntry(
        doc_id=item.doc_id,
        source=item.source,
        published_at=item.published_at,
        title=item.title,
        summary=_clean_summary(item.summary),
        url=item.url,
    )


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
                if item.doc_id in tags
                and window_start <= datetime.fromisoformat(item.published_at) < cutoff
            ),
            key=lambda pair: datetime.fromisoformat(pair[0].published_at),
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

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=NewsData(
                cutoff=as_of,
                player=[_entry(item) for item in buckets["player"][:NEWS_TOP_K]],
                team=[_entry(item) for item in buckets["team"][:NEWS_TEAM_TOP_K]],
                opponent=[_entry(item) for item in buckets["opponent"][:NEWS_OPPONENT_TOP_K]],
            ),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
