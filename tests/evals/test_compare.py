import json
import random

import pytest

import evals.pairs as pairs_module
from evals.compare import Comparison, summary_lines
from evals.models import Judgment, RunMeta
from ffassistant.answering.models import SourceResult
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from tests.evals.helpers import CFG, CFG_B, NOW, SAMPLES, stub_retrieval

META = RunMeta(samples="s.jsonl", a_config="a.yaml", b_config="b.yaml")


def _comparison(keys: list[str], seed: int = 0, meta: RunMeta = META) -> Comparison:
    presses = iter(keys)
    return Comparison(CFG, CFG_B, meta, read_key=lambda: next(presses), rng=random.Random(seed))


def test_run_directory_holds_meta_once_and_judgments_without_configs(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    _comparison(keys=["left", "up"]).run(SAMPLES, tmp_path / "run")

    assert json.loads((tmp_path / "run" / "meta.json").read_text()) == {
        "samples": "s.jsonl", "a_config": "a.yaml", "b_config": "b.yaml", "judge_model": None,
    }
    line = json.loads((tmp_path / "run" / "judgments.jsonl").read_text().splitlines()[0])
    assert line == {
        "gsis_id": "00-1", "cutoff": NOW.isoformat(timespec="seconds"),
        "a": ["a-item"], "b": ["b-item"], "winner": line["winner"],
    }


def test_identical_retrievals_auto_tie_without_asking(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["x"], "recency": ["x"]})

    judgments = _comparison(keys=[]).run(SAMPLES, tmp_path / "run")

    assert [(j.winner, j.identical) for j in judgments] == [("tie", True)] * 2


def test_arrows_pick_first_or_second_and_map_back_to_configs(monkeypatch, tmp_path, capsys):
    stub_retrieval(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})
    shown_first = random.Random(0).choice(["a", "b"])

    first, second = _comparison(keys=["left", "down"]).run(SAMPLES, tmp_path / "run")

    assert first.winner == shown_first
    assert second.winner == "tie"
    out = capsys.readouterr().out
    assert "a.yaml" not in out and "bm25" not in out  # blind: no config names on screen
    assert out.index("--- FIRST ---") < out.index("--- SECOND ---")
    assert "← first better" in out


def test_unknown_keys_are_ignored(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    judgments = _comparison(keys=["x", "\n", "right", "up"]).run(SAMPLES, tmp_path / "run")

    shown_first = random.Random(0).choice(["a", "b"])
    assert [j.winner for j in judgments] == ["b" if shown_first == "a" else "a", "tie"]


def test_quit_keeps_earlier_judgments_and_resume_skips_them(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})
    run = tmp_path / "run"

    assert len(_comparison(keys=["left", "q"]).run(SAMPLES, run)) == 1

    judgments = _comparison(keys=["right"]).run(SAMPLES, run)
    assert [j.gsis_id for j in judgments] == ["00-1", "00-2"]


def test_run_of_other_configs_is_refused(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["x"], "recency": ["x"]})
    _comparison(keys=[]).run(SAMPLES, tmp_path / "run")

    with pytest.raises(ValueError, match="new run directory"):
        _comparison(keys=[], meta=META.model_copy(update={"b_config": "c.yaml"})).run(SAMPLES, tmp_path / "run")


def test_season_mismatch_is_refused(tmp_path):
    with pytest.raises(ValueError, match="season"):
        _comparison(keys=[]).run([SAMPLES[0].model_copy(update={"season": 1999})], tmp_path / "run")


def test_bye_week_player_is_skipped(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["x"], "recency": ["y"]})
    bye = ScheduleWeek(week=11, opponent=None, home=None, played=False, kickoff=None)
    sched = SourceResult(source="schedule", status="ok", as_of="Week 11", data=ScheduleData(team="CIN", weeks=[bye]))
    monkeypatch.setattr(pairs_module, "schedule", lambda ctx: sched)

    assert _comparison(keys=[]).run(SAMPLES, tmp_path / "run") == []


def test_judgment_records_the_cutoff_and_what_each_side_showed(monkeypatch, tmp_path):
    stub_retrieval(monkeypatch, {"bm25": ["a-item"], "recency": ["b-item"]})

    first = _comparison(keys=["left", "up"]).run(SAMPLES, tmp_path / "run")[0]

    # Kickoff is after as_of, so the cutoff is the sample's as_of.
    assert first.cutoff == NOW.isoformat(timespec="seconds")
    assert (first.a, first.b) == (["a-item"], ["b-item"])


def _judgment(winner, identical=False) -> Judgment:
    return Judgment(gsis_id="x", cutoff="c", a=["1"], b=["1"] if identical else ["2"], winner=winner)


def test_summary_reports_win_rate_interval_and_p_value():
    judgments = (
        [_judgment("a")] * 18 + [_judgment("b")] * 7 + [_judgment("tie"), _judgment("tie", identical=True)]
    )

    lines = summary_lines(judgments, META)

    assert "  A (a.yaml): 18 wins" in lines and "  identical (auto-tied): 1" in lines
    assert lines[-1] == "  A win rate excluding ties: 72% of 25 (95% CI 52% to 86%), sign test p = 0.043"


def test_summary_without_decisive_judgments():
    assert summary_lines([], META)[-1] == "  no decisive judgments yet"
