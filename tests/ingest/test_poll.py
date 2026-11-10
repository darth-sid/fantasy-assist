import json

from ffassistant.ingest import poll as poll_module
from ffassistant.ingest import store


def _items():
    return {i.title: i for i in store.iter_items()}


def test_parses_fields_strips_html_and_keeps_raw(feeds):
    poll_module.poll()
    item = _items()["Parsons & Packers"]
    assert item.source == "generic"
    assert item.summary == "Green Bay hopes Parsons returns & plays."
    assert item.raw["summary"].startswith("<p>Green <b>Bay</b>")
    assert item.raw["published"] == "Fri, 6 Nov 2026 20:04:04 -0500"
    assert item.raw["link"].strip() == "https://example.com/a#comments"


def test_url_normalized_and_doc_id_is_hash_of_it(feeds):
    poll_module.poll()
    item = _items()["Parsons & Packers"]
    assert item.url == "https://example.com/a"
    assert item.doc_id == poll_module._doc_id("generic", "https://example.com/a", "ignored")
    assert len(item.doc_id) == 16


def test_non_utc_date_normalized_to_utc(feeds):
    poll_module.poll()
    assert _items()["Parsons & Packers"].published_at == "2026-11-07T01:04:04+00:00"


def test_missing_date_falls_back_to_fetched_at(feeds):
    poll_module.poll()
    item = _items()["No date"]
    assert item.published_at == item.fetched_at


def test_entry_without_link_is_skipped(feeds):
    poll_module.poll()
    assert "No link" not in _items()


def test_duplicate_within_one_poll_is_skipped(feeds, capsys):
    poll_module.poll()
    assert "generic: 4 fetched, 2 new" in capsys.readouterr().out
    assert "Duplicate of a" not in _items()


def test_second_poll_adds_nothing(feeds, capsys):
    poll_module.poll()
    before = store.ITEMS_PATH.read_text()
    capsys.readouterr()
    poll_module.poll()
    assert store.ITEMS_PATH.read_text() == before
    assert "0 new" in capsys.readouterr().out


def test_overridden_feed_keeps_distinct_updates_on_same_link_and_parses_pst(feeds):
    poll_module.poll()
    rotowire = [i for i in store.iter_items() if i.source == "rotowire"]
    assert len(rotowire) == 2
    assert {i.published_at for i in rotowire} == {"2026-11-06T22:30:00+00:00", "2026-11-06T17:05:00+00:00"}
    assert rotowire[0].raw["published"] == "Fri, 06 Nov 2026 2:30:00 PM PST"


def test_unparseable_overridden_date_falls_back_to_fetched_at(feeds, monkeypatch):
    def reject(raw):
        raise ValueError(raw)

    monkeypatch.setitem(poll_module.DATE_PARSERS, "rotowire", reject)
    poll_module.poll()
    item = next(i for i in store.iter_items() if i.source == "rotowire")
    assert item.published_at == item.fetched_at


def test_one_feed_erroring_does_not_stop_others(feeds, capsys):
    feeds["rotowire"] = RuntimeError("HTTP 503")
    assert poll_module.poll() == 0
    out = capsys.readouterr().out
    assert "rotowire: error: HTTP 503" in out
    assert "generic: 4 fetched, 2 new" in out
    assert {i.source for i in store.iter_items()} == {"generic"}


def test_all_feeds_failing_exits_non_zero(feeds):
    feeds["rotowire"] = RuntimeError("timeout")
    feeds["generic"] = RuntimeError("HTTP 500")
    assert poll_module.poll() == 1


def test_stored_line_is_json(feeds):
    poll_module.poll()
    first = json.loads(store.ITEMS_PATH.read_text().splitlines()[0])
    assert set(first) == {"doc_id", "url", "source", "title", "summary", "published_at", "fetched_at", "raw"}


def test_date_parser_and_id_key_overrides_are_independent(feeds, monkeypatch):
    monkeypatch.delitem(poll_module.ID_KEYS, "rotowire")
    poll_module.poll()
    rotowire = [i for i in store.iter_items() if i.source == "rotowire"]
    assert len(rotowire) == 1
    assert rotowire[0].published_at == "2026-11-06T22:30:00+00:00"
