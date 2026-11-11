from datetime import datetime, timedelta, timezone

import ffassistant.answering.sources.news as news_module
import ffassistant.ingest.store as store_module
from ffassistant.answering.models import ResolvedContext
from ffassistant.answering.sources.news import news
from ffassistant.ingest.models import NewsItem

CUTOFF = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)


def _ctx(name: str = "Terrance Ferguson") -> ResolvedContext:
    return ResolvedContext(
        player_id="00-1",
        player_name=name,
        team="LA",
        position="TE",
        roster_status="ACT",
        season=2026,
        week=11,
        scoring_format="PPR",
    )


def _item(
    doc_id: str,
    title: str,
    summary: str = "",
    source: str = "rotowire",
    published: datetime = CUTOFF - timedelta(days=1),
) -> NewsItem:
    return NewsItem(
        doc_id=doc_id,
        url=f"https://example.com/{doc_id}",
        source=source,
        title=title,
        summary=summary,
        published_at=published.isoformat(timespec="seconds"),
        fetched_at=published.isoformat(timespec="seconds"),
        raw={},
    )


def _ids(monkeypatch, items: list[NewsItem], name: str = "Terrance Ferguson") -> list[str]:
    monkeypatch.setattr(news_module, "iter_items", lambda: iter(items))
    result = news(_ctx(name), CUTOFF)
    if result.status == "empty":
        return []
    assert result.status == "ok"
    return [entry.doc_id for entry in result.data.items]


def test_rotowire_matches_on_title_prefix(monkeypatch):
    items = [_item("a", "Terrance Ferguson: Suffers hamstring injury")]

    assert _ids(monkeypatch, items) == ["a"]


def test_rotowire_does_not_match_on_summary(monkeypatch):
    items = [_item("a", "Puka Nacua: Big day", "Ferguson and Terrance Ferguson both caught passes.")]

    assert _ids(monkeypatch, items) == []


def test_other_source_matches_whole_words_in_title_or_summary(monkeypatch):
    items = [
        _item("title", "Rams sign Terrance Ferguson to extension", source="espn"),
        _item("summary", "Rams notes", "Coach praised Terrance Ferguson's blocking.", source="espn"),
    ]

    assert _ids(monkeypatch, items) == ["title", "summary"]


def test_other_source_does_not_match_partial_words(monkeypatch):
    items = [_item("a", "Josh Allensworth signs", "Josh Allensworth is a new name.", source="espn")]

    assert _ids(monkeypatch, items, name="Josh Allen") == []


def test_name_key_ignores_periods(monkeypatch):
    items = [_item("a", "AJ Brown: Limited in practice")]

    assert _ids(monkeypatch, items, name="A.J. Brown") == ["a"]


def test_name_key_drops_suffix(monkeypatch):
    items = [
        _item("rotowire", "Marvin Harrison: Questionable"),
        _item("espn", "Notes", "Marvin Harrison Jr. was limited.", source="espn"),
    ]

    assert _ids(monkeypatch, items, name="Marvin Harrison Jr.") == ["rotowire", "espn"]


def test_name_key_straightens_curly_apostrophes(monkeypatch):
    items = [_item("a", "Ja’Marr Chase: Practices fully")]

    assert _ids(monkeypatch, items, name="Ja'Marr Chase") == ["a"]


def test_lookback_window_bounds(monkeypatch):
    title = "Terrance Ferguson: Update"
    items = [
        _item("at-start", title, published=CUTOFF - timedelta(days=14)),
        _item("before-start", title, published=CUTOFF - timedelta(days=14, seconds=1)),
        _item("just-before-cutoff", title, published=CUTOFF - timedelta(seconds=1)),
        _item("at-cutoff", title, published=CUTOFF),
    ]

    assert sorted(_ids(monkeypatch, items)) == ["at-start", "just-before-cutoff"]


def test_newest_first_and_top_k(monkeypatch):
    items = [
        _item(f"day-{days}", "Terrance Ferguson: Update", published=CUTOFF - timedelta(days=days))
        for days in [3, 1, 6, 2, 5, 4]
    ]

    assert _ids(monkeypatch, items) == ["day-1", "day-2", "day-3", "day-4", "day-5"]


def test_strips_rotowire_boilerplate(monkeypatch):
    summary = "Ferguson was ruled out. Visit RotoWire.com for more analysis on this update."
    monkeypatch.setattr(
        news_module, "iter_items", lambda: iter([_item("a", "Terrance Ferguson: Out", summary)])
    )

    result = news(_ctx(), CUTOFF)

    assert result.data.items[0].summary == "Ferguson was ruled out."


def test_truncates_long_summary(monkeypatch):
    monkeypatch.setattr(
        news_module, "iter_items", lambda: iter([_item("a", "Terrance Ferguson: Out", "x" * 600)])
    )

    result = news(_ctx(), CUTOFF)

    assert result.data.items[0].summary == "x" * 500 + "..."


def test_ok_carries_cutoff_and_entry_fields(monkeypatch):
    monkeypatch.setattr(
        news_module, "iter_items", lambda: iter([_item("a", "Terrance Ferguson: Out", "Ruled out.")])
    )

    result = news(_ctx(), CUTOFF)

    assert result.data.cutoff == "2026-11-15T18:00:00+00:00"
    entry = result.data.items[0]
    assert (entry.source, entry.title, entry.url) == (
        "rotowire",
        "Terrance Ferguson: Out",
        "https://example.com/a",
    )
    assert entry.published_at == "2026-11-14T18:00:00+00:00"


def test_missing_items_file_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(store_module, "ITEMS_PATH", tmp_path / "missing.jsonl")

    result = news(_ctx(), CUTOFF)

    assert result.status == "empty"
    assert result.source == "news"


def test_error_status_when_read_raises(monkeypatch):
    def _raise():
        raise OSError("disk gone")

    monkeypatch.setattr(news_module, "iter_items", _raise)

    result = news(_ctx(), CUTOFF)

    assert result.status == "error"
    assert result.data is None
    assert "disk gone" in result.error
