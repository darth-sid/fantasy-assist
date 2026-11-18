import random
from datetime import datetime, timezone

import pytest

import evals.compare as compare_module
from evals.compare import Comparison, summary_lines, tally
from evals.models import EvalSample
from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.answering.sources.news import NewsData, NewsEntry
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from tests.helpers import CFG, with_news

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
CFG_B = with_news(ranker="recency")
SAMPLES = [
    EvalSample(id="w11-000", season=CFG.season, week=11, as_of=NOW.isoformat(), gsis_id="00-1", full_name="Joe Burrow", position="QB"),
    EvalSample(id="w11-001", season=CFG.season, week=11, as_of=NOW.isoformat(), gsis_id="00-2", full_name="Ja'Marr Chase", position="WR"),
]


def _entry(doc_id: str) -> NewsEntry:
    return NewsEntry(
        doc_id=doc_id, source="espn", published_at="2026-11-18T15:00:00+00:00",
        title=f"Title {doc_id}", summary="", url=f"https://x/{doc_id}",
    )


def _news_result(team_ids: list[str]) -> SourceResult[NewsData]:
    data = NewsData(cutoff=NOW.isoformat(), player=[], team=[_entry(d) for d in team_ids], opponent=[])
    return SourceResult(source="news", status="ok", as_of=NOW.isoformat(), data=data)


def _stub(monkeypatch, team_ids_by_ranker: dict[str, list[str]]) -> None:
    def fake_context(player, season, week, fmt):
        return ResolvedContext(
            player_id=player.player_id, player_name=player.full_name, team="CIN",
            position=player.position, roster_status="ACT", season=season, week=week,
            scoring_format=fmt,
        )

    target = ScheduleWeek(week=11, opponent="PIT", home=True, played=False, kickoff="2026-11-22T18:00:00+00:00")
    sched = SourceResult(source="schedule", status="ok", as_of="Week 11", data=ScheduleData(team="CIN", weeks=[target]))
    monkeypatch.setattr(compare_module, "player_context", fake_context)
    monkeypatch.setattr(compare_module, "schedule", lambda ctx: sched)
    def fake_news(ctx, opp, cutoff, cfg, fetched_before):
        assert fetched_before == NOW
        return _news_result(team_ids_by_ranker[cfg.news.ranker])

    monkeypatch.setattr(compare_module, "news", fake_news)


def _comparison(keys: list[str], seed: int = 0) -> Comparison:
    presses = iter(keys)
    return Comparison(CFG, CFG_B, "a.yaml", "b.yaml", read_key=lambda: next(presses), rng=random.Random(seed))


def test_identical_retrievals_auto_tie_without_asking(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["x"], "recency": ["x"]})

    judgments = _comparison(keys=[]).run(SAMPLES, tmp_path / "j.jsonl")

    assert [(j.choice, j.winner, j.left) for j in judgments] == [("identical", "tie", None)] * 2


def test_arrow_choice_maps_back_to_the_config_on_that_side(monkeypatch, tmp_path, capsys):
    _stub(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    judgments = _comparison(keys=["left", "down"]).run(SAMPLES, tmp_path / "j.jsonl")

    first, second = judgments
    assert first.choice == "left" and first.winner == first.left
    assert (second.choice, second.winner) == ("tie", "tie")
    out = capsys.readouterr().out
    assert "a.yaml" not in out and "bm25" not in out  # blind: no config names on screen
    assert out.index("--- LEFT ---") < out.index("--- RIGHT ---")


def test_unknown_keys_are_ignored(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    judgments = _comparison(keys=["x", "\n", "right", "up"]).run(SAMPLES, tmp_path / "j.jsonl")

    assert [j.choice for j in judgments] == ["right", "tie"]


def test_quit_keeps_earlier_judgments_and_resume_skips_them(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})
    out = tmp_path / "j.jsonl"

    assert len(_comparison(keys=["left", "q"]).run(SAMPLES, out)) == 1

    judgments = _comparison(keys=["right"]).run(SAMPLES, out)
    assert [j.sample_id for j in judgments] == ["w11-000", "w11-001"]


def test_output_from_other_configs_is_refused(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["x"], "recency": ["x"]})
    out = tmp_path / "j.jsonl"
    _comparison(keys=[]).run(SAMPLES, out)

    other = Comparison(CFG, CFG_B, "a.yaml", "c.yaml", read_key=lambda: "q")
    with pytest.raises(ValueError, match="other configs"):
        other.run(SAMPLES, out)


def test_season_mismatch_is_refused(tmp_path):
    with pytest.raises(ValueError, match="season"):
        _comparison(keys=[]).run([SAMPLES[0].model_copy(update={"season": 1999})], tmp_path / "j.jsonl")


def test_bye_week_player_is_skipped(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["x"], "recency": ["y"]})
    bye = ScheduleWeek(week=11, opponent=None, home=None, played=False, kickoff=None)
    sched = SourceResult(source="schedule", status="ok", as_of="Week 11", data=ScheduleData(team="CIN", weeks=[bye]))
    monkeypatch.setattr(compare_module, "schedule", lambda ctx: sched)

    assert _comparison(keys=[]).run(SAMPLES, tmp_path / "j.jsonl") == []


def test_tally_counts_each_outcome(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})
    judgments = _comparison(keys=["left", "up"]).run(SAMPLES, tmp_path / "j.jsonl")

    counts = tally(judgments)

    assert counts[judgments[0].left] == 1 and counts["tie"] == 1 and counts["identical"] == 0


def test_judgment_records_the_cutoff_and_what_each_side_showed(monkeypatch, tmp_path):
    _stub(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    first = _comparison(keys=["left", "up"]).run(SAMPLES, tmp_path / "j.jsonl")[0]

    # Kickoff is after as_of, so the cutoff is the sample's as_of.
    assert first.cutoff == NOW.isoformat(timespec="seconds")
    assert (first.a.status, first.a.team, first.b.team) == ("ok", ["a-item"], ["b-item"])


def test_summary_reports_win_rate_interval_and_p_value():
    def judgment(winner, choice):
        empty = {"status": "ok"}
        return compare_module.Judgment(
            sample_id="s", a_config="a", b_config="b", cutoff="c", a=empty, b=empty,
            left="a" if choice != "identical" else None, choice=choice, winner=winner,
        )

    judgments = [judgment("a", "left")] * 18 + [judgment("b", "right")] * 7 + [judgment("tie", "tie")]

    lines = summary_lines(judgments, "bm25.yaml", "recency.yaml")

    assert "  A (bm25.yaml): 18 wins" in lines
    assert lines[-1] == "  A win rate excluding ties: 72% of 25 (95% CI 52% to 86%), sign test p = 0.043"


def test_summary_without_decisive_judgments():
    assert summary_lines([], "a", "b")[-1] == "  no decisive judgments yet"
