from __future__ import annotations

from contracts import FeatureVector, SourceResult
from sources.recent_stats import RecentStatsData

_PREFIX = "recent_stats"


def extract(result: SourceResult[RecentStatsData]) -> FeatureVector:
    if result.status != "ok" or result.data is None:
        return {}

    games = result.data.games
    if not games:
        return {}

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for game in games:
        for stat, value in game.stats.items():
            sums[stat] = sums.get(stat, 0.0) + value
            counts[stat] = counts.get(stat, 0) + 1

    features: FeatureVector = {f"{_PREFIX}.games_played": float(len(games))}
    for stat, total in sums.items():
        features[f"{_PREFIX}.avg_{stat}"] = total / counts[stat]

    return features
