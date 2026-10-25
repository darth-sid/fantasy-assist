from __future__ import annotations

from ffassistant.clients.anthropic_client import StructuredResponse, parse_structured
from ffassistant.config import PARSER_MODEL, SEASON
from ffassistant.resolution.models import ExtractedRequest
from ffassistant.resolution.roster import load_fantasy_roster, render_roster

_INSTRUCTIONS = """Extract a fantasy football request from the user's message.

Season: {season}. Current week: {current_week}.

- players: every player the user mentions, in order.
  - mention: the player exactly as the user wrote it.
  - player_id: the gsis_id of the matching player from the roster below. Try
    hard to match: handle nicknames, typos, missing or different punctuation,
    and missing suffixes (Jr., II, III). Return null only when there is no
    reasonable match on the roster.
- week: the NFL week the user asks about. Resolve relative weeks using the
  current week ("this week" = {current_week}, "next week" = {next_week}). Return
  an explicitly stated week exactly as written, even if it is not a real NFL
  week (e.g. "week 25" -> 25); it is validated later. Leave null if no week is
  stated.
- scoring_format: normalize common phrasings to exactly "PPR", "Half-PPR", or
  "Standard" (e.g. "half ppr" or "0.5 PPR" -> "Half-PPR", "non-PPR" ->
  "Standard"). Pass anything else through as written. Leave null if no scoring
  format is stated.
"""


def _print_debug(response: StructuredResponse[ExtractedRequest]) -> None:
    extracted, usage = response.parsed, response.usage
    print("--- Extracted request ---")
    for player in extracted.players:
        print(f'"{player.mention}" -> {player.player_id or "null"}')
    print(f"week: {extracted.week if extracted.week is not None else 'null'}")
    print(f"scoring_format: {extracted.scoring_format or 'null'}")
    print(
        f"cache_creation_input_tokens={usage.cache_creation_input_tokens}, "
        f"cache_read_input_tokens={usage.cache_read_input_tokens}"
    )
    print("-------------------------")
    print()


def extract(prompt: str, current_week: int, debug: bool = False) -> ExtractedRequest:
    roster = load_fantasy_roster(SEASON)
    instructions = _INSTRUCTIONS.format(
        season=SEASON, current_week=current_week, next_week=current_week + 1
    )
    system = [
        {"type": "text", "text": instructions},
        {
            "type": "text",
            "text": f"Fantasy roster for {SEASON}:\n{render_roster(roster)}",
            "cache_control": {"type": "ephemeral"},
        },
    ]
    response = parse_structured(
        model=PARSER_MODEL,
        system=system,
        user_content=prompt,
        output_model=ExtractedRequest,
        max_tokens=1024,
    )
    if debug:
        _print_debug(response)
    return response.parsed
