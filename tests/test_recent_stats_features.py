from contracts import SourceResult
from features.recent_stats import extract
from sources.recent_stats import GameLine, RecentStatsData

AS_OF = "Week 12"


def test_ok_status_produces_averaged_features():
    data = RecentStatsData(
        position="WR",
        games=[
            GameLine(week=1, opponent="DAL", stats={"receptions": 5, "receiving_yards": 60}),
            GameLine(week=2, opponent="PHI", stats={"receptions": 7, "receiving_yards": 88}),
        ],
    )
    result = SourceResult(source="recent_stats", status="ok", as_of=AS_OF, data=data)

    features = extract(result)

    assert features["recent_stats.games_played"] == 2
    assert features["recent_stats.avg_receptions"] == 6
    assert features["recent_stats.avg_receiving_yards"] == 74


def test_averages_only_over_games_reporting_that_stat():
    data = RecentStatsData(
        position="QB",
        games=[
            GameLine(week=1, opponent="DAL", stats={"passing_yards": 300}),
            GameLine(week=2, opponent="PHI", stats={"passing_yards": 200, "rushing_yards": 20}),
        ],
    )
    result = SourceResult(source="recent_stats", status="ok", as_of=AS_OF, data=data)

    features = extract(result)

    assert features["recent_stats.avg_passing_yards"] == 250
    assert features["recent_stats.avg_rushing_yards"] == 20


def test_empty_status_produces_no_features():
    result = SourceResult(source="recent_stats", status="empty", as_of=AS_OF)

    assert extract(result) == {}


def test_error_status_produces_no_features():
    result = SourceResult(source="recent_stats", status="error", as_of=AS_OF, error="boom")

    assert extract(result) == {}
