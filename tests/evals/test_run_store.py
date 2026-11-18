import pytest

from evals.models import Judgment, RunMeta
from evals.run_store import RunStore, load_samples, write_samples
from tests.evals.helpers import SAMPLES

META = RunMeta(samples="s.jsonl", a_config="a.yaml", b_config="b.yaml")


def test_samples_round_trip(tmp_path):
    write_samples(tmp_path / "nested" / "s.jsonl", SAMPLES)

    assert load_samples(tmp_path / "nested" / "s.jsonl") == SAMPLES


def test_create_then_open_round_trips_meta_and_judgments(tmp_path):
    judgment = Judgment(gsis_id="00-1", cutoff="c", a=["x"], b=["y"], winner="a")
    RunStore.create(tmp_path / "run", META).append_judgments([judgment])

    store = RunStore.open(tmp_path / "run")

    assert store.meta == META
    assert store.judgments(Judgment) == [judgment]
    assert store.agreements() == []


def test_create_resumes_a_matching_run_and_refuses_another(tmp_path):
    RunStore.create(tmp_path / "run", META)

    assert RunStore.create(tmp_path / "run", META).meta == META
    with pytest.raises(ValueError, match="new run directory"):
        RunStore.create(tmp_path / "run", META.model_copy(update={"b_config": "c.yaml"}))


def test_samples_come_from_the_file_meta_points_at(tmp_path):
    write_samples(tmp_path / "s.jsonl", SAMPLES)
    store = RunStore.create(tmp_path / "run", META.model_copy(update={"samples": str(tmp_path / "s.jsonl")}))

    assert store.samples() == SAMPLES
