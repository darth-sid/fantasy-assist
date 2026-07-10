from config import SEASON
from resolution.player_resolver import resolve_from_player
from sources.recent_stats import recent_stats
from assembler import assemble

# --- Hardcoded request (stands in for request parsing) ---
REQUEST_PLAYER_NAME = "Justin Jefferson"
REQUEST_WEEK = 12
REQUEST_SCORING_FORMAT = "PPR"
# -----------------------------------------------------------

ctx = resolve_from_player(REQUEST_PLAYER_NAME, SEASON, REQUEST_WEEK, REQUEST_SCORING_FORMAT)

block = recent_stats(ctx)
prompt = assemble([block])
print(prompt)
