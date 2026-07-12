from config import SEASON
from resolution.player_resolver import resolve_from_player
from sources.recent_stats import recent_stats
from features.recent_stats import extract as extract_recent_stats_features
from feature_vector import merge_features

# --- Hardcoded request (stands in for request parsing) ---
REQUEST_PLAYER_NAME = "Justin Jefferson"
REQUEST_WEEK = 12
REQUEST_SCORING_FORMAT = "PPR"
# -----------------------------------------------------------

ctx = resolve_from_player(REQUEST_PLAYER_NAME, SEASON, REQUEST_WEEK, REQUEST_SCORING_FORMAT)

recent_stats_result = recent_stats(ctx)
recent_stats_features = extract_recent_stats_features(recent_stats_result)

vector = merge_features([recent_stats_features])
print(vector)
