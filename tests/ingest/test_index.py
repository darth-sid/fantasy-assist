import ffassistant.ingest.index as index_module
from ffassistant.ingest import store
from ffassistant.ingest.gazetteer import Gazetteer
from ffassistant.ingest.index import index
from ffassistant.ingest.models import NewsItem, NewsTags


def _item(doc_id: str, title: str) -> NewsItem:
    return NewsItem(
        doc_id=doc_id,
        url=f"https://example.com/{doc_id}",
        source="espn",
        title=title,
        summary="",
        published_at="2026-11-06T00:00:00+00:00",
        fetched_at="2026-11-06T00:00:00+00:00",
        raw={},
    )


def _setup(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(store, "ITEMS_PATH", tmp_path / "items.jsonl")
    monkeypatch.setattr(store, "TAGS_PATH", tmp_path / "tags.jsonl")
    gazetteer = Gazetteer(players={}, teams={"raiders": "LV", "bills": "BUF"})
    monkeypatch.setattr(index_module, "load_gazetteer", lambda season: gazetteer)
    store.append_items([_item("a", "Raiders win"), _item("b", "Bills win")])
    store.append_tags([NewsTags(doc_id="a", player_ids=[], teams=["OLD"])])


def test_catch_up_tags_only_untagged_items(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)

    assert index() == 1
    assert {t.doc_id: t.teams for t in store.iter_tags()} == {"a": ["OLD"], "b": ["BUF"]}


def test_rebuild_retags_everything(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)

    assert index(rebuild=True) == 2
    assert [(t.doc_id, t.teams) for t in store.iter_tags()] == [("a", ["LV"]), ("b", ["BUF"])]
