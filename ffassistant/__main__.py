from dotenv import load_dotenv

from ffassistant.answer import answer
from ffassistant.config import SEASON
from ffassistant.contracts import ResolvedContext, SourceResult
from ffassistant.resolution.player_resolver import resolve_from_player
from ffassistant.resolution.request_parser import parse_request
from ffassistant.sources.recent_stats import RecentStatsData, recent_stats

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

print(f"Request: {parsed.raw_prompt}")
print()
print(answer(parsed, players).answer)
