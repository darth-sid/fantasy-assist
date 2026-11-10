from collections.abc import Callable
from datetime import datetime, timedelta, timezone

# Per-feed overrides, keyed by the FEEDS key. A feed with no entry uses the defaults:
# the date feedparser parses, and the normalized URL as the doc_id key.

# Raw date string -> aware datetime; raise ValueError/KeyError if it can't be read.
DATE_PARSERS: dict[str, Callable[[str], datetime]] = {}

# (normalized url, raw date string or None) -> the string hashed into doc_id.
ID_KEYS: dict[str, Callable[[str, str | None], str]] = {}


def default_id_key(url: str, raw_date: str | None) -> str:
    return url


_US_ABBREVIATION_OFFSETS = {"PST": -8, "PDT": -7, "MST": -7, "MDT": -6, "CST": -6, "CDT": -5, "EST": -5, "EDT": -4}


def _parse_12_hour_us_date(raw: str) -> datetime:
    # e.g. "Fri, 06 Nov 2026 2:30:00 PM PST"
    text, abbreviation = raw.strip().rsplit(" ", 1)
    parsed = datetime.strptime(text, "%a, %d %b %Y %I:%M:%S %p")
    offset = timedelta(hours=_US_ABBREVIATION_OFFSETS[abbreviation])
    return parsed.replace(tzinfo=timezone(offset))


def _url_and_date_key(url: str, raw_date: str | None) -> str:
    return f"{url}\n{raw_date}" if raw_date else url


DATE_PARSERS["rotowire"] = _parse_12_hour_us_date
ID_KEYS["rotowire"] = _url_and_date_key
