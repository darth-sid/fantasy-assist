from __future__ import annotations

from pydantic import BaseModel

from ffassistant.answering.context import render_context
from ffassistant.answering.models import Answer, PlayerInputs
from ffassistant.answering.player_context import player_context
from ffassistant.answering.sources.defense import defense
from ffassistant.answering.sources.injuries import injuries
from ffassistant.answering.sources.recent_stats import recent_stats
from ffassistant.answering.sources.schedule import schedule
from ffassistant.clients.anthropic_client import parse_structured
from ffassistant.config import ANSWER_MODEL
from ffassistant.resolution.models import ValidatedRequest

_SYSTEM_PROMPT = """Answer the user's fantasy football question using only the provided context.

- answer: your answer in markdown. Choose a format that fits the question — a
  head-to-head comparison reads differently from start/sit calls on several
  players.
- If a player's data is missing or failed to load, say so plainly for that
  player. Don't fill the gap with outside knowledge or guesses.
- A player whose team is on BYE in the target week cannot score that week.
- A player marked Out, or on a reserve or PUP list, will not play. Doubtful
  means unlikely to play; Questionable means uncertain.
- The matchup rank is one input among several. Don't let it outweigh a player's
  own usage and production.
- Mention any player the context says could not be resolved, and any
  "Interpreted ... as ..." name interpretation your answer relies on.
- cited_doc_ids: leave empty.
"""


class GeneratedAnswer(BaseModel):
    answer: str
    cited_doc_ids: list[str]


def gather_inputs(validated: ValidatedRequest) -> list[PlayerInputs]:
    inputs = []
    for player in validated.players:
        ctx = player_context(
            player, validated.season, validated.week, validated.scoring_format
        )
        inputs.append(
            PlayerInputs(
                ctx=ctx,
                recent_stats=recent_stats(ctx),
                schedule=schedule(ctx),
                defense=defense(ctx),
                injuries=injuries(ctx),
            )
        )
    return inputs


def answer(validated: ValidatedRequest, debug: bool = False) -> Answer:
    context = render_context(validated, gather_inputs(validated))
    if debug:
        print("--- Answer context ---")
        print(context)
        print("----------------------")
        print()
    generated = parse_structured(
        model=ANSWER_MODEL,
        system=[{"type": "text", "text": _SYSTEM_PROMPT}],
        user_content=context,
        output_model=GeneratedAnswer,
        max_tokens=2048,
    ).parsed
    return Answer(answer=generated.answer, cited_doc_ids=generated.cited_doc_ids)
