from __future__ import annotations

from typing import get_args

from ffassistant.config import DEFAULT_SCORING_FORMAT, SEASON
from ffassistant.resolution.models import (
    ExtractedRequest,
    RejectedMention,
    RequestValidationError,
    ScoringFormat,
    ValidatedRequest,
    ValidPlayer,
)
from ffassistant.resolution.roster import load_fantasy_roster

_SCORING_FORMATS = get_args(ScoringFormat)


def validate(
    extracted: ExtractedRequest, raw_prompt: str, current_week: int
) -> ValidatedRequest:
    errors = []
    if not extracted.players:
        errors.append("no players found in the request")

    week = extracted.week if extracted.week is not None else current_week
    if not 1 <= week <= 18:
        errors.append(f"week {week} is outside the regular season (1 to 18)")

    scoring_format = (
        extracted.scoring_format
        if extracted.scoring_format is not None
        else DEFAULT_SCORING_FORMAT
    )
    if scoring_format not in _SCORING_FORMATS:
        errors.append(
            f"scoring format {scoring_format!r} is not one of {', '.join(_SCORING_FORMATS)}"
        )

    roster = load_fantasy_roster(SEASON)
    players: list[ValidPlayer] = []
    rejected: list[RejectedMention] = []
    for player in extracted.players:
        if player.player_id is None:
            rejected.append(RejectedMention(player.mention, "no matching player found"))
        elif player.player_id not in roster:
            rejected.append(RejectedMention(player.mention, "unknown player id"))
        elif player.player_id not in {p.player_id for p in players}:
            info = roster[player.player_id]
            players.append(
                ValidPlayer(
                    mention=player.mention,
                    player_id=player.player_id,
                    full_name=info.full_name,
                    position=info.position,
                )
            )

    if extracted.players and not players:
        errors.extend(f'could not resolve "{r.mention}": {r.reason}' for r in rejected)

    if errors:
        raise RequestValidationError(errors)

    return ValidatedRequest(
        raw_prompt=raw_prompt,
        season=SEASON,
        week=week,
        scoring_format=scoring_format,
        players=players,
        rejected=rejected,
    )
