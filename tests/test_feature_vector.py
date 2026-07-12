import pytest

from feature_vector import merge_features


def test_merges_disjoint_feature_dicts():
    merged = merge_features([
        {"recent_stats.avg_receptions": 6.0},
        {"news.injury_severity": 0.5},
    ])

    assert merged == {"recent_stats.avg_receptions": 6.0, "news.injury_severity": 0.5}


def test_raises_on_duplicate_key_across_sources():
    with pytest.raises(ValueError):
        merge_features([
            {"recent_stats.avg_receptions": 6.0},
            {"recent_stats.avg_receptions": 7.0},
        ])


def test_empty_dicts_merge_to_empty():
    assert merge_features([{}, {}]) == {}
