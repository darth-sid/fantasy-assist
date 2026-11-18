"""Small-sample statistics for pairwise A/B judgments; ties are excluded by the callers."""

from __future__ import annotations

import math


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a win rate (95% by default); (0, 1) when n is 0."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test p-value for wins vs losses under a 50/50 null."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n
    return min(1.0, 2 * tail)


def win_rate_line(a: int, b: int) -> str:
    """A's win rate over decisive judgments with a Wilson 95% CI and sign test p."""
    if a + b == 0:
        return "  no decisive judgments yet"
    low, high = wilson_interval(a, a + b)
    return (
        f"  A win rate excluding ties: {a / (a + b):.0%} of {a + b} "
        f"(95% CI {low:.0%} to {high:.0%}), sign test p = {sign_test(a, b):.3f}"
    )
