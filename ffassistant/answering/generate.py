from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from ffassistant.answering.context import render_context
from ffassistant.answering.models import Answer, Citation, PlayerInputs, SourceResult
from ffassistant.answering.player_context import player_context
from ffassistant.answering.sources.defense import defense
from ffassistant.answering.sources.injuries import injuries
from ffassistant.answering.sources.news import news
from ffassistant.answering.sources.recent_stats import recent_stats
from ffassistant.answering.sources.schedule import ScheduleData, schedule
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
- Use the news items as the most current information on availability and role,
  and cite each news item you rely on by putting its id in cited_doc_ids.
- Only cite ids that appear in the context.
- If news conflicts with the injury report, say so and favor whichever is more
  recent.
"""


class GeneratedAnswer(BaseModel):
    answer: str
    cited_doc_ids: list[str]


def news_cutoff(sched: SourceResult[ScheduleData], week: int, now: datetime) -> datetime | None:
    if sched.status != "ok":
        return None
    target = next(w for w in sched.data.weeks if w.week == week)
    if target.kickoff is None:
        return None
    return min(now, datetime.fromisoformat(target.kickoff))


def gather_inputs(validated: ValidatedRequest, now: datetime | None = None) -> list[PlayerInputs]:
    now = now or datetime.now(timezone.utc)
    inputs = []
    for player in validated.players:
        ctx = player_context(
            player, validated.season, validated.week, validated.scoring_format
        )
        sched = schedule(ctx)
        cutoff = news_cutoff(sched, ctx.week, now)
        inputs.append(
            PlayerInputs(
                ctx=ctx,
                recent_stats=recent_stats(ctx),
                schedule=sched,
                defense=defense(ctx),
                injuries=injuries(ctx),
                news=news(ctx, cutoff) if cutoff is not None else None,
            )
        )
    return inputs


def _citations(cited_doc_ids: list[str], players: list[PlayerInputs]) -> list[Citation]:
    rendered = {
        item.doc_id: item
        for inputs in players
        if inputs.news is not None and inputs.news.status == "ok"
        for item in inputs.news.data.items
    }
    return [
        Citation.from_news_entry(rendered[doc_id])
        for doc_id in cited_doc_ids
        if doc_id in rendered
    ]


def answer(
    validated: ValidatedRequest, debug: bool = False, now: datetime | None = None
) -> Answer:
    players = gather_inputs(validated, now)
    context = render_context(validated, players)
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
    return Answer(
        answer=generated.answer, citations=_citations(generated.cited_doc_ids, players)
    )
