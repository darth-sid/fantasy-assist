from __future__ import annotations

from clients.anthropic_client import extract_request
from config import CURRENT_WEEK, DEFAULT_SCORING_FORMAT
from contracts import ParsedRequest


class NoPlayersFoundError(Exception):
    """The prompt didn't mention any players."""


def parse_request(prompt: str) -> ParsedRequest:
    extracted = extract_request(prompt)

    if not extracted.player_names:
        raise NoPlayersFoundError(f"No players found in prompt: {prompt!r}")

    return ParsedRequest(
        raw_prompt=prompt,
        player_names=extracted.player_names,
        week=extracted.week if extracted.week is not None else CURRENT_WEEK,
        scoring_format=(
            extracted.scoring_format
            if extracted.scoring_format is not None
            else DEFAULT_SCORING_FORMAT
        ),
    )
