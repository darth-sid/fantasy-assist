from __future__ import annotations

from ffassistant.ingest.gazetteer import Gazetteer, name_key
from ffassistant.ingest.models import NewsItem, NewsTags


def _resolve(candidates: list[tuple[str, str]], named_teams: set[str]) -> list[tuple[str, str]]:
    # A shared name goes to the players whose team the item names; otherwise every match is kept.
    return [c for c in candidates if c[1] in named_teams] or candidates


def tag(item: NewsItem, gazetteer: Gazetteer) -> NewsTags:
    """Tags a news item with the players (gsis_ids) and teams it mentions."""
    title, summary = gazetteer.find(item.title), gazetteer.find(item.summary)
    named_teams = title.teams | summary.teams

    if item.source == "rotowire":
        # RotoWire titles lead with the full name; summaries use last names and name opponents,
        # so their team names only break ties between players sharing the title name.
        candidates = gazetteer.players.get(name_key(item.title.split(": ", 1)[0]), [])
        players = _resolve(candidates, named_teams)
        teams = {team for _, team in players}
    else:
        players = [p for c in title.players + summary.players for p in _resolve(c, named_teams)]
        teams = named_teams | {team for _, team in players}

    return NewsTags(
        doc_id=item.doc_id,
        player_ids=sorted({gsis_id for gsis_id, _ in players}),
        teams=sorted(teams),
    )
