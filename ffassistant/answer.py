from __future__ import annotations

from dataclasses import dataclass

from ffassistant.clients.anthropic_client import generate_answer
from ffassistant.contracts import Answer, ParsedRequest, ResolvedContext, SourceResult
from ffassistant.sources.recent_stats import GameLine, RecentStatsData
from ffassistant.sources.schedule import ScheduleData, ScheduleWeek

_POINTS_KEYS = ("fantasy_points", "fantasy_points_ppr")
_KICKER_LINE = "fantasy points unavailable for kickers (kicking is not scored in the source data)"


@dataclass
class PlayerInputs:
    ctx: ResolvedContext
    recent_stats: SourceResult[RecentStatsData]
    schedule: SourceResult[ScheduleData]


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


def _game_line(game: GameLine, scoring_format: str, is_kicker: bool) -> str:
    stats = {k: v for k, v in game.stats.items() if k not in _POINTS_KEYS}
    if not is_kicker:
        stats.update(_points_for_format(game.stats, scoring_format))
    rendered = ", ".join(f"{name}={value:g}" for name, value in stats.items())
    return f"Week {game.week} vs {game.opponent}: {rendered}"


def _target_week_line(week: ScheduleWeek) -> str:
    if week.opponent is None:
        return f"Week {week.week}: BYE"
    return f"Week {week.week}: {'vs' if week.home else '@'} {week.opponent}"


def _past_week_line(
    week: ScheduleWeek,
    stats: SourceResult[RecentStatsData],
    games: dict[int, GameLine],
    scoring_format: str,
    is_kicker: bool,
) -> str:
    if week.opponent is None:
        return f"Week {week.week}: BYE"
    if not week.played:
        return f"Week {week.week} vs {week.opponent}: game not yet played, stats pending"
    if stats.status == "error":
        return f"Week {week.week} vs {week.opponent}: stats unavailable"
    if week.week in games:
        return _game_line(games[week.week], scoring_format, is_kicker)
    return f"Week {week.week} vs {week.opponent}: did not play"


def _render_player(inputs: PlayerInputs) -> list[str]:
    ctx, stats, sched = inputs.ctx, inputs.recent_stats, inputs.schedule
    is_kicker = stats.status == "ok" and stats.data.position == "K"
    games = {game.week: game for game in stats.data.games} if stats.status == "ok" else {}

    lines = [f"## {ctx.player_name} ({ctx.team})"]

    if sched.status == "ok":
        weeks = {week.week: week for week in sched.data.weeks}
        lines.append(_target_week_line(weeks[ctx.week]))
        if is_kicker:
            lines.append(_KICKER_LINE)
        if stats.status == "error":
            lines.append(f"recent_stats failed to load: {stats.error}")
        for week_num in range(1, ctx.week):
            lines.append(
                _past_week_line(weeks[week_num], stats, games, ctx.scoring_format, is_kicker)
            )
        return lines

    if sched.status == "error":
        lines.append(f"schedule failed to load: {sched.error}")
    else:
        lines.append(f"No schedule found for {ctx.team} through Week {ctx.week}.")
    if is_kicker:
        lines.append(_KICKER_LINE)
    if stats.status == "error":
        lines.append(f"recent_stats failed to load: {stats.error}")
    elif stats.status == "empty":
        lines.append(f"No games played before Week {ctx.week}.")
    else:
        lines.extend(_game_line(game, ctx.scoring_format, is_kicker) for game in stats.data.games)
    return lines


def render_context(parsed: ParsedRequest, players: list[PlayerInputs]) -> str:
    lines = [
        f"Question: {parsed.raw_prompt}",
        f"Week: {parsed.week}",
        f"Scoring format: {parsed.scoring_format}",
    ]
    for inputs in players:
        lines.append("")
        lines.extend(_render_player(inputs))
    return "\n".join(lines)


def answer(parsed: ParsedRequest, players: list[PlayerInputs]) -> Answer:
    generated = generate_answer(render_context(parsed, players))
    return Answer(answer=generated.answer, cited_doc_ids=generated.cited_doc_ids)
