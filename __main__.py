from config import SEASON
from contracts import FeatureVector
from resolution.player_resolver import resolve_from_player
from resolution.request_parser import parse_request
from sources.recent_stats import recent_stats
from features.recent_stats import extract as extract_recent_stats_features
from feature_vector import merge_features
from decision import rank_players

# --- Natural-language request (stands in for a real request surface) ---
REQUEST = "CeeDee Lamb or Justin Jefferson for Week 16? Or maybe Ja'Marr Chase?"
# -------------------------------------------------------------------------


def _feature_vector_for(
    player_name: str, week: int, scoring_format: str
) -> FeatureVector:
    ctx = resolve_from_player(player_name, SEASON, week, scoring_format)
    recent_stats_result = recent_stats(ctx)
    recent_stats_features = extract_recent_stats_features(recent_stats_result)
    return merge_features([recent_stats_features])


parsed = parse_request(REQUEST)
entries = [
    (name, _feature_vector_for(name, parsed.week, parsed.scoring_format))
    for name in parsed.player_names
]
vectors_by_name = dict(entries)

print(f"Request: {parsed.raw_prompt}")
for rank, (name, score) in enumerate(rank_players(entries), start=1):
    games_played = vectors_by_name[name].get("recent_stats.games_played", 0.0)
    print(f"{rank}. {name}: {score:.1f} pts ({games_played:.0f} games)")
