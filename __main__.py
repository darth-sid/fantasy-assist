from dotenv import load_dotenv

from answer import answer
from config import SEASON
from contracts import ResolvedContext, SourceResult
from resolution.player_resolver import resolve_from_player
from resolution.request_parser import parse_request
from sources.recent_stats import RecentStatsData, recent_stats
from features.recent_stats import extract as extract_recent_stats_features
from feature_vector import merge_features
from decision import rank_players

load_dotenv()

# --- Natural-language request (stands in for a real request surface) ---
REQUEST = "CeeDee Lamb or Justin Jefferson for Week 7? Or maybe Ja'Marr Chase?"
# -------------------------------------------------------------------------


def _player_inputs(
    player_name: str, week: int, scoring_format: str
) -> tuple[ResolvedContext, SourceResult[RecentStatsData]]:
    ctx = resolve_from_player(player_name, SEASON, week, scoring_format)
    return ctx, recent_stats(ctx)


parsed = parse_request(REQUEST)
players = [
    _player_inputs(name, parsed.week, parsed.scoring_format)
    for name in parsed.player_names
]
entries = [
    (name, merge_features([extract_recent_stats_features(result)]))
    for name, (_, result) in zip(parsed.player_names, players)
]
vectors_by_name = dict(entries)

print(f"Request: {parsed.raw_prompt}")
for rank, (name, score) in enumerate(rank_players(entries), start=1):
    games_played = vectors_by_name[name].get("recent_stats.games_played", 0.0)
    print(f"{rank}. {name}: {score:.1f} pts ({games_played:.0f} games)")

result = answer(parsed, players)
print()
print(result.answer)
