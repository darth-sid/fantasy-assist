import pytest

from evals.stats import sign_test, wilson_interval


def test_wilson_interval_matches_known_values():
    low, high = wilson_interval(18, 25)

    assert (round(low, 3), round(high, 3)) == (0.524, 0.857)


def test_wilson_interval_stays_inside_zero_and_one():
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_sign_test_two_sided():
    assert sign_test(18, 7) == pytest.approx(0.04329, abs=1e-5)
    assert sign_test(7, 18) == sign_test(18, 7)
    assert sign_test(5, 5) == 1.0
    assert sign_test(0, 0) == 1.0
