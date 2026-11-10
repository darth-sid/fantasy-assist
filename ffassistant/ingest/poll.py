import calendar
import hashlib
import html
import logging
import re
from datetime import datetime, timezone

import feedparser

from ffassistant.clients.rss_client import fetch_feed
from ffassistant.config import FEEDS
from ffassistant.ingest import store
from ffassistant.ingest.models import NewsItem
from ffassistant.ingest.overrides import DATE_PARSERS, ID_KEYS, default_id_key

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")


def _plain_text(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def _normalize_url(url: str) -> str:
    return url.strip().split("#", 1)[0]


def _doc_id(source: str, url: str, raw_date: str | None) -> str:
    key = ID_KEYS.get(source, default_id_key)(url, raw_date)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _published_at(source: str, entry) -> datetime | None:
    raw_date = entry.get("published")
    parse_date = DATE_PARSERS.get(source)
    if parse_date and raw_date:
        try:
            return parse_date(raw_date).astimezone(timezone.utc)
        except (ValueError, KeyError):
            return None
    if entry.get("published_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.published_parsed), timezone.utc)
    return None


def _build_item(source: str, entry, fetched_at: datetime) -> NewsItem | None:
    link = entry.get("link")
    if not link or not link.strip():
        return None
    url = _normalize_url(link)
    published = _published_at(source, entry) or fetched_at
    return NewsItem(
        doc_id=_doc_id(source, url, entry.get("published")),
        url=url,
        source=source,
        title=_plain_text(entry.get("title", "")),
        summary=_plain_text(entry.get("summary", "")),
        published_at=published.isoformat(timespec="seconds"),
        fetched_at=fetched_at.isoformat(timespec="seconds"),
        raw={k: entry.get(k) for k in ("title", "summary", "link", "published")},
    )


def _poll_feed(source: str, url: str, seen_ids: set[str], fetched_at: datetime) -> tuple[int, int]:
    parsed = feedparser.parse(fetch_feed(url))
    if not parsed.entries:
        log.warning("%s: feed returned no entries", source)
    elif parsed.bozo:
        log.warning("%s: malformed feed, using parsed entries (%s)", source, parsed.bozo_exception)

    new_items = []
    for entry in parsed.entries:
        item = _build_item(source, entry, fetched_at)
        if item is None or item.doc_id in seen_ids:
            continue
        seen_ids.add(item.doc_id)
        new_items.append(item)
    store.append_items(new_items)
    return len(parsed.entries), len(new_items)


def poll() -> int:
    """Polls every feed once and returns the process exit code."""
    seen_ids = store.load_doc_ids()
    fetched_at = datetime.now(timezone.utc)
    failures = 0
    for source, url in FEEDS.items():
        try:
            fetched, new = _poll_feed(source, url, seen_ids, fetched_at)
            print(f"{source}: {fetched} fetched, {new} new")
        except Exception as e:
            failures += 1
            print(f"{source}: error: {e}")
    return 1 if failures == len(FEEDS) else 0
