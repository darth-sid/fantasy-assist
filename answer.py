from __future__ import annotations

from clients.anthropic_client import generate_answer
from contracts import Answer, ParsedRequest, ResolvedContext, SourceResult
from sources.recent_stats import RecentStatsData

_POINTS_KEYS = ("fantasy_points", "fantasy_points_ppr")


def _points_for_format(stats: dict[str, float], scoring_format: str) -> dict[str, float]:
    standard, ppr = stats["fantasy_points"], stats["fantasy_points_ppr"]
    by_format = {
        "Standard": standard,
        "PPR": ppr,
        # ppr - standard is exactly receptions, so the midpoint is exactly half-PPR
        "Half-PPR": (standard + ppr) / 2,
    }
    if scoring_format in by_format:
        return {f"fantasy_points ({scoring_format})": by_format[scoring_format]}
    return {"fantasy_points (Standard)": standard, "fantasy_points (PPR)": ppr}


def _render_player(ctx: ResolvedContext, result: SourceResult[RecentStatsData]) -> list[str]:
    lines = [f"## {ctx.player_name} ({ctx.team})"]
    if result.status == "error":
        lines.append(f"recent_stats failed to load: {result.error}")
    elif result.status == "empty":
        lines.append(f"No games played before Week {ctx.week}.")
    else:
        for game in result.data.games:
            raw = {k: v for k, v in game.stats.items() if k not in _POINTS_KEYS}
            stats = {**raw, **_points_for_format(game.stats, ctx.scoring_format)}
            rendered = ", ".join(f"{name}={value:g}" for name, value in stats.items())
            lines.append(f"Week {game.week} vs {game.opponent}: {rendered}")
    return lines


def render_context(
    parsed: ParsedRequest,
    players: list[tuple[ResolvedContext, SourceResult[RecentStatsData]]],
) -> str:
    lines = [
        f"Question: {parsed.raw_prompt}",
        f"Week: {parsed.week}",
        f"Scoring format: {parsed.scoring_format}",
    ]
    for ctx, result in players:
        lines.append("")
        lines.extend(_render_player(ctx, result))
    return "\n".join(lines)


def answer(
    parsed: ParsedRequest,
    players: list[tuple[ResolvedContext, SourceResult[RecentStatsData]]],
) -> Answer:
    generated = generate_answer(render_context(parsed, players))
    return Answer(answer=generated.answer, cited_doc_ids=generated.cited_doc_ids)
