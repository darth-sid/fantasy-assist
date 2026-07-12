# CLAUDE.md — Fantasy Football Start/Sit RAG Assistant

See [README.md](README.md) for project purpose and structure. This file grows as
process/design decisions land (see Maintaining this file).

## Working agreement (read first)

**Roles — two modes. Check Current edge for the active one.**
- *Review mode (project default):* Sid implements; Claude specs, designs, reviews.
  Don't write implementation code unless Sid explicitly asks. Default output is a
  spec/contract/review.
- *Build mode:* Sid drives the design close to the code and gives tight instructions;
  Claude writes the actual code and acts as a sounding board — surfacing pros/cons to
  ground Sid's decisions — without making the design calls for him.

In both modes Claude flags issues in Sid's design and its own. Overreach in Build mode =
making a design decision Sid reserved, or gold-plating past the spec. Implement exactly
what's decided; when a decision is missing, ask rather than invent. One slice at a time.

## Code style

No huge docstrings. If a function is genuinely complicated enough to seem to need one,
ask Sid rather than writing it.

## Current edge

Structure: `sources/`, `features/`, `resolution/`, and `clients/` subfolders,
everything else flat. `clients/nflreadpy_client.py` holds all raw nflreadpy access;
`sources/` and `resolution/` call through it rather than importing nflreadpy directly.

Pipeline: `sources/*.py` implement `(ctx: ResolvedContext) -> SourceResult[T]`, where
`T` is a rich, source-specific data type the branch defines itself (e.g.
`sources/recent_stats.py`'s `RecentStatsData`) — branches are not forced into a
shared text-block output beyond the `SourceResult` envelope (`source`, `status`,
`as_of`, `data`, `error`). `features/*.py` mirrors `sources/` one module per branch
and implements `extract(SourceResult[T]) -> FeatureVector` (`dict[str, float]`, keys
prefixed with the source name) — this is where an LLM would live for a future
unstructured source; `recent_stats` needs none. `feature_vector.py`'s
`merge_features` combines each source's contribution into one `FeatureVector` per
player, raising on key collisions. The final decision layer (a deterministic model —
a decision tree — consuming the `FeatureVector`) isn't built yet; it needs a training
pipeline/labeled data first.

`resolution/player_resolver.py`'s `resolve_from_player(name, season, week, scoring_format)`
resolves a player name via `load_rosters(season)` — picking the roster row with the
latest `week <= target week` — and returns a `ResolvedContext` directly. Raises on no
match or on a name matching multiple distinct players (`gsis_id`s) — no silent wrong
answers yet. Wired into `__main__.py`; only `REQUEST_PLAYER_NAME`, `REQUEST_WEEK`, and
`REQUEST_SCORING_FORMAT` are still hardcoded there (stand-in for request parsing).

Working mode: **Build** — Sid designs, Claude implements to spec.

## Data Sources

Player/team/NFL data comes from **nflreadpy** (Python port of the R `nflreadr`/nflverse
tooling; loaders return Polars DataFrames).

Full function signatures, config/caching behavior, and accumulated gotchas: see
[API_CONTEXT.md](API_CONTEXT.md). Keep that file current as we learn more about the
library instead of duplicating API detail here.

## Maintaining this file

After Sid **confirms** a design decision, before ending the turn:
1. Append a dated one-line entry to the Decision Log.
2. Update or create the affected section so the body reflects current state.
3. If it supersedes a prior decision, mark the old log entry `[superseded]` — don't delete.

Only confirmed decisions, not options under discussion. Don't churn on micro-choices.
The **body is authoritative** (current state); the log is provenance.

## Decision Log

- 2026-07-04 — Build mode for now (Sid designs close-to-code, Claude implements to spec);
  project default is Review mode.
- 2026-07-04 — Data source: nflreadpy. API surface tracked in API_CONTEXT.md, not here.
- 2026-07-04 — Project structure: `sources/` + `resolution/` subfolders, everything else
  flat. Documented in README.md.
- 2026-07-04 — Added `clients/` subfolder for raw nflreadpy access (both new roster
  access and the existing player-stats call moved in); `sources/`/`resolution/` no
  longer call nflreadpy directly.
- 2026-07-04 — Player-name resolution rule: on a multi-team season for one player, use
  the roster row with the latest week <= target week; on a name matching multiple
  distinct players, raise rather than guess.
- 2026-07-04 — Test framework: pytest, in `tests/`. Client calls mocked at the
  `clients/` boundary; no test hits the network.
- 2026-07-08 — Code style: no huge docstrings; ask Sid if a function seems to need one.
- 2026-07-10 — `resolve_from_player` (renamed from `resolve_player`) returns a
  `ResolvedContext` directly instead of an intermediate `PlayerMatch`; wired into
  `__main__.py`, replacing the hardcoded player_id/team stand-in.
- 2026-07-11 — Sources no longer compile down to a shared `ContextBlock` LLM-prompt
  text format; each branch exposes its own rich `SourceResult[T]` data type instead.
  `ContextBlock` and `assembler.py` retired.
- 2026-07-11 — Added `features/` subfolder: one module per source, turning that
  source's `SourceResult[T]` into named numeric `FeatureVector` contributions;
  `feature_vector.py`'s `merge_features` combines them into one vector per player,
  raising on key collisions rather than silently overwriting.
- 2026-07-11 — Final decision layer will be a deterministic model (e.g. a decision
  tree) over the `FeatureVector`, not an LLM. An LLM, if used at all, stays confined
  to a source's `features/` layer (for parsing unstructured input) and never reaches
  the final decision. The decision-tree layer itself is out of scope until a training
  pipeline/labeled data exist.
