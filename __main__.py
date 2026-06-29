from config import SEASON
from contracts import ResolvedContext
from sources.recent_stats import recent_stats
from assembler import assemble

# --- Hardcoded request (stands in for entity resolution) ---
REQUEST_PLAYER_ID = "00-0036322"  # Justin Jefferson
REQUEST_PLAYER_NAME = "Justin Jefferson"
REQUEST_TEAM = "MIN"
REQUEST_WEEK = 12
REQUEST_SCORING_FORMAT = "PPR"
# -----------------------------------------------------------

ctx = ResolvedContext(
    player_id=REQUEST_PLAYER_ID,
    player_name=REQUEST_PLAYER_NAME,
    team=REQUEST_TEAM,
    season=SEASON,
    week=REQUEST_WEEK,
    scoring_format=REQUEST_SCORING_FORMAT,
)

block = recent_stats(ctx)
prompt = assemble([block])
print(prompt)
