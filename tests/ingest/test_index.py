import ffassistant.ingest.index as index_module
from ffassistant.ingest import store
from ffassistant.ingest.gazetteer import Gazetteer
from ffassistant.ingest.index import index
from ffassistant.config import Config
from ffassistant.ingest.models import NewsItem, NewsTags
from tests.helpers import with_news_dir


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


def _setup(monkeypatch, tmp_path) -> Config:
    gazetteer = Gazetteer(players={}, teams={"Raiders": "LV", "Bills": "BUF"})
    monkeypatch.setattr(index_module, "load_gazetteer", lambda season: gazetteer)
    store.append_items(tmp_path, [_item("a", "Raiders win"), _item("b", "Bills win")])
    store.append_tags(tmp_path, [NewsTags(doc_id="a", player_ids=[], teams=["OLD"])])
    return with_news_dir(tmp_path)


def test_catch_up_tags_only_untagged_items(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path)

    assert index(cfg) == 1
    assert {t.doc_id: t.teams for t in store.iter_tags(tmp_path)} == {"a": ["OLD"], "b": ["BUF"]}


def test_rebuild_retags_everything(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path)

    assert index(cfg, rebuild=True) == 2
    assert [(t.doc_id, t.teams) for t in store.iter_tags(tmp_path)] == [("a", ["LV"]), ("b", ["BUF"])]
