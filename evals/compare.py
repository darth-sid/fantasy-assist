"""Blind A/B comparison of two configs' news retrieval, judged per player in the terminal."""

from __future__ import annotations

import argparse
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evals.cli import add_config_args, load_configs
from evals.models import EvalSample, Judgment, RunMeta
from evals.pairs import check_seasons, doc_ids, retrieve_pair, winner
from evals.run_store import RunStore, load_samples
from evals.stats import win_rate_line
from evals.tui import ask_human, read_key
from ffassistant.config import Config


def summary_lines(judgments: list[Judgment], meta: RunMeta) -> list[str]:
    """Win counts, then A's win rate excluding ties with a Wilson 95% CI and sign test p."""
    counts = Counter("identical" if j.identical else j.winner for j in judgments)
    return [
        f"Results ({len(judgments)} judgments):",
        f"  A ({meta.a_config}): {counts['a']} wins",
        f"  B ({meta.b_config}): {counts['b']} wins",
        f"  ties: {counts['tie']}",
        f"  identical (auto-tied): {counts['identical']}",
        win_rate_line(counts["a"], counts["b"]),
    ]


@dataclass
class Comparison:
    """Two configs to compare blind, plus the keypress source and side shuffler."""

    cfg_a: Config
    cfg_b: Config
    meta: RunMeta
    read_key: Callable[[], str] = read_key
    rng: random.Random = field(default_factory=random.Random)

    def run(self, samples: list[EvalSample], run_dir: Path) -> list[Judgment]:
        """Judges every sample not already in the run, appending as it goes; q stops early."""
        check_seasons(samples, self.cfg_a, self.cfg_b)
        store = RunStore.create(run_dir, self.meta)
        done = {j.gsis_id for j in store.judgments(Judgment)}

        for n, sample in enumerate(samples, 1):
            if sample.gsis_id in done:
                continue
            judgment = self._judge(sample, f"{n}/{len(samples)}")
            if judgment == "quit":
                break
            if judgment is not None:
                store.append_judgments([judgment])
        return store.judgments(Judgment)

    def _judge(self, sample: EvalSample, progress: str) -> Judgment | str | None:
        pair = retrieve_pair(sample, self.cfg_a, self.cfg_b)
        if pair is None:
            return None
        record = dict(
            gsis_id=sample.gsis_id,
            cutoff=pair.cutoff.isoformat(timespec="seconds"),
            a=doc_ids(pair.a),
            b=doc_ids(pair.b),
        )
        if pair.identical:
            return Judgment(**record, winner="tie")

        first = self.rng.choice(["a", "b"])
        choice = ask_human(pair, first, progress, self.read_key)
        if choice == "quit":
            return "quit"
        return Judgment(**record, winner=winner(choice, first))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.compare")
    parser.add_argument("samples", type=Path, help="samples JSONL from evals.generate")
    add_config_args(parser)
    parser.add_argument("-o", "--output", type=Path, required=True, help="run directory (resumable)")
    args = parser.parse_args()

    cfg_a, cfg_b = load_configs(args)
    meta = RunMeta(samples=str(args.samples), a_config=str(args.a), b_config=str(args.b))
    judgments = Comparison(cfg_a, cfg_b, meta).run(load_samples(args.samples), args.output)

    print()
    print("\n".join(summary_lines(judgments, meta)))


if __name__ == "__main__":
    main()
