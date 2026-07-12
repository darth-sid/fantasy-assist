from contracts import FeatureVector


def merge_features(feature_dicts: list[FeatureVector]) -> FeatureVector:
    merged: FeatureVector = {}
    for features in feature_dicts:
        for key, value in features.items():
            if key in merged:
                raise ValueError(f"Duplicate feature key {key!r} across sources.")
            merged[key] = value
    return merged
