"""Blind human check of a random subset of an LLM-judged run, to measure agreement with the judge."""

from __future__ import annotations

import argparse
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evals.models import AgreementJudgment, LLMJudgment
from evals.pairs import rebuild_pair, winner
from evals.run_store import RunStore
from evals.stats import wilson_interval
from evals.tui import ask_human, read_key
from ffassistant.config import CONFIG_PATH, Config, load_config

_OUTCOMES = ("a", "b", "tie")


@dataclass
class AgreementCheck:
    """Draws an LLM run's judged pairs at random and asks for blind human judgments of them."""

    cfg: Config
    read_key: Callable[[], str] = read_key
    rng: random.Random = field(default_factory=random.Random)

    def run(self, run_dir: Path, n: int) -> list[AgreementJudgment]:
        """Judges random pairs not yet in the run's agreement file until it holds n; q stops early."""
        store = RunStore.open(run_dir)
        if store.meta.judge_model is None:
            raise ValueError(f"{run_dir} is not an LLM-judged run")
        samples = {s.gsis_id: s for s in store.samples()}
        done = {a.gsis_id for a in store.agreements()}
        # Identical pairs were never judged, so there's nothing to agree with.
        pool = [
            j
            for j in store.judgments(LLMJudgment)
            if not j.identical and j.gsis_id not in done
        ]
        self.rng.shuffle(pool)

        judged = len(done)
        for judgment in pool:
            if judged >= n:
                break
            pair = rebuild_pair(samples[judgment.gsis_id], judgment.a, judgment.b, self.cfg)
            if pair is None:
                continue
            first = self.rng.choice(["a", "b"])
            choice = ask_human(pair, first, f"agreement check {judged + 1}/{n}", self.read_key)
            if choice == "quit":
                break
            record = AgreementJudgment(
                gsis_id=judgment.gsis_id, human=winner(choice, first), llm=judgment.winner
            )
            store.append_agreements([record])
            judged += 1
        return store.agreements()


def summary_lines(records: list[AgreementJudgment]) -> list[str]:
    """Agreement rate with a Wilson 95% CI, then counts of human vs LLM outcomes."""
    if not records:
        return ["No agreement judgments yet."]
    agreed = sum(r.human == r.llm for r in records)
    low, high = wilson_interval(agreed, len(records))
    pairs = Counter((r.human, r.llm) for r in records)
    lines = [
        f"Agreement: {agreed / len(records):.0%} of {len(records)} pairs "
        f"(95% CI {low:.0%} to {high:.0%}); LLM inconsistent verdicts count as tie",
        "  human \\ LLM    a    b  tie",
    ]
    for outcome in _OUTCOMES:
        cells = "".join(f"{pairs[(outcome, llm)]:>5}" for llm in _OUTCOMES)
        lines.append(f"  {outcome:<11}{cells}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.agreement")
    parser.add_argument("run", type=Path, help="run directory from evals.llm_judge")
    parser.add_argument("-n", type=int, default=20, help="how many pairs to judge in total")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config for the news store")
    args = parser.parse_args()

    records = AgreementCheck(load_config(args.config)).run(args.run, args.n)
    print()
    print("\n".join(summary_lines(records)))


if __name__ == "__main__":
    main()
