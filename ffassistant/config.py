SEASON = 2026  # pinned season; in production this comes from the calendar
DEFAULT_SCORING_FORMAT = "PPR"  # fallback when a request doesn't specify one
LLM_PROVIDER = "anthropic"
PARSER_MODEL = "claude-haiku-5-5"
ANSWER_MODEL = "claude-haiku-5-5"

FEEDS = {
    "rotowire": "https://www.rotowire.com/rss/news.php?sport=NFL",
    "espn": "https://www.espn.com/espn/rss/nfl/news",
}
NEWS_DIR = "data/news"  # relative to the repo root

NEWS_TOP_K = 5  # player's own news
NEWS_TEAM_TOP_K = 3
NEWS_OPPONENT_TOP_K = 3
NEWS_RANKER = "bm25"  # "recency" or "bm25"; team and opponent buckets only
NEWS_QUERY_TEAM = (
    "{position_words} role workload targets carries snaps teammate injury questionable out "
    "returns depth chart starter"
)
NEWS_QUERY_OPPONENT = (
    "{opponent} defense injury questionable out returns secondary cornerback safety linebacker pass rush "
    "starter"
)
NEWS_POSITION_WORDS = {
    "QB": "quarterback passing",
    "RB": "running back rushing backfield",
    "WR": "wide receiver receivers",
    "TE": "tight end",
    "K": "kicker",
}
NEWS_LOOKBACK_DAYS = 14
NEWS_MAX_SUMMARY_CHARS = 500
