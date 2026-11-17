"""Blind A/B comparison of two configs' news retrieval, judged per player in the terminal."""

from __future__ import annotations

import argparse
import os
import random
import sys
import termios
import tty
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from evals.models import EvalSample, Judgment
from ffassistant.answering.generate import news_cutoff
from ffassistant.answering.models import SourceResult
from ffassistant.answering.player_context import player_context
from ffassistant.answering.sources.news import NewsData, NewsEntry, news
from ffassistant.answering.sources.schedule import schedule
from ffassistant.config import Config, load_config
from ffassistant.resolution.models import ValidPlayer

_ARROWS = {b"\x1b[D": "left", b"\x1b[C": "right", b"\x1b[A": "up", b"\x1b[B": "down"}
_CHOICES = {"left": "left", "right": "right", "up": "tie", "down": "tie", "q": "quit"}
_KEYS_HELP = "← left better   → right better   ↑/↓ tie   q quit"


def read_key() -> str:
    """Reads one keypress: 'left' / 'right' / 'up' / 'down' for arrows, else the character."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        data = os.read(fd, 3)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return _ARROWS.get(data, data.decode(errors="ignore"))


def _selection(result: SourceResult[NewsData]) -> tuple:
    if result.status != "ok":
        return (result.status, result.error)
    data = result.data
    return tuple(tuple(e.doc_id for e in bucket) for bucket in (data.player, data.team, data.opponent))


def _entry_line(entry: NewsEntry) -> str:
    text = f"{entry.title}. {entry.summary}" if entry.summary else entry.title
    return f"  - {entry.published_at[:10]} {entry.source}: {text}"


def _side_lines(label: str, result: SourceResult[NewsData], player: str, team: str, opp: str) -> list[str]:
    lines = [f"--- {label} ---"]
    if result.status != "ok":
        return [*lines, f"news: {result.status}" + (f": {result.error}" if result.error else "")]
    groups = [
        (f"About {player}:", result.data.player),
        (f"{team} team news:", result.data.team),
        (f"Opponent ({opp}) news:", result.data.opponent),
    ]
    for heading, entries in groups:
        lines.append(heading)
        lines.extend(_entry_line(e) for e in entries)
        if not entries:
            lines.append("  - none")
    return lines


def _load_judgments(path: Path) -> list[Judgment]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Judgment.model_validate_json(line) for line in lines if line.strip()]


def tally(judgments: list[Judgment]) -> Counter:
    """Counts wins per config, judged ties, and identical (auto) ties."""
    return Counter(
        "identical" if j.choice == "identical" else j.winner for j in judgments
    )


@dataclass
class Comparison:
    """Two configs to compare blind, plus the keypress source, clock, and side shuffler."""

    cfg_a: Config
    cfg_b: Config
    a_label: str
    b_label: str
    read_key: Callable[[], str] = read_key
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rng: random.Random = field(default_factory=random.Random)

    def run(self, samples: list[EvalSample], out_path: Path) -> list[Judgment]:
        """Judges every sample not already in out_path, appending as it goes; q stops early."""
        for cfg in (self.cfg_a, self.cfg_b):
            mismatched = {s.season for s in samples} - {cfg.season}
            if mismatched:
                raise ValueError(
                    f"sample seasons {sorted(mismatched)} don't match config season {cfg.season}"
                )
        existing = _load_judgments(out_path)
        if any((j.a_config, j.b_config) != (self.a_label, self.b_label) for j in existing):
            raise ValueError(f"{out_path} has judgments for other configs; use a new output file")
        done = {j.sample_id for j in existing}

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as out:
            for n, sample in enumerate(samples, 1):
                if sample.id in done:
                    continue
                judgment = self._judge(sample, f"{n}/{len(samples)}")
                if judgment == "quit":
                    return _load_judgments(out_path)
                if judgment is not None:
                    out.write(judgment.model_dump_json() + "\n")
                    out.flush()
        return _load_judgments(out_path)

    def _judge(self, sample: EvalSample, progress: str) -> Judgment | str | None:
        valid = ValidPlayer(
            mention=sample.full_name,
            player_id=sample.gsis_id,
            full_name=sample.full_name,
            position=sample.position,
        )
        ctx = player_context(valid, sample.season, sample.week, self.cfg_a.default_scoring_format)
        sched = schedule(ctx)
        cutoff = news_cutoff(sched, sample.week, self.now)
        if cutoff is None:
            print(f"skipped {sample.full_name} ({sample.id}): bye or schedule unavailable")
            return None
        opponent = next(w.opponent for w in sched.data.weeks if w.week == sample.week)
        results = {
            "a": news(ctx, opponent, cutoff, self.cfg_a),
            "b": news(ctx, opponent, cutoff, self.cfg_b),
        }

        record = dict(sample_id=sample.id, a_config=self.a_label, b_config=self.b_label)
        if _selection(results["a"]) == _selection(results["b"]):
            return Judgment(**record, left=None, choice="identical", winner="tie")

        left = self.rng.choice(["a", "b"])
        right = "b" if left == "a" else "a"
        names = (ctx.player_name, ctx.team, opponent)
        print()
        print(f"=== {sample.id} ({progress})")
        print(
            f"{ctx.player_name} ({ctx.team} {ctx.position}), Week {sample.week} vs {opponent}, "
            f"news before {cutoff:%Y-%m-%d %H:%M} UTC"
        )
        print()
        print("\n".join(_side_lines("LEFT", results[left], *names)))
        print()
        print("\n".join(_side_lines("RIGHT", results[right], *names)))
        print()
        print(_KEYS_HELP)

        while (choice := _CHOICES.get(self.read_key())) is None:
            pass
        if choice == "quit":
            return "quit"
        winner = {"left": left, "right": right, "tie": "tie"}[choice]
        return Judgment(**record, left=left, choice=choice, winner=winner)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.compare")
    parser.add_argument("samples", type=Path, help="samples JSONL from evals.generate")
    parser.add_argument("-a", type=Path, required=True, help="config A")
    parser.add_argument("-b", type=Path, required=True, help="config B")
    parser.add_argument("-o", "--output", type=Path, required=True, help="judgments JSONL (appended; resumable)")
    args = parser.parse_args()

    lines = args.samples.read_text(encoding="utf-8").splitlines()
    samples = [EvalSample.model_validate_json(line) for line in lines if line.strip()]
    comparison = Comparison(load_config(args.a), load_config(args.b), str(args.a), str(args.b))
    judgments = comparison.run(samples, args.output)

    counts = tally(judgments)
    print()
    print(f"Results ({len(judgments)} judgments in {args.output}):")
    print(f"  A ({args.a}): {counts['a']} wins")
    print(f"  B ({args.b}): {counts['b']} wins")
    print(f"  ties: {counts['tie']}")
    print(f"  identical (auto-tied): {counts['identical']}")


if __name__ == "__main__":
    main()
