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

- `load_player_stats(seasons, summary_level="week")` — `sources/recent_stats.py`.
  Filtered on `player_id`, `season_type == "REG"`, sorted by `week`. Columns relied on:
  `player_id`, `season_type`, `week`, `position`, `opponent_team`, plus stat columns
  (`completions`, `attempts`, `passing_yards`, `passing_tds`, `passing_interceptions`,
  `carries`, `rushing_yards`, `rushing_tds`, `receptions`, `targets`, `receiving_yards`,
  `receiving_tds`, `fg_made`, `fg_att`, `pat_made`).

## Full loader surface (v0.1.5)

All `seasons` params: `None` = current season, `True` = all available history, `int |
list[int]` = specific season(s), unless noted otherwise.

| Function | Signature | Notes |
|---|---|---|
| `load_player_stats` | `(seasons=None, summary_level: "week"\|"reg"\|"post"\|"reg+post"="week")` | Main per-player stat source. |
| `load_players` | `()` | No season arg — full player table. Cross-platform ID mappings (GSIS, PFR, PFF, OTC, ESB, ESPN). |
| `load_rosters` | `(seasons=None)` | `True` = all data since 1920. |
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
- `config.SEASON` is currently hardcoded to `2023` rather than derived from
  `get_current_season()` — see the stand-in comment in `config.py`.
- (Add new gotchas here as they're hit.)
