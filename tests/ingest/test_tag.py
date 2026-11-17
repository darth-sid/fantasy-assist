from ffassistant.ingest.gazetteer import Gazetteer
from ffassistant.ingest.models import NewsItem
from ffassistant.ingest.tag import tag

GAZETTEER = Gazetteer(
    players={
        "terrance ferguson": [("00-1", "LA")],
        "josh allen": [("00-2", "BUF"), ("00-3", "JAX")],
        "aj brown": [("00-4", "PHI")],
        "marvin harrison": [("00-5", "ARI")],
        "ja'marr chase": [("00-6", "CIN")],
        "parker washington": [("00-7", "JAX")],
    },
    teams={
        "Las Vegas Raiders": "LV",
        "Raiders": "LV",
        "Las Vegas": "LV",
        "Washington": "WAS",
        "Bills": "BUF",
        "Buffalo": "BUF",
        "Jaguars": "JAX",
    },
)


def _item(title: str, summary: str = "", source: str = "espn") -> NewsItem:
    return NewsItem(
        doc_id="d",
        url="https://example.com/d",
        source=source,
        title=title,
        summary=summary,
        published_at="2026-11-06T00:00:00+00:00",
        fetched_at="2026-11-06T00:00:00+00:00",
        raw={},
    )


def test_rotowire_tags_title_prefix_player_and_their_team():
    tags = tag(_item("Terrance Ferguson: Suffers hamstring injury", source="rotowire"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-1"], ["LA"])


def test_rotowire_ignores_summary():
    summary = "Ferguson and Josh Allen played against Washington."
    tags = tag(_item("Terrance Ferguson: Update", summary, source="rotowire"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-1"], ["LA"])


def test_other_source_matches_whole_words_in_title_and_summary():
    tags = tag(_item("Ferguson news", "Coach praised Terrance Ferguson's blocking."), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-1"], ["LA"])


def test_no_partial_word_match():
    tags = tag(_item("Josh Allensworth signs"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == ([], [])


def test_nickname_and_unique_city_tag_teams():
    assert tag(_item("Raiders name starter"), GAZETTEER).teams == ["LV"]
    assert tag(_item("Notes", "Ruled out against Washington."), GAZETTEER).teams == ["WAS"]


def test_player_name_containing_a_city_does_not_tag_that_team():
    tags = tag(_item("Parker Washington scores twice"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-7"], ["JAX"])


def test_name_clash_tags_every_match_when_no_team_is_named():
    tags = tag(_item("Josh Allen throws three touchdowns"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-2", "00-3"], ["BUF", "JAX"])


def test_name_clash_resolved_by_named_team():
    tags = tag(_item("Josh Allen throws three touchdowns", "The Bills won again."), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-2"], ["BUF"])


def test_name_clash_falls_back_when_named_team_matches_no_candidate():
    tags = tag(_item("Josh Allen throws three touchdowns against Washington"), GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-2", "00-3"], ["BUF", "JAX", "WAS"])


def test_rotowire_name_clash_resolved_by_summary_team_without_tagging_it():
    item = _item("Josh Allen: Sacks leader", "Allen leads the Jaguars against Washington.", "rotowire")

    tags = tag(item, GAZETTEER)

    assert (tags.player_ids, tags.teams) == (["00-3"], ["JAX"])


def test_lowercase_team_words_do_not_tag():
    tags = tag(_item("Bettors pay their bills", "Fans watched the raiders movie."), GAZETTEER)

    assert tags.teams == []


def test_name_keys_handle_periods_suffixes_and_curly_apostrophes():
    tags = tag(
        _item("A.J. Brown and Marvin Harrison Jr. limited", "Ja’Marr Chase practiced fully."),
        GAZETTEER,
    )

    assert tags.player_ids == ["00-4", "00-5", "00-6"]
    assert tags.teams == ["ARI", "CIN", "PHI"]
