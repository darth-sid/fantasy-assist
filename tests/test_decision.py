from decision import predict_points, rank_players


def test_rank_players_orders_by_avg_fantasy_points_ppr_descending():
    entries = [
        ("Low Scorer", {"recent_stats.avg_fantasy_points_ppr": 5.0}),
        ("High Scorer", {"recent_stats.avg_fantasy_points_ppr": 20.0}),
        ("Mid Scorer", {"recent_stats.avg_fantasy_points_ppr": 12.0}),
    ]

    ranked = rank_players(entries)

    assert [name for name, _ in ranked] == ["High Scorer", "Mid Scorer", "Low Scorer"]
    assert ranked[0] == ("High Scorer", 20.0)


def test_predict_points_defaults_to_zero_when_key_missing():
    assert predict_points({}) == 0.0
