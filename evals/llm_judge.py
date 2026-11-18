"""LLM-as-judge for two configs' news retrieval: each pair judged blind in both orders."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from evals.cli import add_config_args, load_configs
from evals.models import EvalSample, LLMJudgment, RunMeta, Side
from evals.pairs import Pair, check_seasons, doc_ids, render_pair, retrieve_pair, winner
from evals.run_store import RunStore, load_samples
from evals.stats import wilson_interval, win_rate_line
from ffassistant.clients.llm_client import (
    LLMClient,
    QueryError,
    QueryRequest,
    SystemBlock,
    get_llm_client,
)
from ffassistant.config import Config, load_config

# Haiku-class judges think by default and thinking counts toward this; the verdict itself is tiny.
MAX_TOKENS = 1024
INCONSISTENT = "inconsistent"

RUBRIC = """You judge news retrieval for a fantasy football start/sit assistant.

You get one player and week, then two lists of news items, FIRST and SECOND.
Decide which list would better help someone decide whether to start this
player this week.

- Most valuable: news on the player's own availability, health, and role.
- Also useful: teammate news that changes the player's usage (injuries, depth
  chart, workload) and news on the opponent's defense (injuries, key players).
- Prefer recent items over stale ones.
- Penalize items that don't bear on this decision (other teams' storylines,
  front-office news, game recaps with nothing on usage or availability).
- Don't prefer a list just because it has more items.
- Answer "tie" when both lists are about equally useful.

Give your reason in at most two sentences, then your choice."""


class JudgeVerdict(BaseModel):
    reason: str = Field(description="Why, in at most two sentences.")
    choice: Literal["first", "second", "tie"]


def _request(pair: Pair, first: Side, judge_model: str) -> QueryRequest:
    return QueryRequest(
        model=judge_model,
        system=[SystemBlock(RUBRIC, cache=True)],
        user_content=render_pair(pair, first),
        output_model=JudgeVerdict,
        max_tokens=MAX_TOKENS,
    )


def combine(a_first: JudgeVerdict, b_first: JudgeVerdict) -> tuple[str, str]:
    """The agreed winner with A-first's reason, or a tie with reason "inconsistent"."""
    a_winner, b_winner = winner(a_first.choice, "a"), winner(b_first.choice, "b")
    if a_winner != b_winner:
        return "tie", INCONSISTENT
    return a_winner, a_first.reason


def is_inconsistent(judgment: LLMJudgment) -> bool:
    return judgment.reason == INCONSISTENT


def _record(pair: Pair, winner_: str, reason: str | None) -> LLMJudgment:
    return LLMJudgment(
        gsis_id=pair.sample.gsis_id,
        cutoff=pair.cutoff.isoformat(timespec="seconds"),
        a=doc_ids(pair.a),
        b=doc_ids(pair.b),
        winner=winner_,
        reason=reason,
    )


@dataclass
class LLMJudge:
    """Two configs to compare, the run's meta (with the judge model), and the client that runs it."""

    cfg_a: Config
    cfg_b: Config
    meta: RunMeta
    client: LLMClient

    def run(
        self, samples: list[EvalSample], run_dir: Path, sync: bool = False, workers: int = 8
    ) -> list[LLMJudgment]:
        """Judges every sample not already in the run and appends one record per pair.
        A pair whose calls fail isn't written, so the next run retries it."""
        check_seasons(samples, self.cfg_a, self.cfg_b)
        store = RunStore.create(run_dir, self.meta)
        done = {j.gsis_id for j in store.judgments(LLMJudgment)}

        records: list[LLMJudgment] = []
        to_judge: list[Pair] = []
        for sample in samples:
            if sample.gsis_id in done:
                continue
            pair = retrieve_pair(sample, self.cfg_a, self.cfg_b)
            if pair is None:
                continue
            if pair.identical:
                records.append(_record(pair, "tie", None))
            else:
                to_judge.append(pair)

        # Two requests per pair, A first then B first, so position bias shows up.
        judge_model = self.meta.judge_model
        requests = [_request(pair, first, judge_model) for pair in to_judge for first in ("a", "b")]
        if sync:
            responses = self.client.query_many(requests, workers)
        else:
            responses = self.client.query_batch(requests, job_file=store.batch_file)

        for i, pair in enumerate(to_judge):
            a_first, b_first = responses[2 * i : 2 * i + 2]
            errors = [r.message for r in (a_first, b_first) if isinstance(r, QueryError)]
            if errors:
                print(f"judge failed for {pair.sample.full_name}, retried next run: {errors[0]}")
                continue
            records.append(_record(pair, *combine(a_first.parsed, b_first.parsed)))

        store.append_judgments(records)
        return store.judgments(LLMJudgment)


def summary_lines(judgments: list[LLMJudgment], meta: RunMeta) -> list[str]:
    """Outcome counts, A's win rate (inconsistent counted as tie), and the inconsistency rate."""
    counts = Counter("identical" if j.identical else j.winner for j in judgments)
    inconsistent = sum(is_inconsistent(j) for j in judgments)
    judged = len(judgments) - counts["identical"]
    lines = [
        f"Results ({len(judgments)} pairs, judge {meta.judge_model}):",
        f"  A ({meta.a_config}): {counts['a']} wins",
        f"  B ({meta.b_config}): {counts['b']} wins",
        f"  ties: {counts['tie']} (inconsistent: {inconsistent})",
        f"  identical (not sent to the judge): {counts['identical']}",
        win_rate_line(counts["a"], counts["b"]),
    ]
    if judged:
        low, high = wilson_interval(inconsistent, judged)
        lines.append(
            f"  inconsistency rate: {inconsistent / judged:.0%} of {judged} judged pairs "
            f"(95% CI {low:.0%} to {high:.0%})"
        )
    return lines


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m evals.llm_judge")
    parser.add_argument("samples", type=Path, help="samples JSONL from evals.generate")
    add_config_args(parser)
    parser.add_argument("-o", "--output", type=Path, required=True, help="run directory (resumable)")
    parser.add_argument("--sync", action="store_true", help="concurrent calls instead of a batch")
    parser.add_argument("--workers", type=int, default=8, help="concurrent calls with --sync")
    args = parser.parse_args()

    base = load_config(args.config)
    cfg_a, cfg_b = load_configs(args)
    meta = RunMeta(
        samples=str(args.samples),
        a_config=str(args.a),
        b_config=str(args.b),
        judge_model=base.llm.judge_model,
    )
    llm_judge = LLMJudge(cfg_a, cfg_b, meta, get_llm_client(base.llm))
    judgments = llm_judge.run(
        load_samples(args.samples), args.output, sync=args.sync, workers=args.workers
    )
    print()
    print("\n".join(summary_lines(judgments, meta)))


if __name__ == "__main__":
    main()
