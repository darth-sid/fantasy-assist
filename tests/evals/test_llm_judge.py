import json

import pytest

from evals.llm_judge import MAX_TOKENS, RUBRIC, JudgeVerdict, LLMJudge, summary_lines
from evals.models import LLMJudgment, RunMeta
from ffassistant.clients.llm_client import LLMClient, StructuredResponse
from tests.evals.helpers import CFG, CFG_B, SAMPLES, stub_retrieval

META = RunMeta(samples="s.jsonl", a_config="a.yaml", b_config="b.yaml", judge_model="judge-model")


class FakeJudge(LLMClient):
    """Answers with policy(first_text, second_text); records how it was called."""

    def __init__(self, policy):
        self.policy = policy
        self.requests = []
        self.mode = None

    def query(self, request):
        first, second = request.user_content.split("--- SECOND ---")
        choice = self.policy(first, second)
        if choice == "error":
            raise RuntimeError("judge down")
        return StructuredResponse(parsed=JudgeVerdict(reason="because", choice=choice), usage=None)

    def query_many(self, requests, workers=8, progress=False):
        self.mode = self.mode or "sync"
        self.requests.extend(requests)
        self.progress = progress
        return super().query_many(requests, workers)

    def query_batch(self, requests, job_file=None):
        self.mode = "batch"
        self.job_file = job_file
        return self.query_many(requests)


def prefers_a_item(first, second):
    return "first" if "a-item" in first else "second"


def _run(monkeypatch, tmp_path, policy, ids=None, sync=False, run="run", meta=META):
    stub_retrieval(monkeypatch, ids or {"bm25": ["a-item"], "recency": ["b-item"]})
    client = FakeJudge(policy)
    results = LLMJudge(CFG, CFG_B, meta, client).run(SAMPLES, tmp_path / run, sync=sync)
    return results, client


def test_each_pair_is_judged_in_both_orders(monkeypatch, tmp_path):
    results, client = _run(monkeypatch, tmp_path, prefers_a_item)

    assert len(client.requests) == 4
    first, second = client.requests[:2]
    assert first.user_content.index("a-item") < first.user_content.index("--- SECOND ---")
    assert second.user_content.index("b-item") < second.user_content.index("--- SECOND ---")
    assert (first.model, first.max_tokens, first.system[0].text) == ("judge-model", MAX_TOKENS, RUBRIC)


def test_one_record_per_pair_extending_judgment_with_reason(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path, prefers_a_item)

    lines = (tmp_path / "run" / "judgments.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert set(json.loads(lines[0])) == {"gsis_id", "cutoff", "a", "b", "winner", "reason"}


def test_meta_holds_the_judge_model_once(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path, prefers_a_item)

    assert json.loads((tmp_path / "run" / "meta.json").read_text())["judge_model"] == "judge-model"
    line = json.loads((tmp_path / "run" / "judgments.jsonl").read_text().splitlines()[0])
    assert not {"a_config", "b_config", "judge_model"} & set(line)


def test_consistent_preference_wins(monkeypatch, tmp_path):
    results, _ = _run(monkeypatch, tmp_path, prefers_a_item)

    assert [(r.winner, r.reason) for r in results] == [("a", "because")] * 2


def test_position_bias_is_flagged_inconsistent(monkeypatch, tmp_path):
    results, _ = _run(monkeypatch, tmp_path, lambda first, second: "first")

    assert {(r.winner, r.reason) for r in results} == {("tie", "inconsistent")}


def test_identical_pairs_are_not_sent(monkeypatch, tmp_path):
    results, client = _run(monkeypatch, tmp_path, prefers_a_item, ids={"bm25": ["x"], "recency": ["x"]})

    assert client.requests == []
    assert {(r.winner, r.reason, r.a == r.b) for r in results} == {("tie", None, True)}


def test_failed_pairs_are_not_recorded(monkeypatch, tmp_path, capsys):
    results, _ = _run(monkeypatch, tmp_path, lambda first, second: "error")

    assert results == []
    assert "judge down" in capsys.readouterr().out


def test_batch_by_default_sync_on_request(monkeypatch, tmp_path):
    _, batch_client = _run(monkeypatch, tmp_path, prefers_a_item)
    _, sync_client = _run(monkeypatch, tmp_path, prefers_a_item, sync=True, run="sync-run")

    assert batch_client.mode == "batch" and batch_client.job_file == tmp_path / "run" / "batch_id"
    assert sync_client.mode == "sync" and sync_client.progress


def test_rerun_skips_judged_samples(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path, prefers_a_item)
    results, client = _run(monkeypatch, tmp_path, prefers_a_item)

    assert client.requests == []
    assert len(results) == 2


def test_errored_samples_are_retried_and_replace_the_failure(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path, lambda first, second: "error")
    results, client = _run(monkeypatch, tmp_path, prefers_a_item)

    assert len(client.requests) == 4
    assert [r.winner for r in results] == ["a", "a"]


def test_rerun_with_another_judge_model_is_refused(monkeypatch, tmp_path):
    _run(monkeypatch, tmp_path, prefers_a_item)

    with pytest.raises(ValueError, match="new run directory"):
        _run(monkeypatch, tmp_path, prefers_a_item, meta=META.model_copy(update={"judge_model": "other"}))


def _judgment(winner: str, reason: str | None = "r", identical: bool = False) -> LLMJudgment:
    return LLMJudgment(
        gsis_id="x", cutoff="c", a=["1"], b=["1"] if identical else ["2"], winner=winner, reason=reason
    )


def test_summary_counts_inconsistent_as_tie_and_reports_its_rate():
    judgments = (
        [_judgment("a")] * 6 + [_judgment("b")] * 2 + [_judgment("tie")]
        + [_judgment("tie", "inconsistent")] * 3 + [_judgment("tie", None, identical=True)]
    )

    lines = summary_lines(judgments, META)

    assert lines[0] == "Results (13 pairs, judge judge-model):"
    assert "  ties: 4 (inconsistent: 3)" in lines
    assert any(line.startswith("  A win rate excluding ties: 75% of 8") for line in lines)
    assert lines[-1].startswith("  inconsistency rate: 25% of 12 judged pairs")
