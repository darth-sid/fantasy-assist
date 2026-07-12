from config import SEASON
from contracts import FeatureVector
from resolution.player_resolver import resolve_from_player
from sources.recent_stats import recent_stats
from features.recent_stats import extract as extract_recent_stats_features
from feature_vector import merge_features

# --- Hardcoded request (stands in for request parsing) ---
# Comma-delimited player names, trailing token is the week.
REQUEST = "Justin Jefferson, CeeDee Lamb, Ja'Marr Chase, 12"
REQUEST_SCORING_FORMAT = "PPR"
# -----------------------------------------------------------


def _parse_request(request: str) -> tuple[list[str], int]:
    *names, week = (part.strip() for part in request.split(","))
    return names, int(week)


def _feature_vector_for(player_name: str, week: int) -> FeatureVector:
    ctx = resolve_from_player(player_name, SEASON, week, REQUEST_SCORING_FORMAT)
    recent_stats_result = recent_stats(ctx)
    recent_stats_features = extract_recent_stats_features(recent_stats_result)
    return merge_features([recent_stats_features])


player_names, week = _parse_request(REQUEST)

for player_name in player_names:
    vector = _feature_vector_for(player_name, week)
    print(player_name, vector)
