import json

import ffassistant.ingest.index as index_module
from ffassistant.ingest import poll as poll_module
from ffassistant.ingest import store


def _items(cfg):
    return {i.title: i for i in store.iter_items(cfg.news_dir)}


def test_parses_fields_strips_html_and_keeps_raw(cfg, feeds):
    poll_module.poll(cfg)
    item = _items(cfg)["Parsons & Packers"]
    assert item.source == "generic"
    assert item.summary == "Green Bay hopes Parsons returns & plays."
    assert item.raw["summary"].startswith("<p>Green <b>Bay</b>")
    assert item.raw["published"] == "Fri, 6 Nov 2026 20:04:04 -0500"
    assert item.raw["link"].strip() == "https://example.com/a#comments"


def test_url_normalized_and_doc_id_is_hash_of_it(cfg, feeds):
    poll_module.poll(cfg)
    item = _items(cfg)["Parsons & Packers"]
    assert item.url == "https://example.com/a"
    assert item.doc_id == poll_module._doc_id("generic", "https://example.com/a", "ignored")
    assert len(item.doc_id) == 16


def test_non_utc_date_normalized_to_utc(cfg, feeds):
    poll_module.poll(cfg)
    assert _items(cfg)["Parsons & Packers"].published_at == "2026-11-07T01:04:04+00:00"


def test_missing_date_falls_back_to_fetched_at(cfg, feeds):
    poll_module.poll(cfg)
    item = _items(cfg)["No date"]
    assert item.published_at == item.fetched_at


def test_entry_without_link_is_skipped(cfg, feeds):
    poll_module.poll(cfg)
    assert "No link" not in _items(cfg)


def test_duplicate_within_one_poll_is_skipped(cfg, feeds, capsys):
    poll_module.poll(cfg)
    assert "generic: 4 fetched, 2 new" in capsys.readouterr().out
    assert "Duplicate of a" not in _items(cfg)


def test_second_poll_adds_nothing(cfg, feeds, capsys):
    poll_module.poll(cfg)
    before = (cfg.news_dir / "items.jsonl").read_text()
    capsys.readouterr()
    poll_module.poll(cfg)
    assert (cfg.news_dir / "items.jsonl").read_text() == before
    assert "0 new" in capsys.readouterr().out


def test_overridden_feed_keeps_distinct_updates_on_same_link_and_parses_pst(cfg, feeds):
    poll_module.poll(cfg)
    rotowire = [i for i in store.iter_items(cfg.news_dir) if i.source == "rotowire"]
    assert len(rotowire) == 2
    assert {i.published_at for i in rotowire} == {"2026-11-06T22:30:00+00:00", "2026-11-06T17:05:00+00:00"}
    assert rotowire[0].raw["published"] == "Fri, 06 Nov 2026 2:30:00 PM PST"


def test_unparseable_overridden_date_falls_back_to_fetched_at(cfg, feeds, monkeypatch):
    def reject(raw):
        raise ValueError(raw)

    monkeypatch.setitem(poll_module.DATE_PARSERS, "rotowire", reject)
    poll_module.poll(cfg)
    item = next(i for i in store.iter_items(cfg.news_dir) if i.source == "rotowire")
    assert item.published_at == item.fetched_at


def test_one_feed_erroring_does_not_stop_others(cfg, feeds, capsys):
    feeds["rotowire"] = RuntimeError("HTTP 503")
    assert poll_module.poll(cfg) == 0
    out = capsys.readouterr().out
    assert "rotowire: error: HTTP 503" in out
    assert "generic: 4 fetched, 2 new" in out
    assert {i.source for i in store.iter_items(cfg.news_dir)} == {"generic"}


def test_all_feeds_failing_exits_non_zero(cfg, feeds):
    feeds["rotowire"] = RuntimeError("timeout")
    feeds["generic"] = RuntimeError("HTTP 500")
    assert poll_module.poll(cfg) == 1


def test_stored_line_is_json(cfg, feeds):
    poll_module.poll(cfg)
    first = json.loads((cfg.news_dir / "items.jsonl").read_text().splitlines()[0])
    assert set(first) == {"doc_id", "url", "source", "title", "summary", "published_at", "fetched_at", "raw"}


def test_date_parser_and_id_key_overrides_are_independent(cfg, feeds, monkeypatch):
    monkeypatch.delitem(poll_module.ID_KEYS, "rotowire")
    poll_module.poll(cfg)
    rotowire = [i for i in store.iter_items(cfg.news_dir) if i.source == "rotowire"]
    assert len(rotowire) == 1
    assert rotowire[0].published_at == "2026-11-06T22:30:00+00:00"


def test_poll_tags_new_items(cfg, feeds, capsys):
    poll_module.poll(cfg)

    tags = {t.doc_id: t for t in store.iter_tags(cfg.news_dir)}
    item = _items(cfg)["Parsons & Packers"]
    assert tags[item.doc_id].teams == ["GB"]
    assert set(tags) == {i.doc_id for i in store.iter_items(cfg.news_dir)}
    assert "index: tagged 4 items" in capsys.readouterr().out


def test_gazetteer_failure_keeps_items_and_reports(cfg, feeds, monkeypatch, capsys):
    def fail(season):
        raise RuntimeError("roster down")

    monkeypatch.setattr(index_module, "load_gazetteer", fail)

    assert poll_module.poll(cfg) == 0
    assert len(_items(cfg)) == 4
    assert list(store.iter_tags(cfg.news_dir)) == []
    assert "index: error: roster down" in capsys.readouterr().out


def test_run_starts_with_a_timestamp_line_matching_fetched_at(cfg, feeds, capsys):
    poll_module.poll(cfg)

    first_line = capsys.readouterr().out.splitlines()[0]
    fetched_at = next(store.iter_items(cfg.news_dir)).fetched_at
    assert first_line == f"[{fetched_at}]"
