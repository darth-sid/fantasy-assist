from ffassistant.ingest import store
from ffassistant.ingest.models import NewsItem, NewsTags


def _item(doc_id: str) -> NewsItem:
    return NewsItem(
        doc_id=doc_id, url=f"https://x/{doc_id}", source="s", title="t", summary="s",
        published_at="2026-11-06T00:00:00+00:00", fetched_at="2026-11-06T00:01:00+00:00",
        raw={"title": "t", "summary": None, "link": f"https://x/{doc_id}", "published": None},
    )


def test_round_trip_and_doc_ids(tmp_path):
    news_dir = tmp_path / "news"
    assert store.load_doc_ids(news_dir) == set()
    store.append_items(news_dir, [_item("a"), _item("b")])
    store.append_items(news_dir, [_item("c")])
    assert [i.doc_id for i in store.iter_items(news_dir)] == ["a", "b", "c"]
    assert list(store.iter_items(news_dir))[0] == _item("a")
    assert store.load_doc_ids(news_dir) == {"a", "b", "c"}


def _tags(doc_id: str, teams: list[str]) -> NewsTags:
    return NewsTags(doc_id=doc_id, player_ids=[], teams=teams)


def test_tags_round_trip_and_replace(tmp_path):
    news_dir = tmp_path / "news"
    assert list(store.iter_tags(news_dir)) == []
    store.append_tags(news_dir, [_tags("a", ["BUF"])])
    store.append_tags(news_dir, [_tags("b", [])])
    assert list(store.iter_tags(news_dir)) == [_tags("a", ["BUF"]), _tags("b", [])]

    store.replace_tags(news_dir, [_tags("a", ["KC"])])

    assert list(store.iter_tags(news_dir)) == [_tags("a", ["KC"])]
    assert [p.name for p in (tmp_path / "news").iterdir()] == ["tags.jsonl"]
