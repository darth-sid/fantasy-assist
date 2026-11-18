"""One sample's news under configs A and B as two flat lists, retrieved live or rebuilt from doc_ids."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from evals.models import EvalSample, Side
from ffassistant.answering.models import ResolvedContext, SourceResult
from ffassistant.answering.player_context import player_context
from ffassistant.answering.sources.news import NewsData, NewsEntry, news, news_entry
from ffassistant.answering.sources.schedule import news_cutoff, schedule, target_week
from ffassistant.config import Config
from ffassistant.ingest.store import iter_items
from ffassistant.resolution.models import ValidPlayer


@dataclass
class Pair:
    """Both configs' news for one sample, plus the player header shown above it."""

    sample: EvalSample
    team: str
    opponent: str
    cutoff: datetime
    a: list[NewsEntry]
    b: list[NewsEntry]

    @property
    def identical(self) -> bool:
        return doc_ids(self.a) == doc_ids(self.b)


def doc_ids(entries: list[NewsEntry]) -> list[str]:
    return [entry.doc_id for entry in entries]


def _context(sample: EvalSample, cfg: Config) -> tuple[ResolvedContext, str, datetime] | None:
    valid = ValidPlayer(
        mention=sample.full_name,
        player_id=sample.gsis_id,
        full_name=sample.full_name,
        position=sample.position,
    )
    ctx = player_context(valid, sample.season, sample.week, cfg.default_scoring_format)
    sched = schedule(ctx)
    cutoff = news_cutoff(sched, sample.week, datetime.fromisoformat(sample.as_of))
    if cutoff is None:
        return None
    opponent = target_week(sched, sample.week).opponent
    return ctx, opponent, cutoff


def _flat(result: SourceResult[NewsData]) -> list[NewsEntry]:
    # Buckets are a retrieval design choice; eval judges one list, in retrieved order.
    if result.status != "ok":
        return []
    return [*result.data.player, *result.data.team, *result.data.opponent]


def retrieve_pair(sample: EvalSample, cfg_a: Config, cfg_b: Config) -> Pair | None:
    """Runs news() under both configs, frozen at the sample's as_of.
    None, with a printed reason, on a bye, no schedule, or a news error."""
    context = _context(sample, cfg_a)
    if context is None:
        print(f"skipped {sample.full_name}: bye or schedule unavailable")
        return None
    ctx, opponent, cutoff = context
    as_of = datetime.fromisoformat(sample.as_of)
    results = [news(ctx, opponent, cutoff, cfg, fetched_before=as_of) for cfg in (cfg_a, cfg_b)]
    errors = [r.error for r in results if r.status == "error"]
    if errors:
        print(f"skipped {sample.full_name}: news failed to load: {errors[0]}")
        return None
    return Pair(sample, ctx.team, opponent, cutoff, _flat(results[0]), _flat(results[1]))


def rebuild_pair(sample: EvalSample, a: list[str], b: list[str], cfg: Config) -> Pair | None:
    """The pair exactly as judged, from recorded doc_ids; None, with a reason, if any is gone."""
    context = _context(sample, cfg)
    if context is None:
        print(f"skipped {sample.full_name}: bye or schedule unavailable")
        return None
    ctx, opponent, cutoff = context
    wanted = {*a, *b}
    items = {item.doc_id: item for item in iter_items(cfg.news_dir) if item.doc_id in wanted}
    if wanted - items.keys():
        print(f"skipped {sample.full_name}: a recorded item is missing from the news store")
        return None
    entries = lambda ids: [news_entry(items[doc_id], cfg.news.max_summary_chars) for doc_id in ids]
    return Pair(sample, ctx.team, opponent, cutoff, entries(a), entries(b))


def _side_lines(label: str, entries: list[NewsEntry]) -> list[str]:
    lines = [f"--- {label} ---"]
    for entry in entries:
        text = f"{entry.title}. {entry.summary}" if entry.summary else entry.title
        lines.append(f"  - {entry.published_at[:10]} {entry.source}: {text}")
    if not entries:
        lines.append("  - none")
    return lines


def render_pair(pair: Pair, first: Side) -> str:
    """The text a judge (human or LLM) sees: the player header, then FIRST and SECOND news."""
    sides = {"a": pair.a, "b": pair.b}
    sample = pair.sample
    header = (
        f"{sample.full_name} ({pair.team} {sample.position}), Week {sample.week} "
        f"vs {pair.opponent}, news before {pair.cutoff:%Y-%m-%d %H:%M} UTC"
    )
    return "\n".join(
        [
            header,
            "",
            *_side_lines("FIRST", sides[first]),
            "",
            *_side_lines("SECOND", sides[other(first)]),
        ]
    )


def other(side: Side) -> Side:
    return "b" if side == "a" else "a"


def winner(choice: str, first: Side) -> str:
    """Maps a first / second / tie choice back to config a, b, or tie."""
    return {"first": first, "second": other(first), "tie": "tie"}[choice]


def check_seasons(samples: list[EvalSample], *cfgs: Config) -> None:
    """Raises if any sample's season differs from a config's."""
    for cfg in cfgs:
        mismatched = {s.season for s in samples} - {cfg.season}
        if mismatched:
            raise ValueError(f"sample seasons {sorted(mismatched)} don't match config season {cfg.season}")
