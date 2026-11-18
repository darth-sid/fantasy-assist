"""Draws a seeded set of player samples for a week, weighted toward productive players."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from evals.models import EvalSample
from ffassistant.clients.nflreadpy_client import load_player_stats, load_schedules
from ffassistant.config import CONFIG_PATH, load_config
from ffassistant.resolution.roster import RosterPlayer, load_fantasy_roster

def teams_playing(schedules: pl.DataFrame, week: int) -> set[str]:
    """Teams with a REG game in week, i.e. everyone not on a bye."""
    games = schedules.filter((pl.col("game_type") == "REG") & (pl.col("week") == week))
    return set(games["home_team"]) | set(games["away_team"])


def player_weights(
    roster: dict[str, RosterPlayer],
    stats: pl.DataFrame,
    week: int,
    playing: set[str],
    min_ppg: float,
) -> dict[str, float]:
    """Squared PPR points per game before week, for active players on teams playing that week.
    Players under min_ppg are dropped."""
    active = [
        gsis_id
        for gsis_id, player in roster.items()
        if player.status == "ACT" and player.team in playing
    ]
    per_game = (
        stats.filter(
            (pl.col("season_type") == "REG")
            & (pl.col("week") < week)
            & pl.col("player_id").is_in(active)
        )
        .group_by("player_id")
        .agg(pl.col("fantasy_points_ppr").mean().alias("ppg"))
        .filter(pl.col("ppg") >= min_ppg)
    )
    return {row["player_id"]: row["ppg"] ** 2 for row in per_game.to_dicts()}


def sample_players(
    roster: dict[str, RosterPlayer],
    weights: dict[str, float],
    season: int,
    week: int,
    n: int,
    seed: int,
    as_of: datetime,
) -> list[EvalSample]:
    """n distinct players drawn by weight, without replacement."""
    if n > len(weights):
        raise ValueError(f"asked for {n} players but only {len(weights)} are eligible")
    rng = random.Random(seed)
    # Sorted so the same seed gives the same samples regardless of dict order.
    remaining = dict(sorted(weights.items()))
    samples = []
    for i in range(n):
        gsis_id = rng.choices(list(remaining), list(remaining.values()))[0]
        del remaining[gsis_id]
        player = roster[gsis_id]
        samples.append(
            EvalSample(
                id=f"w{week}-{i:03d}",
                season=season,
                week=week,
                as_of=as_of.isoformat(timespec="seconds"),
                gsis_id=gsis_id,
                full_name=player.full_name,
                position=player.position,
            )
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.generate")
    parser.add_argument("--week", type=int, required=True, help="target week every sample uses")
    parser.add_argument("-n", type=int, default=30, help="how many players")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--min-ppg", type=float, default=5.0, help="drop players under this PPR points per game"
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file to use")
    parser.add_argument("-o", "--output", type=Path, required=True, help="samples JSONL to write")
    args = parser.parse_args()

    cfg = load_config(args.config)
    roster = load_fantasy_roster(cfg.season)
    playing = teams_playing(load_schedules(cfg.season), args.week)
    weights = player_weights(
        roster, load_player_stats(cfg.season), args.week, playing, args.min_ppg
    )
    samples = sample_players(
        roster, weights, cfg.season, args.week, args.n, args.seed, datetime.now(timezone.utc)
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(s.model_dump_json() + "\n" for s in samples), encoding="utf-8")
    print(f"wrote {len(samples)} samples to {args.output}")


if __name__ == "__main__":
    main()
