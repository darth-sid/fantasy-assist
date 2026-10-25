# API_CONTEXT.md — nflreadpy reference

Living reference for the `nflreadpy` package. Update this as we learn more about the
API (new functions used, column quirks discovered, gotchas hit). CLAUDE.md points here
instead of duplicating this content.

Installed: `nflreadpy==0.1.5` (see `.venv/lib/python3.14/site-packages/nflreadpy`).
Python port of the R `nflreadr` package (nflverse). All loaders return **Polars**
DataFrames, not pandas.

- GitHub: https://github.com/nflverse/nflreadpy
- Per-function data dictionaries: https://nflreadr.nflverse.com/articles/ (R docs, same schemas)

## Config / caching

`nflreadpy.config.get_config()` defaults (observed):

```
cache_mode=CacheMode.MEMORY   # options: MEMORY, FILESYSTEM, OFF
cache_dir=~/Library/Caches/nflreadpy
cache_duration=86400          # seconds
verbose=False
timeout=30
```

Default cache is in-memory only (per-process), not persisted to disk. Use
`nflreadpy.config.update_config(cache_mode=...)` to change. `nflreadpy.clear_cache()`
clears it.

## Functions currently used in this repo

All calls now go through `clients/nflreadpy_client.py` — `answering/` and `resolution/`
never import `nflreadpy` directly.

- `load_player_stats(seasons, summary_level="week")` — used by `answering/sources/recent_stats.py`
  via `clients.nflreadpy_client.load_player_stats`. Filtered on `player_id`,
  `season_type == "REG"`, sorted by `week`. Columns relied on: `player_id`,
  `season_type`, `week`, `position`, `opponent_team`, plus stat columns
  (`completions`, `attempts`, `passing_yards`, `passing_tds`, `passing_interceptions`,
  `carries`, `rushing_yards`, `rushing_tds`, `receptions`, `targets`, `receiving_yards`,
  `receiving_tds`, `fg_made`, `fg_att`, `pat_made`).
  Also used by `answering/sources/defense.py`: points allowed is derived by filtering on
  `season_type`, `week`, and `position`, then grouping by `opponent_team` (summed
  per `(opponent_team, week)`, then averaged per defense). So `load_player_stats`
  is now called by two sources per player; nflreadpy's in-memory cache absorbs
  the repeat.
- `load_rosters(seasons)` — used via `clients.nflreadpy_client.load_rosters` by
  `resolution/roster.py` (the fantasy roster the extraction LLM resolves against,
  and the `gsis_id` lookup validation checks) and by `answering/player_context.py`
  (team as of the target week). Columns relied on: `full_name`, `gsis_id`, `team`,
  `week`, `position`, `status`. Loaded up to three times per run (extract,
  validate, player context); the in-memory cache absorbs the repeats. See gotchas
  below — this is not a simple one-row-per-player table.
- `load_schedules(seasons)` — used by `answering/sources/schedule.py` via
  `clients.nflreadpy_client.load_schedules` (always passed a single season, so the
  all-seasons default never applies). Filtered on `game_type == "REG"` and the
  player's team as `home_team` or `away_team`. Columns relied on: `game_type`,
  `week`, `home_team`, `away_team`, `result`.

## Full loader surface (v0.1.5)

All `seasons` params: `None` = current season, `True` = all available history, `int |
list[int]` = specific season(s), unless noted otherwise.

| Function | Signature | Notes |
|---|---|---|
| `load_player_stats` | `(seasons=None, summary_level: "week"\|"reg"\|"post"\|"reg+post"="week")` | Main per-player stat source. |
| `load_players` | `()` | No season arg — full player table. Cross-platform ID mappings (GSIS, PFR, PFF, OTC, ESB, ESPN). |
| `load_rosters` | `(seasons=None)` | `True` = all data since 1920. Not one row per player — see gotchas. |
| `load_rosters_weekly` | `(seasons=None)` | Data from 2002+. Week-by-week roster moves, injury designations. |
| `load_schedules` | `(seasons=True)` | Note default is `True` here (all seasons), unlike most other loaders. |
| `load_teams` | `()` | Team metadata: abbreviations, names, colors, logos. |
| `load_snap_counts` | `(seasons=None)` | PFR-sourced, 2012+. |
| `load_injuries` | `(seasons=None)` | 2009+. |
| `load_depth_charts` | `(seasons=None)` | 2001+. |
| `load_ff_rankings` | `(type: "draft"\|"week"\|"all"="draft")` | No `seasons` param. |
| `load_ff_opportunity` | `(seasons=None, stat_type: "weekly"\|"pbp_pass"\|"pbp_rush"="weekly", model_version: "latest"\|"v1.0.0"="latest")` | Target share / opportunity data from ffverse/ffopportunity. |
| `load_ff_playerids` | `()` | DynastyProcess.com ID mappings. Source is an `.rds`; package falls back to CSV — worth double-checking output if used. |
| `load_pbp` | `(seasons=None)` | `True` = all since 1999. Play-by-play, heavy. |
| `load_combine` | — | Not yet inspected. |
| `load_contracts` | — | Not yet inspected. |
| `load_draft_picks` | — | Not yet inspected. |
| `load_ftn_charting` | — | Not yet inspected. |
| `load_nextgen_stats` | — | Not yet inspected. |
| `load_officials` | — | Not yet inspected. |
| `load_participation` | — | Not yet inspected. |
| `load_pfr_advstats` | — | Not yet inspected. |
| `load_stats` | — | Not yet inspected; distinct from `load_player_stats`/`load_team_stats`. |
| `load_team_stats` | — | Not yet inspected. |
| `load_trades` | — | Not yet inspected. |
| `get_current_season` | `(roster: bool=False)` | `roster=True` uses "after March 15" logic instead of season-start logic. |
| `get_current_week` | `(use_date: bool=False, **kwargs)` | `use_date=False` (default) calls `load_schedules` under the hood — network cost. |

## Gotchas / observations

- `get_current_week(use_date=False)` triggers a schedule load — prefer `use_date=True`
  if we just need a rough week number without a network round-trip.
- `config.SEASON` is currently hardcoded to `2026` rather than derived from
  `get_current_season()` — see the stand-in comment in `config.py`.
- `load_rosters(season)` is **not** one row per player. It's one row per observed
  roster-status change, tagged with the `week` it was observed. Most players get one
  row for the whole season; players who were cut/traded/re-signed get one row per
  status change, each potentially with a different `team`. Observed on 2023 data:
  3090 rows for ~2000-ish distinct players, weeks ranging 1–22 (18 regular + playoff
  round codes in `game_type`: `REG`/`WC`/`DIV`/`CON`/`SB`).
- `full_name` in `load_rosters` is **not unique** — real name collisions exist (16
  cases in the 2023 data alone, e.g. two different players both named "Lamar
  Jackson", distinguishable only by `gsis_id`). Any name-keyed lookup must check for
  multiple distinct `gsis_id`s per name and handle the collision explicitly rather
  than picking one silently. Resolution no longer keys on names (the LLM picks a
  `gsis_id` from the roster), and within 2026 fantasy positions no two players
  share a `full_name` (verified 2026-10-24), but a future season could.
- `gsis_id` is the right column to use as `player_id` — format matches what
  `answering/sources/recent_stats.py` already expects (e.g. `"00-0036322"`).
- Roster `status` codes seen: `ACT`, `DEV`, `CUT`, `RES`, `INA`, `TRC`, `TRD`, `EXE`,
  `PUP`, `TRT`, `RET` (and others). The fantasy roster context includes every
  status (reserve/IR players must be resolvable) and shows it to the LLM.
  `answering/player_context.py` ignores `status` and just picks the latest row
  at/before the target week for the team.
- The 2026 fantasy roster (QB/RB/WR/TE/K, one row per `gsis_id`) is 997 players.
  One row has a null `gsis_id` (Al-Jay Henderson, NYJ RB, DEV) and is dropped, so
  996 are rendered: ~43.6k characters, **21,132 tokens** as measured with
  `count_tokens` on `claude-haiku-4-5` (2026-10-24). It sits in its own cached
  system block in `resolution/extract.py`.
- The latest week's `load_player_stats` rows can be **incomplete** until Monday
  night games are processed. Observed 2026-10-19: Week 6 had ~911 rows vs ~1,100
  for earlier weeks. Treat the most recent week as possibly partial.
- `load_player_stats` has `fantasy_points` (standard) and `fantasy_points_ppr`, but
  no half-PPR column. `fantasy_points_ppr - fantasy_points == receptions` exactly
  (verified on every 2026 row), so half-PPR is exactly their midpoint.
- `load_rosters` `position` is coarse: `QB`/`RB`/`WR`/`TE`/`OL`/`K`/`P`/`LS` and
  defense `DB`/`LB`/`DL` (finer detail is in `depth_chart_position`). Name
  collisions often cross offense/defense — 2026 has two "Justin Jefferson"s
  (`00-0036322` MIN WR, `00-0041075` CLE LB rookie); `resolution/roster.py`
  filters to QB/RB/WR/TE/K.
- `load_schedules` `result` (home score minus away score) is **null for unplayed
  games**, which is how `answering/sources/schedule.py` sets `played`. A week before the
  target week can still be null if the data hasn't caught up.
- `load_player_stats` `fantasy_points` / `fantasy_points_ppr` **do not score
  kicking**. All 184 kicker rows in 2026 (as of 2026-10-19) have
  `fantasy_points = 0.0`. `answering/context.py` shows kickers' raw stats with no points.
- `load_teams` includes historical codes like `OAK`, `SD`, and `STL`, so it should
  not be used to derive byes (a team "missing" from a week would include defunct
  franchises). Byes come from a team's own schedule having no game that week.
- `answering/sources/schedule.py` looks up the schedule by `ctx.team`, the player's team as of
  the target week. A player traded mid-season gets past weeks matched against the
  wrong team's schedule (e.g. "did not play" for weeks they played elsewhere).
  Known, not yet solved.
- Points allowed by position is a small sample: 5 to 6 games per defense as of
  Week 7 of 2026 (byes account for the 5s).
- (Add new gotchas here as they're hit.)
