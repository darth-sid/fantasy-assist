from __future__ import annotations

import re

from ffassistant.answering.models import PlayerInputs, ResolvedContext, SourceResult
from ffassistant.answering.sources.defense import DefenseData
from ffassistant.answering.sources.injuries import InjuryData
from ffassistant.answering.sources.recent_stats import GameLine, RecentStatsData
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from ffassistant.resolution.models import ValidatedRequest

_POINTS_KEYS = ("fantasy_points", "fantasy_points_ppr")
_KICKER_LINE = "fantasy points unavailable for kickers (kicking is not scored in the source data)"
_KICKER_MATCHUP_LINE = "Matchup unavailable for kickers (kicking is not scored in the source data)"
_MATCHUP_CAVEAT = "Points allowed is a small early-season sample and is not adjusted for opponents faced."
_ROSTER_STATUS_MEANINGS = {
    "RES": "reserve list, not available to play",
    "INA": "inactive",
    "PUP": "physically unable to perform list, not available to play",
    "CUT": "released",
    "DEV": "practice squad",
    "RET": "retired",
}
_CURLY_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalize_name(name: str) -> str:
    normalized = name.strip().lower().translate(_CURLY_QUOTES)
    return re.sub(r"\s+", " ", normalized)


def _points_for_format(standard: float, ppr: float, scoring_format: str) -> float:
    by_format = {
        "Standard": standard,
        "PPR": ppr,
        # ppr - standard is exactly receptions, so the midpoint is exactly half-PPR
        "Half-PPR": (standard + ppr) / 2,
    }
    return by_format[scoring_format]


def _game_line(game: GameLine, scoring_format: str, is_kicker: bool, venue: str = "vs") -> str:
    stats = {k: v for k, v in game.stats.items() if k not in _POINTS_KEYS}
    if not is_kicker:
        stats[f"fantasy_points ({scoring_format})"] = _points_for_format(
            game.stats["fantasy_points"], game.stats["fantasy_points_ppr"], scoring_format
        )
    rendered = ", ".join(f"{name}={value:g}" for name, value in stats.items())
    return f"Week {game.week} {venue} {game.opponent}: {rendered}"


def _venue(week: ScheduleWeek) -> str:
    return "vs" if week.home else "@"


def _target_week_line(week: ScheduleWeek) -> str:
    if week.opponent is None:
        return f"Week {week.week}: BYE"
    return f"Week {week.week}: {_venue(week)} {week.opponent}"


def _roster_status_lines(ctx: ResolvedContext) -> list[str]:
    if ctx.roster_status == "ACT":
        return []
    meaning = _ROSTER_STATUS_MEANINGS.get(ctx.roster_status, "unrecognized status code")
    return [f"Roster status: {ctx.roster_status} ({meaning})"]


def _injury_lines(
    ctx: ResolvedContext,
    injuries: SourceResult[InjuryData],
    sched: SourceResult[ScheduleData],
) -> list[str]:
    if sched.status == "ok" and any(
        week.week == ctx.week and week.opponent is None for week in sched.data.weeks
    ):
        return []
    if injuries.status == "error":
        return [f"Week {ctx.week} injury report failed to load: {injuries.error}"]
    if injuries.status == "empty":
        return [f"Week {ctx.week} injury report not available yet"]
    entry = injuries.data.entry
    if entry is None:
        return [f"Not on the Week {ctx.week} injury report"]
    line = f"Injury report (Week {ctx.week}): {entry.report_status or 'no game designation'}"
    if entry.primary_injury is not None:
        line += f" ({entry.primary_injury})"
    if entry.practice_status is not None:
        line += f". Practice: {entry.practice_status}"
    return [line]


def _matchup_line(opponent: str, defense: DefenseData, scoring_format: str) -> str:
    by_team = {
        row.team: _points_for_format(row.standard_pg, row.ppr_pg, scoring_format)
        for row in defense.rows
    }
    value = by_team[opponent]
    # Ranked at display precision so teams that look tied in the context share a rank.
    rank = 1 + sum(round(other, 1) > round(value, 1) for other in by_team.values())
    average = sum(by_team.values()) / len(by_team)
    games = next(row.games for row in defense.rows if row.team == opponent)
    return (
        f"Matchup: {opponent} has allowed {value:.1f} {scoring_format} points per game to "
        f"{defense.position}s (rank {rank} of {len(by_team)}, 1 = most allowed, "
        f"league avg {average:.1f}, {games} game{'' if games == 1 else 's'})"
    )


def _matchup_lines(
    ctx: ResolvedContext,
    sched: SourceResult[ScheduleData],
    defense: SourceResult[DefenseData],
) -> list[str]:
    if ctx.position == "K":
        return [_KICKER_MATCHUP_LINE]
    if sched.status != "ok":
        return ["Matchup unavailable: no target-week opponent"]
    opponent = next(week.opponent for week in sched.data.weeks if week.week == ctx.week)
    if opponent is None:
        return []
    if defense.status == "error":
        return [f"Matchup unavailable: defense failed to load: {defense.error}"]
    if defense.status == "empty":
        return [
            f"Matchup unavailable: no points-allowed data for {ctx.position}s before Week {ctx.week}"
        ]
    if opponent not in {row.team for row in defense.data.rows}:
        return [f"Matchup unavailable: no games found for {opponent} defense"]
    return [_matchup_line(opponent, defense.data, ctx.scoring_format), _MATCHUP_CAVEAT]


def _past_week_line(
    week: ScheduleWeek,
    stats: SourceResult[RecentStatsData],
    games: dict[int, GameLine],
    scoring_format: str,
    is_kicker: bool,
) -> str:
    if week.opponent is None:
        return f"Week {week.week}: BYE"
    prefix = f"Week {week.week} {_venue(week)} {week.opponent}"
    if not week.played:
        return f"{prefix}: game not yet played, stats pending"
    if stats.status == "error":
        return f"{prefix}: stats unavailable"
    if week.week in games:
        return _game_line(games[week.week], scoring_format, is_kicker, _venue(week))
    return f"{prefix}: did not play"


def _render_player(inputs: PlayerInputs, mention: str) -> list[str]:
    ctx, stats, sched = inputs.ctx, inputs.recent_stats, inputs.schedule
    is_kicker = stats.status == "ok" and stats.data.position == "K"
    games = {game.week: game for game in stats.data.games} if stats.status == "ok" else {}

    lines = [f"## {ctx.player_name} ({ctx.team})"]
    if _normalize_name(mention) != _normalize_name(ctx.player_name):
        lines.append(f'Interpreted "{mention}" as {ctx.player_name} ({ctx.team} {ctx.position})')
    lines.extend(_roster_status_lines(ctx))
    lines.extend(_injury_lines(ctx, inputs.injuries, sched))

    if sched.status == "ok":
        weeks = {week.week: week for week in sched.data.weeks}
        lines.append(_target_week_line(weeks[ctx.week]))
        lines.extend(_matchup_lines(ctx, sched, inputs.defense))
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
    lines.extend(_matchup_lines(ctx, sched, inputs.defense))
    if is_kicker:
        lines.append(_KICKER_LINE)
    if stats.status == "error":
        lines.append(f"recent_stats failed to load: {stats.error}")
    elif stats.status == "empty":
        lines.append(f"No games played before Week {ctx.week}.")
    else:
        lines.extend(_game_line(game, ctx.scoring_format, is_kicker) for game in stats.data.games)
    return lines


def render_context(validated: ValidatedRequest, players: list[PlayerInputs]) -> str:
    lines = [
        f"Question: {validated.raw_prompt}",
        f"Week: {validated.week}",
        f"Scoring format: {validated.scoring_format}",
    ]
    lines.extend(
        f'Could not resolve "{rejected.mention}": {rejected.reason}'
        for rejected in validated.rejected
    )
    mentions = {player.player_id: player.mention for player in validated.players}
    for inputs in players:
        lines.append("")
        lines.extend(_render_player(inputs, mentions[inputs.ctx.player_id]))
    return "\n".join(lines)
