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

Structure: all code lives in the `ffassistant/` package (run with
`python -m ffassistant`; imports are absolute, `from ffassistant.x import ...`),
split into two stages plus shared plumbing: `resolution/` (stage 1, prompt ->
`ValidatedRequest`), `answering/` (stage 2, `ValidatedRequest` -> `Answer`, with
`answering/sources/` inside it), `clients/`, and flat `config.py` /
`__main__.py`. `tests/` mirrors the package's folders (`tests/resolution/`,
`tests/answering/`, `tests/answering/sources/`). Paths below are relative to
`ffassistant/`.

**Dependency rule:** `answering/` may import `resolution.models` (the
`ValidatedRequest` handoff type and its parts); `resolution/` never imports from
`answering/`. There is no shared `contracts.py`; each type lives in the stage
that owns it.

`clients/nflreadpy_client.py` holds all raw nflreadpy access.
`clients/anthropic_client.py` is raw SDK access only: one generic
`parse_structured(model, system, user_content, output_model, max_tokens)`
(`messages.parse()`, `temperature=0`). Prompts and Pydantic output schemas live
in the stage modules that use them. Nothing else imports either library.

`__main__.py` is orchestration only: one natural-language `REQUEST` string ->
`extract` -> `validate` -> `answer`. It loads `.env` via `load_dotenv()`, prints
the request, then on `RequestValidationError` prints each error and exits 1
without calling the answer stage; otherwise prints `answer.answer`. The `DEBUG`
env var (`true`, shell or `.env`) is passed as `answer(validated, debug=...)`,
which prints the rendered context it already built before the LLM call.

`config.py` pins `SEASON = 2026`, `CURRENT_WEEK = 7`,
`DEFAULT_SCORING_FORMAT = "PPR"`, and the models `PARSER_MODEL` /
`ANSWER_MODEL` (both `"claude-haiku-4-5"`).

### Stage 1: resolution

Request data model (`resolution/models.py`):
- `ExtractedRequest` (Pydantic, the extraction LLM's output schema):
  `players: list[ExtractedPlayer]` (`mention` as the user wrote it,
  `player_id: str | None` = a `gsis_id`), `week: int | None`,
  `scoring_format: str | None`.
- `ValidatedRequest`: `raw_prompt`, `season`, `week`,
  `scoring_format: ScoringFormat` (`Literal["PPR", "Half-PPR", "Standard"]`),
  `players: list[ValidPlayer]` (`mention`, `player_id`, `full_name`,
  `position`), `rejected: list[RejectedMention]` (`mention`, `reason`).
- `RequestValidationError(errors: list[str])`.

`resolution/roster.py`: `load_fantasy_roster(season)` loads `load_rosters`,
filters to QB/RB/WR/TE/K with a non-null `gsis_id`, keeps the latest-week row
per `gsis_id`, every status included (reserve/IR players are resolvable), and
returns `dict[gsis_id, RosterPlayer]` (`gsis_id`, `full_name`, `team`,
`position`, `status`) sorted by name — the lookup validation uses.
`render_roster` renders a header plus one `gsis_id | full_name | team |
position | status` line per player.

`resolution/extract.py`: `extract(prompt) -> ExtractedRequest`. **Players are
resolved by the LLM with the roster in context, not by string matching.** Two
system blocks: instructions (with `SEASON` and `CURRENT_WEEK`), then the
rendered roster in its own block with `cache_control` (ephemeral) so repeat
calls hit the prompt cache. The instructions: map each mention to a roster
`gsis_id`, trying hard on nicknames, typos, punctuation, and missing suffixes,
null only with no reasonable match; resolve relative weeks from `CURRENT_WEEK`,
return a stated week as written even if invalid (validation rejects it), null
if none stated; normalize common scoring phrasings to `PPR` / `Half-PPR` /
`Standard`, pass anything else through, null if none stated.

`resolution/validate.py`: `validate(extracted, raw_prompt) -> ValidatedRequest`.
Request-level errors are collected and raised together as
`RequestValidationError` (nothing is answered): no players extracted; week
outside 1 to 18; scoring format not one of the three; every mention rejected
(one `could not resolve "<mention>": <reason>` error each). Defaults when null:
week = `CURRENT_WEEK`, scoring format = `DEFAULT_SCORING_FORMAT`. Player-level
(collected in `rejected`, the rest still answered): `player_id` null ->
"no matching player found"; `player_id` not in the roster -> "unknown player
id" (catches hallucinated ids); a repeated `player_id` keeps the first and
drops the duplicate silently.

### Stage 2: answering

`answering/models.py` holds `ResolvedContext` (`player_id`, `player_name`,
`team`, `position`, `season`, `week`, `scoring_format`), `SourceResult[T]`,
`PlayerInputs(ctx, recent_stats, schedule, defense)`, and `Answer`.

`answering/player_context.py`: `player_context(player, season, week,
scoring_format) -> ResolvedContext`. Team comes from the player's roster row
with the latest `week <= target week` (falling back to the earliest row);
`player_name` and `position` come from the `ValidPlayer`.

`answering/generate.py`: `answer(validated) -> Answer` is the stage entry point.
`gather_inputs(validated)` builds a `PlayerInputs` per valid player;
`render_context` turns them into the text context, sent via `parse_structured`
(`config.ANSWER_MODEL`) with a `GeneratedAnswer` output schema. `Answer`:
`answer: str` (markdown, format chosen by the LLM to fit the question) and
`cited_doc_ids: list[str]` (always empty for now, reserved for a future news
branch). **The LLM makes the start/sit call.**

Sources: `answering/sources/*.py` implement `(ctx: ResolvedContext) ->
SourceResult[T]`, where `T` is a rich, source-specific data type the branch
defines itself — branches are not forced into a shared text-block output beyond
the `SourceResult` envelope (`source`, `status`, `as_of`, `data`, `error`).
- `recent_stats.py` (`RecentStatsData`): REG games strictly before `ctx.week`,
  every game stamped with `"fantasy_points"` (standard) and
  `"fantasy_points_ppr"` regardless of position, alongside position-specific raw
  stats.
- `schedule.py` (`ScheduleData`): `team` plus one `ScheduleWeek` (`week`,
  `opponent`, `home`, `played`) per week 1..`ctx.week`, from that season's REG
  games involving `ctx.team`. `opponent=None` means bye; `played` comes from
  `result` being non-null. Known simplification: it uses the player's team as of
  the target week, so a player traded mid-season gets past weeks matched against
  the wrong team's schedule.
- `defense.py` (`DefenseData`: `position`, `rows: list[DefenseRow]`): the league
  table of fantasy points each defense allowed to `ctx.position`: REG games
  strictly before `ctx.week`, summed per `(opponent_team, week)` across that
  position's players, then averaged per defense (`DefenseRow`: `team`, `games`,
  `standard_pg`, `ppr_pg`). No rows (e.g. Week 1) is `status="empty"`.

`answering/context.py`: `render_context(validated, players)` renders the raw
prompt, week, and scoring format, then one `Could not resolve "<mention>":
<reason>` line per rejected mention, then per player a `name (team)` header.
When the normalized mention (lowercase, straight quotes, collapsed whitespace)
differs from the normalized full name, the header is followed by
`Interpreted "CeeDee Lam" as CeeDee Lamb (DAL WR)`. When the schedule loaded,
next comes the target week (`Week 7: vs IND`, `Week 7: @ BAL`, or `Week 7:
BYE`), then the matchup lines (below), then one line per past week
1..`ctx.week - 1` merging schedule and stats: `Week 6: BYE`; the stats line if
the team played and the player has a stat row; `Week 4 vs MIA: did not play` if
the team played and the player has none; `Week 6 vs SF: game not yet played,
stats pending` if the game has no result yet. If `recent_stats` errored while
the schedule loaded, the error line is rendered and played weeks show `stats
unavailable` instead of "did not play". If the schedule is `empty`/`error`, an
explicit line says so (with the error string) and rendering falls back to
stats-only lines. Each stats line shows only the points for the request's
scoring format, labeled (e.g. `fantasy_points (Half-PPR)=15.4`); Half-PPR is
derived as the midpoint of standard and PPR. The matchup line, e.g.
`Matchup: BAL has allowed 34.1 PPR points per game to WRs (rank 5 of 32, 1 = most allowed, league avg 30.2, 6 games)`,
is followed by a fixed small-sample / not-opponent-adjusted caveat line. Its
per-game value uses the same format rule (`_points_for_format`). Rank is
competition-style (ties share a rank) over values rounded to the displayed 0.1;
league avg is the mean of the teams' per-game values. Fallbacks: no line on a
target-week BYE; `Matchup unavailable: no target-week opponent` when the
schedule didn't load (it follows the schedule failure line); `Matchup
unavailable: defense failed to load: <error>` / `Matchup unavailable: no
points-allowed data for WRs before Week 7` for defense `error`/`empty`;
`Matchup unavailable: no games found for <TEAM> defense` when the opponent has
no row; and `Matchup unavailable for kickers ...` when `ctx.position == "K"`.
Kickers get raw stats with no points value plus one `fantasy points unavailable
for kickers ...` line, since nflverse doesn't score kicking. `status="empty"`
and `status="error"` render as explicit lines — a player never silently
disappears.

Working mode: **Build** — Sid designs, Claude implements to spec.

## LLM usage

Two LLM touch points, both through `clients/anthropic_client.py`'s
`parse_structured` (`temperature=0`, `messages.parse()` + a Pydantic model). The
prompts and output schemas live in the calling stage modules:
1. `resolution/extract.py` — turns the raw natural-language prompt into an
   `ExtractedRequest` (player mentions **resolved to `gsis_id`s** against the
   season's fantasy roster, week, scoring format). The roster (~21k tokens for
   2026) is its own prompt-cached system block. Model: `config.PARSER_MODEL`.
   Its output is untrusted until `resolution/validate.py` checks it.
2. `answering/generate.py` — **makes the start/sit decision.** Gets the rendered
   context (request, unresolved mentions, per-player name interpretation,
   schedule, matchup, and recent stats) and returns the `Answer` envelope.
   Model: `config.ANSWER_MODEL`. The system prompt tells it to say plainly when
   a player's data is missing or failed to load rather than fill the gap, that
   a player on bye in the target week cannot score, that the matchup rank
   shouldn't outweigh a player's own usage and production, and to mention
   unresolved players and any name interpretation it relied on.

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
- [superseded] 2026-07-04 — Project structure: `sources/` + `resolution/` subfolders, everything else
  flat. Documented in README.md.
- 2026-07-04 — Added `clients/` subfolder for raw nflreadpy access (both new roster
  access and the existing player-stats call moved in); `sources/`/`resolution/` no
  longer call nflreadpy directly.
- [superseded] 2026-07-04 — Player-name resolution rule: on a multi-team season for one player, use
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
- [superseded] 2026-07-11 — Added `features/` subfolder: one module per source, turning that
  source's `SourceResult[T]` into named numeric `FeatureVector` contributions;
  `feature_vector.py`'s `merge_features` combines them into one vector per player,
  raising on key collisions rather than silently overwriting.
- [superseded] 2026-07-11 — Final decision layer will be a deterministic model (e.g. a decision
  tree) over the `FeatureVector`, not an LLM. An LLM, if used at all, stays confined
  to a source's `features/` layer (for parsing unstructured input) and never reaches
  the final decision. The decision-tree layer itself is out of scope until a training
  pipeline/labeled data exist.
- [superseded] 2026-07-13 — Added `decision.py` as a placeholder decision layer (`predict_points`/
  `rank_players`) to prove the `sources` → `features` → `feature_vector` → decision
  pipeline shape end to end, using `recent_stats.avg_fantasy_points_ppr` directly
  rather than a trained model. The real trained decision tree is still future work.
- 2026-07-13 — Fixed a leakage bug in `sources/recent_stats.py`: it never bounded
  games by `ctx.week`, so "recent stats as of week W" included games at/after W.
  Now filtered to `week < ctx.week`. Also added a universal `fantasy_points_ppr`
  stat to every game (not position-gated), giving `features/recent_stats.py` a
  `recent_stats.avg_fantasy_points_ppr` feature — the signal `decision.py`'s
  placeholder uses.
- [superseded] 2026-07-17 — Request parsing is a third LLM touch point, distinct from the
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
- [superseded] 2026-10-19 — Player resolution only considers fantasy roster positions
  (QB/RB/WR/TE/K), so defensive namesakes (e.g. a CLE LB "Justin Jefferson") no
  longer raise `AmbiguousPlayerNameError`. OL, P, LS and defense excluded.
- 2026-10-19 — Deleted the off-path ranking: `features/`, `feature_vector.py`,
  `decision.py`, their tests, and the `FeatureVector` alias. `__main__.py` no
  longer prints a ranking. Supersedes the 2026-07-11 `features/` and 2026-07-13
  `decision.py` entries.
- 2026-10-19 — Repo reorg: all code moved into an `ffassistant/` package (run with
  `python -m ffassistant`, absolute `ffassistant.` imports); `tests/` mirrors the
  package folders; docs stay at the root. Supersedes the 2026-07-04 structure entry.
- 2026-10-19 — Added `sources/schedule.py` (`schedule(ctx) -> SourceResult[ScheduleData]`,
  one `ScheduleWeek` per week 1..`ctx.week`, `opponent=None` = bye) and
  `clients/nflreadpy_client.py`'s `load_schedules`. Looked up by `ctx.team`;
  mid-season trades are a known, unsolved limitation.
- 2026-10-19 — `answer.py` takes `PlayerInputs(ctx, recent_stats, schedule)` per player
  instead of a `(ctx, stats_result)` tuple; `render_context`, `answer`, and
  `__main__.py` updated.
- 2026-10-19 — Answer context merges schedule and stats per week: target-week line
  (`vs`/`@`/`BYE`), then per past week a bye, stats, did-not-play, or
  stats-pending line. Schedule `empty`/`error` renders explicitly and falls back to
  stats-only. Stats `error` with a loaded schedule keeps bye/pending lines and
  shows played weeks as `stats unavailable`. Answer system prompt notes a player
  on bye can't score.
- 2026-10-19 — Kickers render raw stats with no points value plus an explicit
  "fantasy points unavailable for kickers" line, since nflverse `fantasy_points`
  doesn't score kicking.
- 2026-10-19 — `DEBUG=true` (env var or `.env`) makes `__main__.py` print the
  rendered answer context before the answer.
- [superseded] 2026-10-24 — `ResolvedContext` gains `position`, taken from the roster row in
  `resolve_from_player` (exists even for a player with no games yet).
- 2026-10-24 — Added `sources/defense.py` (`defense(ctx) -> SourceResult[DefenseData]`):
  league table of standard/PPR points each defense allowed per game to `ctx.position`,
  from `load_player_stats`, weeks strictly before `ctx.week`. `PlayerInputs` gains
  `defense`; `__main__.py` calls it.
- 2026-10-24 — Answer context gets a matchup line after the target week (opponent's
  points allowed per game to the position, rank with 1 = most allowed, league avg,
  games) plus a small-sample caveat line. Format via `_points_for_format`; an
  unrecognized format renders one combined line (`Standard / PPR` values, ranks,
  and averages). Explicit fallbacks for BYE (no line), schedule failure, defense
  empty/error, opponent missing, and kickers.
- 2026-10-24 — Answer system prompt: the matchup rank is one input among several
  and shouldn't outweigh a player's own usage and production.
- 2026-10-24 — v0.8 request data model: extract (LLM fills `ExtractedRequest`) ->
  validate (deterministic, `ValidatedRequest` or `RequestValidationError`) ->
  answer (runs only on a `ValidatedRequest`).
- 2026-10-24 — Players are resolved by the extraction LLM with the season's
  fantasy roster in context (returns `gsis_id`s), not by string matching. It tries
  hard on nicknames, typos, punctuation, and missing suffixes; null only with no
  real idea. Supersedes the 2026-07-04 name-resolution and 2026-07-17
  request-parsing entries. `player_resolver.py` and `request_parser.py` removed.
- 2026-10-24 — Fantasy roster context: QB/RB/WR/TE/K, one row per `gsis_id`
  (latest week), every status, one `gsis_id | full_name | team | position |
  status` line each, in its own `cache_control` system block. Supersedes the
  2026-10-19 fantasy-positions resolution entry (the filter carries over).
- 2026-10-24 — Partial answers: if some mentions fail validation, answer the valid
  players and state which mentions couldn't be resolved and why (rendered
  `Could not resolve ...` lines; answer prompt told to mention them).
- 2026-10-24 — Validation: week must be 1 to 18 and scoring format one of `PPR`,
  `Half-PPR`, `Standard` (request-level, along with no players and all mentions
  rejected); null/unknown `player_id` rejected per player; duplicate ids dropped
  silently. Defaults: `CURRENT_WEEK`, `DEFAULT_SCORING_FORMAT`.
- 2026-10-24 — Stage split: `resolution/` (models, roster, extract, validate) and
  `answering/` (models, player_context, sources, context, generate). `answering/`
  may import `resolution.models`; `resolution/` never imports `answering/`.
  `contracts.py` and `answer.py` removed; their types moved to the owning stage.
- 2026-10-24 — `clients/anthropic_client.py` is raw SDK access only: one generic
  `parse_structured`. Prompts and output schemas moved into `resolution/extract.py`
  and `answering/generate.py`.
- 2026-10-24 — `ResolvedContext` is built in `answering/player_context.py` from a
  `ValidPlayer`: team from the latest roster row at or before the target week,
  `position` from the `ValidPlayer`. Supersedes the earlier 2026-10-24
  `resolve_from_player` position entry.
- 2026-10-24 — Answer context adds an `Interpreted "<mention>" as <name> (<TEAM>
  <POS>)` line when the normalized mention differs from the roster name; the
  "unrecognized format shows both" rendering branches are removed since the
  format is now always valid.
- 2026-10-24 — `DEBUG` is threaded into `answer(validated, debug=...)`, which
  prints the context it built, so sources are never loaded twice for the print.
