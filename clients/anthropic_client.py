from __future__ import annotations

import anthropic
from pydantic import BaseModel

_SYSTEM_PROMPT = """Extract a fantasy football request from the user's message.

- player_names: every player mentioned, as written by the user.
- week: the NFL week ONLY if the user states an explicit numeric week (e.g.
  "week 8"). Leave null for relative phrases like "this week" or "next week" —
  those are resolved separately, not by you.
- scoring_format: "PPR", "Standard", or "Half-PPR" only if the user states it.
  Leave null otherwise.
"""


class ExtractedRequest(BaseModel):
    player_names: list[str]
    week: int | None
    scoring_format: str | None


def extract_request(prompt: str) -> ExtractedRequest:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=1024,
        temperature=0,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=ExtractedRequest,
    )
    return response.parsed_output
