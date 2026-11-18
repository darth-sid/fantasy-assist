"""Eval files on disk: samples files, and run directories (meta.json once, judgments as JSONL)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from evals.models import AgreementJudgment, EvalSample, RunMeta

_META = "meta.json"
_JUDGMENTS = "judgments.jsonl"
_AGREEMENTS = "agreement.jsonl"
_BATCH = "batch_id"


def _read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [model.model_validate_json(line) for line in lines if line.strip()]


def _append_jsonl(path: Path, records: list[BaseModel]) -> None:
    # Flushed per record so a crash keeps everything written so far.
    with path.open("a", encoding="utf-8") as out:
        for record in records:
            out.write(record.model_dump_json() + "\n")
            out.flush()


def load_samples(path: Path) -> list[EvalSample]:
    """The samples in a file written by write_samples."""
    return _read_jsonl(path, EvalSample)


def write_samples(path: Path, samples: list[EvalSample]) -> None:
    """Writes a samples file, replacing any existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(s.model_dump_json() + "\n" for s in samples), encoding="utf-8")


class RunStore:
    """One run directory: its meta, judgments, agreement checks, and in-flight batch."""

    def __init__(self, run_dir: Path, meta: RunMeta):
        self.dir = run_dir
        self.meta = meta

    @classmethod
    def create(cls, run_dir: Path, meta: RunMeta) -> RunStore:
        """Starts a run, or resumes one; raises if the existing run compares something else."""
        if (run_dir / _META).exists():
            store = cls.open(run_dir)
            if store.meta != meta:
                raise ValueError(f"{run_dir} is a run of {store.meta}; use a new run directory")
            return store
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / _META).write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return cls(run_dir, meta)

    @classmethod
    def open(cls, run_dir: Path) -> RunStore:
        """An existing run."""
        meta = RunMeta.model_validate_json((run_dir / _META).read_text(encoding="utf-8"))
        return cls(run_dir, meta)

    def samples(self) -> list[EvalSample]:
        """The samples file this run was made from."""
        return load_samples(Path(self.meta.samples))

    def judgments[T: BaseModel](self, model: type[T]) -> list[T]:
        return _read_jsonl(self.dir / _JUDGMENTS, model)

    def append_judgments(self, records: list[BaseModel]) -> None:
        _append_jsonl(self.dir / _JUDGMENTS, records)

    def agreements(self) -> list[AgreementJudgment]:
        return _read_jsonl(self.dir / _AGREEMENTS, AgreementJudgment)

    def append_agreements(self, records: list[AgreementJudgment]) -> None:
        _append_jsonl(self.dir / _AGREEMENTS, records)

    @property
    def batch_file(self) -> Path:
        """Where a provider batch records its id while in flight, so a rerun can resume it."""
        return self.dir / _BATCH
