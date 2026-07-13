from contracts import FeatureVector


def predict_points(features: FeatureVector) -> float:
    # Placeholder for a trained model — just surfaces trailing avg PPR points
    # directly, to prove the pipeline shape end to end.
    return features.get("recent_stats.avg_fantasy_points_ppr", 0.0)


def rank_players(entries: list[tuple[str, FeatureVector]]) -> list[tuple[str, float]]:
    scored = [(name, predict_points(features)) for name, features in entries]
    return sorted(scored, key=lambda entry: entry[1], reverse=True)
