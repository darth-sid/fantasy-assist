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
everything else flat. `clients/nflreadpy_client.py` holds all raw nflreadpy access
and `clients/anthropic_client.py` holds all raw Anthropic SDK access; `sources/`
and `resolution/` call through `clients/` rather than importing either library
directly.

Pipeline: `sources/*.py` implement `(ctx: ResolvedContext) -> SourceResult[T]`, where
`T` is a rich, source-specific data type the branch defines itself (e.g.
`sources/recent_stats.py`'s `RecentStatsData`) — branches are not forced into a
shared text-block output beyond the `SourceResult` envelope (`source`, `status`,
`as_of`, `data`, `error`). `sources/recent_stats.py` bounds games to strictly
before `ctx.week` (was previously unbounded — a leakage bug) and stamps every
game with `"fantasy_points"` (standard) and `"fantasy_points_ppr"` regardless of
position, alongside the existing position-specific raw stats. `features/*.py` mirrors `sources/` one
module per branch and implements `extract(SourceResult[T]) -> FeatureVector`
(`dict[str, float]`, keys prefixed with the source name).
`feature_vector.py`'s `merge_features` combines each source's contribution into
one `FeatureVector` per player, raising on key collisions. `decision.py`'s
`rank_players` scores each player via `predict_points` — a placeholder
(`recent_stats.avg_fantasy_points_ppr`). `features/`, `feature_vector.py`, and
`decision.py` stay as-is and still print a ranking in `__main__.py`, but they are
**not on the answer path**.

The answer path ends in `answer.py`: `render_context(parsed, players)` turns the
`ParsedRequest` plus each player's `(ResolvedContext, SourceResult[RecentStatsData])`
into a text context (raw prompt, week, scoring format, then per player a
`name (team)` header and one row per game). Each game row shows only the points
for the request's scoring format, labeled (e.g. `fantasy_points (Half-PPR)=15.4`);
Half-PPR is derived as the midpoint of standard and PPR, and an unrecognized
format shows both standard and PPR, labeled. `status="empty"` and `status="error"`
render as explicit lines (the latter including the error string) — a player never
silently disappears. `answer(parsed, players)` sends that context to
`clients/anthropic_client.py`'s `generate_answer` (`config.ANSWER_MODEL`,
`temperature=0`, `messages.parse()`) and returns an `Answer` envelope
(`contracts.py`): `answer: str` (markdown, format chosen by the LLM to fit the
question) and `cited_doc_ids: list[str]` (always empty for now, reserved for a
future news branch). **The LLM makes the start/sit call.**

`resolution/player_resolver.py`'s `resolve_from_player(name, season, week, scoring_format)`
resolves a player name via `load_rosters(season)`, restricted to fantasy
positions (QB/RB/WR/TE/K) — picking the roster row with the latest
`week <= target week` — and returns a `ResolvedContext` directly. Raises on no
match or on a name matching multiple distinct players (`gsis_id`s) — no silent wrong
answers yet. `resolution/request_parser.py`'s `parse_request(prompt)` turns a
natural-language prompt into a `ParsedRequest` (player names, week, scoring format)
via an LLM structured-extraction call (`clients/anthropic_client.py`,
`config.PARSER_MODEL`, `temperature=0`); only week/scoring_format are defaulted
(`config.CURRENT_WEEK`, `"PPR"`) when the LLM doesn't extract them — at least one
player name is required, raises otherwise. Both wired into `__main__.py`, which is
now driven entirely by one natural-language `REQUEST` string and ends by
printing `answer.answer`.

`config.py` pins `SEASON = 2026`, `CURRENT_WEEK = 7`, and the models
`PARSER_MODEL` / `ANSWER_MODEL` (both `"claude-haiku-4-5"`).

Working mode: **Build** — Sid designs, Claude implements to spec.

## LLM usage

Two LLM touch points, both through `clients/anthropic_client.py` at
`temperature=0` with structured output (`messages.parse()` + a Pydantic model):
1. `resolution/request_parser.py` — turns the raw natural-language prompt into a
   structured `ParsedRequest` (player names, week, scoring format).
   Model: `config.PARSER_MODEL`.
2. `answer.py` — **makes the start/sit decision.** Gets the rendered context
   (request + per-player recent stats) and returns the `Answer` envelope.
   Model: `config.ANSWER_MODEL`. The system prompt tells it to say plainly when a
   player's data is missing or failed to load rather than fill the gap.

`decision.py` is no longer the decision layer; it's a placeholder ranking that
stays printed in `__main__.py` but doesn't feed the answer.

## Data Sources

Player/team/NFL data comes from **nflreadpy** (Python port of the R `nflreadr`/nflverse
tooling; loaders return Polars DataFrames). LLM calls go through
`clients/anthropic_client.py` (Anthropic SDK).

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
- [superseded] 2026-07-11 — Final decision layer will be a deterministic model (e.g. a decision
  tree) over the `FeatureVector`, not an LLM. An LLM, if used at all, stays confined
  to a source's `features/` layer (for parsing unstructured input) and never reaches
  the final decision. The decision-tree layer itself is out of scope until a training
  pipeline/labeled data exist.
- 2026-07-13 — Added `decision.py` as a placeholder decision layer (`predict_points`/
  `rank_players`) to prove the `sources` → `features` → `feature_vector` → decision
  pipeline shape end to end, using `recent_stats.avg_fantasy_points_ppr` directly
  rather than a trained model. The real trained decision tree is still future work.
- 2026-07-13 — Fixed a leakage bug in `sources/recent_stats.py`: it never bounded
  games by `ctx.week`, so "recent stats as of week W" included games at/after W.
  Now filtered to `week < ctx.week`. Also added a universal `fantasy_points_ppr`
  stat to every game (not position-gated), giving `features/recent_stats.py` a
  `recent_stats.avg_fantasy_points_ppr` feature — the signal `decision.py`'s
  placeholder uses.
- 2026-07-17 — Request parsing is a third LLM touch point, distinct from the
  `features/`-confined rule above (see "LLM usage"): `resolution/request_parser.py`
  turns a natural-language prompt into a `ParsedRequest` via
  `clients/anthropic_client.py` (`claude-haiku-4-5`, `temperature=0`, structured
  output via `client.messages.parse()` + a Pydantic model). Only player names are
  required from the prompt; week and scoring format default to `config.CURRENT_WEEK`
  and `"PPR"` when not stated. `config.py` gained `CURRENT_WEEK`, the same
  dev-pin convention as `SEASON`. `__main__.py`'s request is now one
  natural-language string instead of the earlier comma-delimited stand-in.
- 2026-10-19 — The LLM now makes the start/sit call (`answer.py` →
  `clients/anthropic_client.py`'s `generate_answer`). Supersedes the 2026-07-11
  deterministic-model entry. `features/`, `feature_vector.py`, and `decision.py`
  stay as they are but are not on the answer path.
- 2026-10-19 — `config.SEASON`/`CURRENT_WEEK` moved to 2026 / 7.
- 2026-10-19 — Models are configurable: `config.PARSER_MODEL` and
  `config.ANSWER_MODEL`, both defaulting to `"claude-haiku-4-5"`;
  `extract_request` reads `PARSER_MODEL` instead of hardcoding the model.
- 2026-10-19 — Answer output is an envelope with a free-form body: `Answer`
  (`answer: str` markdown, LLM picks the format; `cited_doc_ids: list[str]`,
  always empty in v0.5, reserved for the v1 news branch). `temperature=0`.
- 2026-10-19 — The answer context shows fantasy points for the request's scoring
  format, labeled with that format. `sources/recent_stats.py` now also stamps
  standard `fantasy_points`; Half-PPR is derived as `(standard + ppr) / 2`; an
  unrecognized format falls back to showing both, labeled.
- 2026-10-19 — Player resolution only considers fantasy roster positions
  (QB/RB/WR/TE/K), so defensive namesakes (e.g. a CLE LB "Justin Jefferson") no
  longer raise `AmbiguousPlayerNameError`. OL, P, LS and defense excluded.
