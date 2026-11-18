import random

import pytest

from evals.agreement import AgreementCheck, summary_lines
from evals.models import AgreementJudgment, LLMJudgment, RunMeta
from evals.run_store import RunStore, write_samples
from ffassistant.ingest import store
from ffassistant.ingest.models import NewsItem
from tests.evals.helpers import NOW, SAMPLES, stub_retrieval
from tests.helpers import with_news_dir


def _item(doc_id: str) -> NewsItem:
    stamp = NOW.isoformat(timespec="seconds")
    return NewsItem(
        doc_id=doc_id, url=f"https://x/{doc_id}", source="espn", title=f"Title {doc_id}",
        summary="", published_at=stamp, fetched_at=stamp, raw={},
    )


def _judgment(sample, winner: str, a=("a-item",), b=("b-item",), reason="r") -> LLMJudgment:
    return LLMJudgment(
        gsis_id=sample.gsis_id, cutoff=NOW.isoformat(), a=list(a), b=list(b), winner=winner, reason=reason
    )


def _llm_run(monkeypatch, tmp_path, judgments, judge_model="m"):
    stub_retrieval(monkeypatch, {})
    samples = tmp_path / "samples.jsonl"
    write_samples(samples, SAMPLES)
    run = tmp_path / "run"
    meta = RunMeta(samples=str(samples), a_config="a.yaml", b_config="b.yaml", judge_model=judge_model)
    RunStore.create(run, meta).append_judgments(judgments)
    store.append_items(tmp_path / "news", [_item("a-item"), _item("b-item")])
    return run


def _check(tmp_path, keys, seed=0):
    presses = iter(keys)
    return AgreementCheck(with_news_dir(tmp_path / "news"), read_key=lambda: next(presses), rng=random.Random(seed))


def test_pairs_are_rebuilt_from_recorded_ids_and_shown_blind(monkeypatch, tmp_path, capsys):
    run = _llm_run(monkeypatch, tmp_path, [_judgment(SAMPLES[0], "a")])

    [record] = _check(tmp_path, ["left"]).run(run, n=1)

    out = capsys.readouterr().out
    assert "Title a-item" in out and "Title b-item" in out
    assert "Joe Burrow (CIN QB), Week 11 vs PIT" in out
    assert record == AgreementJudgment(gsis_id="00-1", human=random.Random(0).choice(["a", "b"]), llm="a")
    assert (run / "agreement.jsonl").exists()


def test_inconsistent_llm_tie_agrees_with_a_human_tie(monkeypatch, tmp_path):
    run = _llm_run(monkeypatch, tmp_path, [_judgment(SAMPLES[0], "tie", reason="inconsistent")])

    [record] = _check(tmp_path, ["up"]).run(run, n=1)

    assert (record.human, record.llm) == ("tie", "tie")


def test_identical_pairs_are_never_drawn(monkeypatch, tmp_path):
    run = _llm_run(monkeypatch, tmp_path, [_judgment(SAMPLES[0], "tie", a=["x"], b=["x"], reason=None)])

    assert _check(tmp_path, []).run(run, n=5) == []


def test_missing_stored_item_skips_the_pair(monkeypatch, tmp_path):
    run = _llm_run(monkeypatch, tmp_path, [_judgment(SAMPLES[0], "a", a=["gone"]), _judgment(SAMPLES[1], "b")])

    records = _check(tmp_path, ["right", "right"]).run(run, n=2)

    assert [r.gsis_id for r in records] == [SAMPLES[1].gsis_id]


def test_resume_continues_toward_n_without_repeats(monkeypatch, tmp_path):
    run = _llm_run(monkeypatch, tmp_path, [_judgment(SAMPLES[0], "a"), _judgment(SAMPLES[1], "b")])
    news_cfg = with_news_dir(tmp_path / "news")

    assert len(_check(tmp_path, ["left", "q"]).run(run, n=2)) == 1
    records = AgreementCheck(news_cfg, read_key=lambda: "up").run(run, n=2)

    assert sorted(r.gsis_id for r in records) == sorted(s.gsis_id for s in SAMPLES)
    assert AgreementCheck(news_cfg, read_key=lambda: "up").run(run, n=2) == records


def test_human_run_is_refused(monkeypatch, tmp_path):
    run = _llm_run(monkeypatch, tmp_path, [], judge_model=None)

    with pytest.raises(ValueError, match="not an LLM-judged run"):
        _check(tmp_path, []).run(run, n=1)


def test_summary_rate_and_table():
    def rec(human, llm):
        return AgreementJudgment(gsis_id="x", human=human, llm=llm)

    lines = summary_lines([rec("a", "a")] * 3 + [rec("b", "a")])

    assert lines[0].startswith("Agreement: 75% of 4 pairs")
    assert lines[2] == "  a              3    0    0"
    assert lines[3] == "  b              1    0    0"
