from __future__ import annotations

from ffassistant.ingest.gazetteer import Gazetteer, name_key
from ffassistant.ingest.models import NewsItem, NewsTags


def tag(item: NewsItem, gazetteer: Gazetteer) -> NewsTags:
    """Tags a news item with the players (gsis_ids) and teams it mentions."""
    player_ids: set[str] = set()
    teams: set[str] = set()

    if item.source == "rotowire":
        # RotoWire titles lead with the full name; summaries use last names and name past opponents.
        matches = gazetteer.players.get(name_key(item.title.split(": ", 1)[0]), [])
        player_ids.update(gsis_id for gsis_id, _ in matches)
        teams.update(team for _, team in matches)
    else:
        for text in (item.title, item.summary):
            for key in gazetteer.find(text):
                for gsis_id, team in gazetteer.players.get(key, []):
                    player_ids.add(gsis_id)
                    teams.add(team)
                if key in gazetteer.teams:
                    teams.add(gazetteer.teams[key])

    return NewsTags(doc_id=item.doc_id, player_ids=sorted(player_ids), teams=sorted(teams))
