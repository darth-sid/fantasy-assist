SEASON = 2026  # pinned season; in production this comes from the calendar
DEFAULT_SCORING_FORMAT = "PPR"  # fallback when a request doesn't specify one
LLM_PROVIDER = "anthropic"
PARSER_MODEL = "claude-haiku-4-5"
ANSWER_MODEL = "claude-haiku-4-5"

FEEDS = {
    "rotowire": "https://www.rotowire.com/rss/news.php?sport=NFL",
    "espn": "https://www.espn.com/espn/rss/nfl/news",
}
NEWS_DIR = "data/news"  # relative to the repo root

NEWS_TOP_K = 5
NEWS_LOOKBACK_DAYS = 14
NEWS_MAX_SUMMARY_CHARS = 500
