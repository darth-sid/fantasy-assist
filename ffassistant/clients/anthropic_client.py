from __future__ import annotations

import anthropic
from pydantic import BaseModel

from ffassistant.config import ANSWER_MODEL, PARSER_MODEL

_SYSTEM_PROMPT = """Extract a fantasy football request from the user's message.

- player_names: every player mentioned, as written by the user.
- week: the NFL week ONLY if the user states an explicit numeric week (e.g.
  "week 8"). Leave null for relative phrases like "this week" or "next week" —
  those are resolved separately, not by you.
- scoring_format: "PPR", "Standard", or "Half-PPR" only if the user states it.
  Leave null otherwise.
"""

_ANSWER_SYSTEM_PROMPT = """Answer the user's fantasy football question using only the provided context.

- answer: your answer in markdown. Choose a format that fits the question — a
  head-to-head comparison reads differently from start/sit calls on several
  players.
- If a player's data is missing or failed to load, say so plainly for that
  player. Don't fill the gap with outside knowledge or guesses.
- cited_doc_ids: leave empty.
"""


class ExtractedRequest(BaseModel):
    player_names: list[str]
    week: int | None
    scoring_format: str | None


class GeneratedAnswer(BaseModel):
    answer: str
    cited_doc_ids: list[str]


def extract_request(prompt: str) -> ExtractedRequest:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=PARSER_MODEL,
        max_tokens=1024,
        temperature=0,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=ExtractedRequest,
    )
    return response.parsed_output


def generate_answer(context: str) -> GeneratedAnswer:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=ANSWER_MODEL,
        max_tokens=2048,
        temperature=0,
        system=_ANSWER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
        output_format=GeneratedAnswer,
    )
    return response.parsed_output
