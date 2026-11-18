from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from ffassistant.answering.context import render_context
from ffassistant.answering.models import Answer, Citation, PlayerInputs
from ffassistant.answering.player_context import player_context
from ffassistant.answering.sources.defense import defense
from ffassistant.answering.sources.injuries import injuries
from ffassistant.answering.sources.news import NewsEntry, news, news_query
from ffassistant.answering.sources.recent_stats import recent_stats
from ffassistant.answering.sources.schedule import news_cutoff, schedule, target_week
from ffassistant.clients.llm_client import QueryRequest, SystemBlock, get_llm_client
from ffassistant.config import Config, NewsConfig
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
- Team and opponent news are context (teammate availability, opposing
  defenders). Don't let them outweigh the player's own news and production.
  Cite them the same way.
"""


class GeneratedAnswer(BaseModel):
    answer: str
    cited_doc_ids: list[str]


def gather_inputs(
    validated: ValidatedRequest, cfg: Config, now: datetime | None = None
) -> list[PlayerInputs]:
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
                news=(
                    news(ctx, target_week(sched, ctx.week).opponent, cutoff, cfg)
                    if cutoff is not None
                    else None
                ),
            )
        )
    return inputs


def _citations(cited_doc_ids: list[str], players: list[PlayerInputs]) -> list[Citation]:
    rendered = {
        item.doc_id: item
        for inputs in players
        if inputs.news is not None and inputs.news.status == "ok"
        for bucket in (inputs.news.data.player, inputs.news.data.team, inputs.news.data.opponent)
        for item in bucket
    }
    return [
        Citation.from_news_entry(rendered[doc_id])
        for doc_id in cited_doc_ids
        if doc_id in rendered
    ]


def _ranking_lines(label: str, ranker: str, query: str, entries: list[NewsEntry]) -> list[str]:
    lines = [f"{label} ({ranker}): {query}"]
    for entry in sorted(entries, key=lambda e: e.score, reverse=True):
        lines.append(f"  {entry.score:.2f}  {entry.published_at[:10]}  {entry.title}")
    if not entries:
        lines.append("  (none selected)")
    return lines


def _print_news_ranking(players: list[PlayerInputs], news_cfg: NewsConfig) -> None:
    print("--- News ranking ---")
    for inputs in players:
        ctx, result = inputs.ctx, inputs.news
        print(f"## {ctx.player_name} ({ctx.team})")
        if result is None or result.status != "ok":
            print(f"news: {'not fetched' if result is None else result.status}")
            continue
        opponent = target_week(inputs.schedule, ctx.week).opponent
        ranker = news_cfg.ranker
        team_query = news_query(ctx, opponent, "team", news_cfg)
        opponent_query = news_query(ctx, opponent, "opponent", news_cfg)
        lines = _ranking_lines(f"{ctx.team} team news", ranker, team_query, result.data.team)
        lines += _ranking_lines(
            f"Opponent ({opponent}) news", ranker, opponent_query, result.data.opponent
        )
        print("\n".join(lines))
    print("--------------------")
    print()


def answer(
    validated: ValidatedRequest, cfg: Config, debug: bool = False, now: datetime | None = None
) -> Answer:
    players = gather_inputs(validated, cfg, now)
    context = render_context(validated, players, cfg)
    if debug:
        _print_news_ranking(players, cfg.news)
        print("--- Answer context ---")
        print(context)
        print("----------------------")
        print()
    client = get_llm_client(cfg.llm)
    generated = client.query(
        QueryRequest(
            model=cfg.llm.answer_model,
            system=[SystemBlock(text=_SYSTEM_PROMPT)],
            user_content=context,
            output_model=GeneratedAnswer,
            max_tokens=2048,
        )
    ).parsed
    return Answer(
        answer=generated.answer, citations=_citations(generated.cited_doc_ids, players)
    )
