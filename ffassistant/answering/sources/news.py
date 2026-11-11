from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.config import NEWS_LOOKBACK_DAYS, NEWS_MAX_SUMMARY_CHARS, NEWS_TOP_K
from ffassistant.ingest.models import NewsItem
from ffassistant.ingest.store import iter_items

_CURLY_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv)$")
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
    items: list[NewsEntry]


def name_key(text: str) -> str:
    key = text.lower().translate(_CURLY_QUOTES).replace(".", "")
    key = re.sub(r"\s+", " ", key).strip()
    return _SUFFIX.sub("", key)


def _is_about(item: NewsItem, player_key: str) -> bool:
    if item.source == "rotowire":
        # RotoWire titles lead with the full name; summaries use last names only.
        return name_key(item.title.split(": ", 1)[0]) == player_key
    pattern = rf"\b{re.escape(player_key)}\b"
    return any(re.search(pattern, name_key(text)) for text in (item.title, item.summary))


def _clean_summary(summary: str) -> str:
    summary = summary.removesuffix(_ROTOWIRE_BOILERPLATE).rstrip()
    if len(summary) > NEWS_MAX_SUMMARY_CHARS:
        return summary[:NEWS_MAX_SUMMARY_CHARS] + "..."
    return summary


def news(ctx: ResolvedContext, cutoff: datetime) -> SourceResult[NewsData]:
    source = "news"
    as_of = cutoff.isoformat(timespec="seconds")

    try:
        player_key = name_key(ctx.player_name)
        window_start = cutoff - timedelta(days=NEWS_LOOKBACK_DAYS)
        matches = [
            item
            for item in iter_items()
            if window_start <= datetime.fromisoformat(item.published_at) < cutoff
            and _is_about(item, player_key)
        ]

        if not matches:
            return SourceResult(source=source, status="empty", as_of=as_of)

        matches.sort(key=lambda item: datetime.fromisoformat(item.published_at), reverse=True)
        entries = [
            NewsEntry(
                doc_id=item.doc_id,
                source=item.source,
                published_at=item.published_at,
                title=item.title,
                summary=_clean_summary(item.summary),
                url=item.url,
            )
            for item in matches[:NEWS_TOP_K]
        ]

        return SourceResult(
            source=source,
            status="ok",
            as_of=as_of,
            data=NewsData(cutoff=as_of, items=entries),
        )

    except Exception as exc:
        return SourceResult(
            source=source,
            status="error",
            as_of=as_of,
            error=f"{type(exc).__name__}: {exc}",
        )
