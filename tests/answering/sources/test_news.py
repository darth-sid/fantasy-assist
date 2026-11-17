from datetime import datetime, timedelta, timezone

import ffassistant.answering.sources.news as news_module
import ffassistant.ingest.store as store_module
from ffassistant.answering.models import ResolvedContext
from ffassistant.answering.sources.news import news
from ffassistant.ingest.models import NewsItem, NewsTags

CUTOFF = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
CTX = ResolvedContext(
    player_id="00-1",
    player_name="Terrance Ferguson",
    team="LA",
    position="TE",
    roster_status="ACT",
    season=2026,
    week=11,
    scoring_format="PPR",
)


def _item(
    doc_id: str,
    summary: str = "",
    published: datetime = CUTOFF - timedelta(days=1),
    title: str | None = None,
) -> NewsItem:
    return NewsItem(
        doc_id=doc_id,
        url=f"https://example.com/{doc_id}",
        source="rotowire",
        title=title or f"Title {doc_id}",
        summary=summary,
        published_at=published.isoformat(timespec="seconds"),
        fetched_at=published.isoformat(timespec="seconds"),
        raw={},
    )


def _tags(doc_id: str, player_ids: list[str] = (), teams: list[str] = ()) -> NewsTags:
    return NewsTags(doc_id=doc_id, player_ids=list(player_ids), teams=list(teams))


def _run(monkeypatch, items: list[NewsItem], tags: list[NewsTags], ranker: str = "recency"):
    monkeypatch.setattr(news_module, "NEWS_RANKER", ranker)
    monkeypatch.setattr(news_module, "iter_items", lambda: iter(items))
    monkeypatch.setattr(news_module, "iter_tags", lambda: iter(tags))
    return news(CTX, "ARI", CUTOFF)


def _buckets(result) -> dict[str, list[str]]:
    if result.status == "empty":
        return {}
    assert result.status == "ok"
    return {
        name: [entry.doc_id for entry in getattr(result.data, name)]
        for name in ("player", "team", "opponent")
    }


def test_each_bucket(monkeypatch):
    items = [_item("p"), _item("t"), _item("o"), _item("other")]
    tags = [
        _tags("p", player_ids=["00-1"], teams=["LA"]),
        _tags("t", player_ids=["00-2"], teams=["LA"]),
        _tags("o", teams=["ARI"]),
        _tags("other", teams=["KC"]),
    ]

    assert _buckets(_run(monkeypatch, items, tags)) == {
        "player": ["p"],
        "team": ["t"],
        "opponent": ["o"],
    }


def test_item_lands_in_first_qualifying_bucket(monkeypatch):
    items = [_item("player-and-opp"), _item("team-and-opp")]
    tags = [
        _tags("player-and-opp", player_ids=["00-1"], teams=["LA", "ARI"]),
        _tags("team-and-opp", teams=["ARI", "LA"]),
    ]

    assert _buckets(_run(monkeypatch, items, tags)) == {
        "player": ["player-and-opp"],
        "team": ["team-and-opp"],
        "opponent": [],
    }


def test_per_bucket_caps_and_newest_first(monkeypatch):
    days = [3, 1, 6, 2, 5, 4]
    items = [
        _item(f"{kind}-{d}", published=CUTOFF - timedelta(days=d))
        for kind in ("p", "t", "o")
        for d in days
    ]
    tags = [_tags(f"p-{d}", player_ids=["00-1"]) for d in days]
    tags += [_tags(f"t-{d}", teams=["LA"]) for d in days]
    tags += [_tags(f"o-{d}", teams=["ARI"]) for d in days]

    assert _buckets(_run(monkeypatch, items, tags)) == {
        "player": ["p-1", "p-2", "p-3", "p-4", "p-5"],
        "team": ["t-1", "t-2", "t-3"],
        "opponent": ["o-1", "o-2", "o-3"],
    }


def test_untagged_items_are_skipped(monkeypatch):
    result = _run(monkeypatch, [_item("untagged")], [])

    assert result.status == "empty"


def test_lookback_window_bounds(monkeypatch):
    items = [
        _item("at-start", published=CUTOFF - timedelta(days=14)),
        _item("before-start", published=CUTOFF - timedelta(days=14, seconds=1)),
        _item("just-before-cutoff", published=CUTOFF - timedelta(seconds=1)),
        _item("at-cutoff", published=CUTOFF),
    ]
    tags = [_tags(item.doc_id, player_ids=["00-1"]) for item in items]

    assert _buckets(_run(monkeypatch, items, tags))["player"] == ["just-before-cutoff", "at-start"]


def test_strips_rotowire_boilerplate_and_truncates(monkeypatch):
    items = [
        _item("short", "Ruled out. Visit RotoWire.com for more analysis on this update."),
        _item("long", "x" * 600, published=CUTOFF - timedelta(days=2)),
    ]
    tags = [_tags("short", player_ids=["00-1"]), _tags("long", player_ids=["00-1"])]

    result = _run(monkeypatch, items, tags)

    assert [entry.summary for entry in result.data.player] == ["Ruled out.", "x" * 500 + "..."]


def test_ok_carries_cutoff_and_entry_fields(monkeypatch):
    result = _run(monkeypatch, [_item("a", "Ruled out.")], [_tags("a", player_ids=["00-1"])])

    assert result.data.cutoff == "2026-11-15T18:00:00+00:00"
    entry = result.data.player[0]
    assert (entry.source, entry.title, entry.url, entry.published_at) == (
        "rotowire",
        "Title a",
        "https://example.com/a",
        "2026-11-14T18:00:00+00:00",
    )


def test_missing_files_are_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(store_module, "ITEMS_PATH", tmp_path / "missing.jsonl")
    monkeypatch.setattr(store_module, "TAGS_PATH", tmp_path / "missing-tags.jsonl")

    result = news(CTX, "ARI", CUTOFF)

    assert result.status == "empty"
    assert result.source == "news"


def test_error_status_when_read_raises(monkeypatch):
    def _raise():
        raise OSError("disk gone")

    monkeypatch.setattr(news_module, "iter_tags", _raise)

    result = news(CTX, "ARI", CUTOFF)

    assert result.status == "error"
    assert result.data is None
    assert "disk gone" in result.error


def _bm25(monkeypatch, items: list[NewsItem], tags: list[NewsTags]):
    monkeypatch.setattr(news_module, "NEWS_QUERY_TEAM", "cornerback injury")
    return _run(monkeypatch, items, tags, ranker="bm25")


def _team_ids(result) -> list[str]:
    return [entry.doc_id for entry in result.data.team]


def test_recency_ranker_scores_are_timestamps(monkeypatch):
    result = _run(monkeypatch, [_item("t")], [_tags("t", teams=["LA"])])

    assert result.data.team[0].score == (CUTOFF - timedelta(days=1)).timestamp()


def test_bm25_orders_relevant_item_above_irrelevant(monkeypatch):
    monkeypatch.setattr(news_module, "NEWS_TEAM_TOP_K", 1)
    items = [
        _item("uniforms", title="Rams unveil throwback uniforms", published=CUTOFF - timedelta(hours=1)),
        _item("cb", title="Rams cornerback ruled out with injury", published=CUTOFF - timedelta(days=3)),
        _item("ticket", title="Rams ticket injury waiver", published=CUTOFF - timedelta(days=2)),
    ]
    tags = [_tags(i.doc_id, teams=["LA"]) for i in items]

    assert _team_ids(_bm25(monkeypatch, items, tags)) == ["cb"]


def test_bm25_drops_zero_score_items(monkeypatch):
    items = [
        _item("cb", title="Rams cornerback ruled out"),
        _item("uniforms", title="Rams unveil throwback uniforms"),
    ]
    tags = [_tags(i.doc_id, teams=["LA"]) for i in items]

    assert _team_ids(_bm25(monkeypatch, items, tags)) == ["cb"]


def test_bm25_ties_go_to_the_newer_item(monkeypatch):
    monkeypatch.setattr(news_module, "NEWS_TEAM_TOP_K", 1)
    items = [
        _item("old", title="Rams cornerback hurt", published=CUTOFF - timedelta(days=3)),
        _item("new", title="Rams cornerback hurt", published=CUTOFF - timedelta(days=1)),
    ]
    tags = [_tags(i.doc_id, teams=["LA"]) for i in items]

    assert _team_ids(_bm25(monkeypatch, items, tags)) == ["new"]


def test_bm25_term_weights_come_from_the_whole_window(monkeypatch):
    monkeypatch.setattr(news_module, "NEWS_QUERY_TEAM", "injury")
    items = [
        _item("cb", title="Rams cornerback injury update"),
        _item("other", title="Rams practice notes"),
    ]
    tags = [_tags(i.doc_id, teams=["LA"]) for i in items]
    alone = _run(monkeypatch, items, tags, ranker="bm25").data.team[0].score

    # An item outside the bucket (a KC item) that also says "injury" lowers that term's weight.
    outside = _item("kc", title="Chiefs injury report")
    with_outside = _run(
        monkeypatch, [*items, outside], [*tags, _tags("kc", teams=["KC"])], ranker="bm25"
    )

    assert _team_ids(with_outside) == ["cb"]
    assert with_outside.data.team[0].score < alone


def test_player_bucket_ignores_ranker(monkeypatch):
    items = [
        _item("p-irrelevant", title="Ferguson unveils new cleats", published=CUTOFF - timedelta(days=1)),
        _item("p-injury", title="Ferguson cornerback injury", published=CUTOFF - timedelta(days=2)),
    ]
    tags = [_tags(i.doc_id, player_ids=["00-1"]) for i in items]

    result = _bm25(monkeypatch, items, tags)

    assert [entry.doc_id for entry in result.data.player] == ["p-irrelevant", "p-injury"]
    assert all(entry.score is None for entry in result.data.player)


def test_selected_items_render_newest_first(monkeypatch):
    items = [
        _item("strong-old", title="Rams cornerback injury cornerback", published=CUTOFF - timedelta(days=5)),
        _item("weak-new", title="Rams cornerback signs", published=CUTOFF - timedelta(days=1)),
    ]
    tags = [_tags(i.doc_id, teams=["LA"]) for i in items]

    result = _bm25(monkeypatch, items, tags)

    assert _team_ids(result) == ["weak-new", "strong-old"]
    assert result.data.team[1].score > result.data.team[0].score


def test_news_query_fills_placeholders():
    query = news_module.news_query(CTX, "ARI", "team")

    assert query.startswith("tight end role workload")
