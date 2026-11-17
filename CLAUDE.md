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

No huge docstrings. Utility modules (e.g. `ingest/gazetteer.py`) and their public
API functions/classes get a very short docstring, one line preferably, two at most.
If a function is genuinely complicated enough to seem to need more, ask Sid rather
than writing it.

## Current edge

Structure: all code lives in the `ffassistant/` package (run with
`python -m ffassistant`; imports are absolute, `from ffassistant.x import ...`),
split into three stages plus shared plumbing: `ingest/` (stage 0, feeds -> stored
news items, independent of the other two), `resolution/` (stage 1, prompt ->
`ValidatedRequest`), `answering/` (stage 2, `ValidatedRequest` -> `Answer`, with
`answering/sources/` inside it), `clients/`, and flat `config.py` /
`__main__.py`. `tests/` mirrors the package's folders (`tests/clients/`, `tests/ingest/`, `tests/resolution/`,
`tests/answering/`, `tests/answering/sources/`). Paths below are relative to
`ffassistant/`.

**Dependency rule:** `answering/` may import `resolution.models` (the
`ValidatedRequest` handoff type and its parts), and `ingest.store` (read
functions only: `iter_items`, `iter_tags`) and `ingest.models.NewsItem` /
`NewsTags`; `resolution/` never
imports from `answering/`; `ingest/` imports nothing from `resolution/` or
`answering/`. There is no shared `contracts.py`; each type lives in the stage
that owns it.

`clients/nflreadpy_client.py` holds all raw nflreadpy access, including
`get_current_week()` (nflreadpy's default schedule-based lookup, never
`use_date=True`). LLM access goes through a provider-neutral interface in
`clients/llm_client.py`: the `LLMClient` ABC with one method,
`generate_structured(model, system, user_content, output_model, max_tokens) ->
StructuredResponse[T]`, plus the neutral types it speaks: `SystemBlock`
(`text`, `cache: bool`, a prompt-caching hint providers may ignore),
`TokenUsage` (`input_tokens`, `output_tokens`, `cache_write_tokens`,
`cache_read_tokens`), and `StructuredResponse` (`parsed: T`, `usage:
TokenUsage`). `get_llm_client()` returns the implementation named by
`config.LLM_PROVIDER` (`"anthropic"`; anything else raises `ValueError`); the
stages do `client = get_llm_client()` then `client.generate_structured(...)`,
and tests monkeypatch
`get_llm_client`. `clients/anthropic_client.py`'s `AnthropicClient` is raw SDK
access only (`messages.parse()`, `temperature=0`): it turns `SystemBlock`s into
text blocks (`cache=True` -> `cache_control` ephemeral) and the SDK usage into
`TokenUsage`. Prompts and Pydantic output schemas live in the stage modules that
use them. Nothing else imports either library.

`__main__.py` is orchestration only: one natural-language request ->
`extract` -> `validate` -> `answer`. The request is the first command-line
argument (`python -m ffassistant "question"`), falling back to the hardcoded
`REQUEST`. It loads `.env` via `load_dotenv()`, prints the request, computes the
current week once with `get_current_week()` and passes it to both
`extract(request, current_week, debug=...)` and `validate(extracted, request,
current_week)` so they agree, then on `RequestValidationError` prints each
error and exits 1 without calling the answer stage; otherwise prints
`answer.answer`, then, if there are any citations, a `Sources:` block with one
`- <title> (<published date>): <url>` line per `Citation` (nothing extra when
there are none). The `DEBUG` env var (`true`, shell or `.env`) turns on debug
output in order: `extract` prints the `ExtractedRequest` (each mention with
its `player_id` or null, week, scoring format) and the extract call's
`cache_write_tokens` / `cache_read_tokens`; `__main__` prints
validation's `rejected` list; `answer(validated, debug=...)` prints a `---
News ranking ---` block (per player, for the team and opponent buckets: the
ranker, the filled-in query, and each selected item's score, date, and title,
highest score first; `news: not fetched` / `news: <status>` otherwise), then
the rendered context it already built, before the LLM call.

`config.py` pins `SEASON = 2026`, `DEFAULT_SCORING_FORMAT = "PPR"`, and the
models `PARSER_MODEL` / `ANSWER_MODEL` (both `"claude-haiku-4-5"`), and the
news retrieval knobs `NEWS_TOP_K = 5` (player bucket), `NEWS_TEAM_TOP_K = 3`,
`NEWS_OPPONENT_TOP_K = 3`, `NEWS_LOOKBACK_DAYS = 14`,
`NEWS_MAX_SUMMARY_CHARS = 500`, and the team/opponent ranking settings:
`NEWS_RANKER = "bm25"` (or `"recency"`), the query templates `NEWS_QUERY_TEAM`
/ `NEWS_QUERY_OPPONENT` (placeholders `{player}`, `{position_words}`, `{team}`,
`{opponent}`), and `NEWS_POSITION_WORDS` (QB/RB/WR/TE/K -> words for
`{position_words}`). There is no current-week pin; the current week
comes from the schedule at run time.

### Stage 0: ingest

`ingest/` is a standalone collector (`python -m ffassistant.ingest`): one poll of
every feed in `config.FEEDS` per invocation, then exit. Scheduling is external
(cron/launchd); poll frequency is not in config. It builds the news history that
retrieval reads. **Dependency rule:** `ingest/` imports nothing from
`resolution/` or `answering/` (it may use `clients/` and `config`);
`answering/` may import only `ingest.store`'s read functions (`iter_items`,
`iter_tags`) and `ingest.models.NewsItem` / `NewsTags`; `resolution/` imports
nothing from it.

- `clients/rss_client.py`: `fetch_feed(url) -> bytes`, raw HTTP only (`requests`,
  20 s timeout, `ffassistant/0.1` User-Agent; non-200 raises).
- `ingest/store.py` is the only module that touches `data/news/`:
  `load_doc_ids()`, `append_items(items)`, `iter_items()`, and for tags
  `iter_tags()`, `append_tags(tags)`, `replace_tags(tags)` (writes a temp file
  and renames it over `tags.jsonl`, so a failed rebuild never leaves it
  half-written). `iter_items`/`iter_tags` are retrieval's read interface; a
  missing file yields nothing. The path is `config.NEWS_DIR`
  (`data/news`) resolved against the repo root, so cwd doesn't matter under
  cron. `data/` is gitignored.
- `ingest/poll.py`: loads stored `doc_id`s, then per feed independently
  (a failure doesn't stop the others) fetches, parses with `feedparser`
  (malformed-but-has-entries -> warning and use them; no entries -> logged),
  builds `NewsItem`s, skips entries with no link and any `doc_id` already
  stored or seen earlier in the poll, and appends. One status line per feed
  (`rotowire: 5 fetched, 2 new` / `espn: error: <reason>`). Then it runs the
  index catch-up and prints `index: tagged N items`, or `index: error: <reason>`
  if it fails (the items stay; the next successful catch-up tags them). Exit 1
  only if every feed failed. A second run immediately after adds nothing.
- `ingest/gazetteer.py`: `load_gazetteer(season) -> Gazetteer` from
  `load_rosters` and `load_teams`. `players`: name key -> `[(gsis_id, team)]`,
  every position, non-null `gsis_id`, latest-week row per player; a name clash
  keeps every player. `teams`: alias -> abbreviation for `team_name`,
  `team_nick`, and the city (`team_name` minus `team_nick`) only when no other
  team shares it (so `Washington` yes, `New York` / `Los Angeles` no);
  abbreviations are never aliases. Aliases keep their case and match
  **case-sensitively** (`Bills`, not `bills`), so ordinary words don't tag
  teams; player names match in any case. Only the season's roster teams are used,
  since `load_teams` also lists relocated franchises and a duplicate Rams row.
  `Gazetteer.find(text) -> Mentions` (`players`: one candidate list per
  player-name mention; `teams`: the named teams) matches whole words, longest
  name first and non-overlapping, so `Parker Washington` is a player and not
  the WAS city alias. `name_key`: lowercase, curly quotes straightened,
  periods removed, whitespace collapsed, a trailing `jr`/`sr`/`ii`/`iii`/`iv`
  removed.
- `ingest/tag.py`: `tag(item, gazetteer) -> NewsTags`. **Shared names:** a
  mention matching several players tags only those whose team the item names
  (a team alias in its title or summary); if none of them is named, every match
  is tagged. `rotowire`: players from the title text before the first `": "`
  only (summaries use last names and name opponents); the summary's team names
  are used only to break shared-name ties, never tagged; teams = the tagged
  players' teams. Other sources: players and team aliases found in the title or
  summary, plus the tagged players' teams. Lists are deduped and sorted.
  A player's team is their roster team at tagging time, so a traded player's
  old items move only on `--rebuild`.
- `ingest/index.py` (`python -m ffassistant.ingest.index [--rebuild]`):
  `index(rebuild=False) -> int`. Default is catch-up, tagging every item with
  no tags row; `--rebuild` re-tags every item and replaces `tags.jsonl` (after
  a tagger change, or to pick up roster moves). Prints `tagged N items`.
- `ingest/overrides.py`: two independent per-feed override registries keyed by
  the `FEEDS` key; a feed with no entry uses the defaults. `DATE_PARSERS[key]`
  (raw date string -> aware datetime) replaces feedparser's date parse, and
  `ID_KEYS[key]` ((url, raw date) -> string hashed into `doc_id`) replaces the
  default of the URL alone. **Adding a feed:** fetch it and check item count,
  date span, description quality, link uniqueness, and whether feedparser parses
  its dates correctly; register an override only for what fails; record the
  findings in API_CONTEXT.md.
- Storage: `data/news/items.jsonl`, one `NewsItem` per line, append-only,
  kept forever; no raw XML snapshots. `data/news/tags.jsonl`, one `NewsTags`
  (`doc_id`, `player_ids` gsis_ids, `teams` abbreviations) per tagged item,
  rebuildable from the items at any time.
- `NewsItem`: `doc_id` (first 16 hex of sha256 of the normalized URL; for
  feeds with an `ID_KEYS` override, of that override's key; RotoWire: `url + "\n" + raw date string`), `url` (stripped,
  `#fragment` removed, nothing else), `source` (the `FEEDS` key), `title` and
  `summary` (plain text: tags stripped, entities decoded, whitespace
  collapsed), `published_at` (ISO 8601 UTC; falls back to `fetched_at` when the
  date is missing or unparseable), `fetched_at` (poll time, ISO 8601 UTC),
  `raw` (`title`, `summary`, `link`, `published` as feedparser returned them).
- Only feed title and summary are stored; linked articles are never fetched.
  Chunking and embeddings are later steps, not in ingest.

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

`resolution/extract.py`: `extract(prompt, current_week, debug=False) ->
ExtractedRequest`. **Players are resolved by the LLM with the roster in
context, not by string matching.** Two system blocks: instructions (with
`SEASON` and the passed-in current week), then the rendered roster in its own block with `cache_control` (ephemeral) so repeat
calls hit the prompt cache. The instructions: map each mention to a roster
`gsis_id`, trying hard on nicknames, typos, punctuation, and missing suffixes,
null only with no reasonable match; resolve relative weeks from the current week,
return a stated week as written even if invalid (validation rejects it), null
if none stated; normalize common scoring phrasings to `PPR` / `Half-PPR` /
`Standard`, pass anything else through, null if none stated.

`resolution/validate.py`: `validate(extracted, raw_prompt, current_week) ->
ValidatedRequest`. Request-level errors are collected and raised together as
`RequestValidationError` (nothing is answered): no players extracted; week
outside 1 to 18; scoring format not one of the three; every mention rejected
(one `could not resolve "<mention>": <reason>` error each). Defaults when null:
week = the passed-in current week, scoring format =
`DEFAULT_SCORING_FORMAT`. Player-level (collected in `rejected`, the rest still answered): `player_id` null ->
"no matching player found"; `player_id` not in the roster -> "unknown player
id" (catches hallucinated ids); a repeated `player_id` keeps the first and
drops the duplicate silently.

### Stage 2: answering

`answering/models.py` holds `ResolvedContext` (`player_id`, `player_name`,
`team`, `position`, `roster_status`, `season`, `week`, `scoring_format`),
`SourceResult[T]`, `PlayerInputs(ctx, recent_stats, schedule, defense,
injuries, news)` (`news: SourceResult[NewsData] | None`, None when not fetched
because of a target-week BYE or a schedule that isn't `ok`), `Citation`
(`doc_id`, `title`, `published_at`, `url`; decoupled from `NewsEntry`, with
the adapter `Citation.from_news_entry` living alongside it in the models), and
`Answer`.

`answering/player_context.py`: `player_context(player, season, week,
scoring_format) -> ResolvedContext`. Team and `roster_status` come from the
player's roster row with the latest `week <= target week` (falling back to the
earliest row); `player_name` and `position` come from the `ValidPlayer`.

`answering/generate.py`: `answer(validated, debug=False, now=None) -> Answer`
is the stage entry point. `gather_inputs(validated, now=None)` builds a
`PlayerInputs` per valid player (`now` defaults to the current UTC time and is
injectable for tests); `render_context` turns them into the text context, sent
via `generate_structured` (`config.ANSWER_MODEL`) with a `GeneratedAnswer` output
schema (`answer`, `cited_doc_ids`). **News cutoff:** `news_cutoff(schedule,
week, now)` = `min(now, kickoff of the target-week game)`, so upcoming weeks use
now and past weeks use that game's kickoff; it is None (news not fetched) when
the schedule isn't `ok` (no safe cutoff) or the target week is a BYE. After
generation, `cited_doc_ids` not among the rendered news items are dropped
deterministically, and the rest become `Citation`s via
`Citation.from_news_entry`. `Answer`:
`answer: str` (markdown, format chosen by the LLM to fit the question) and
`citations: list[Citation]`. **The LLM makes the start/sit call.**

Sources: `answering/sources/*.py` implement `(ctx: ResolvedContext) ->
SourceResult[T]`, where `T` is a rich, source-specific data type the branch
defines itself — branches are not forced into a shared text-block output beyond
the `SourceResult` envelope (`source`, `status`, `as_of`, `data`, `error`).
- `recent_stats.py` (`RecentStatsData`): REG games strictly before `ctx.week`,
  every game stamped with `"fantasy_points"` (standard) and
  `"fantasy_points_ppr"` regardless of position, alongside position-specific raw
  stats.
- `schedule.py` (`ScheduleData`): `team` plus one `ScheduleWeek` (`week`,
  `opponent`, `home`, `played`, `kickoff`) per week 1..`ctx.week`, from that
  season's REG games involving `ctx.team`. `opponent=None` means bye; `played`
  comes from `result` being non-null; `kickoff` is ISO 8601 UTC from `gameday` +
  `gametime` read as `America/New_York` local time (midnight Eastern when
  `gametime` is null), None on a bye. Known simplification: it uses the player's team as of
  the target week, so a player traded mid-season gets past weeks matched against
  the wrong team's schedule.
- `defense.py` (`DefenseData`: `position`, `rows: list[DefenseRow]`): the league
  table of fantasy points each defense allowed to `ctx.position`: REG games
  strictly before `ctx.week`, summed per `(opponent_team, week)` across that
  position's players, then averaged per defense (`DefenseRow`: `team`, `games`,
  `standard_pg`, `ppr_pg`). No rows (e.g. Week 1) is `status="empty"`.
- `injuries.py` (`InjuryData`: `week`, `entry: InjuryEntry | None`): the
  `load_injuries` rows for `week == ctx.week` and `team == ctx.team`. No rows
  for the team that week is `status="empty"` (report not out yet, or bye).
  Otherwise `ok`, with `entry=None` meaning the team reported and the player
  isn't on it. `InjuryEntry`: `report_status` (`Out` / `Doubtful` /
  `Questionable`, or null = listed without a game designation),
  `primary_injury`, `practice_status`. Reserve-list players drop off the
  report, which is why roster status is shown too.
- `news.py` (`NewsData`: `cutoff`, `player`, `team`, `opponent`, each a
  `list[NewsEntry]`; `NewsEntry`: `doc_id`, `source`, `published_at`, `title`,
  `summary`, `url`, `score` (the ranker's score, None for the player bucket;
  never rendered into the context)): `news(ctx, opponent, cutoff)`, the one
  source that takes extra arguments (the target-week opponent and the cutoff).
  Retrieval over the ingest-time tags; team scoping is the only filter. Joins `iter_items()` with `iter_tags()` on `doc_id` (items
  with no tags row are skipped) and keeps items with `cutoff -
  NEWS_LOOKBACK_DAYS <= published_at < cutoff`, newest first. Each item lands in
  the first bucket it qualifies for: player (`ctx.player_id` in `player_ids`),
  then team (`ctx.team` in `teams`), then opponent (`opponent` in `teams`).
  The player bucket is always newest first, capped at `NEWS_TOP_K` (the newest
  update about the player is what matters). The team and opponent buckets are
  ranked by `config.NEWS_RANKER` against their query template (`news_query(ctx,
  opponent, bucket)`), capped at `NEWS_TEAM_TOP_K` / `NEWS_OPPONENT_TOP_K`,
  then rendered newest first. Summaries
  have RotoWire's trailing `Visit RotoWire.com for more analysis on this
  update.` stripped, then are truncated to `NEWS_MAX_SUMMARY_CHARS` plus `...`.
  `status="empty"` only when all three buckets are empty (including missing
  files); `as_of` is the cutoff. Out of scope: the RotoWire id crosswalk.

`answering/ranking.py`: rankers share one signature, `(query, candidates,
corpus) -> list[(RankDoc, score)]` in rank order (`RankDoc`: `doc_id`, `text`,
`published_at`), registered in `RANKERS`. Ties go to the newer document.
`rank_recency`: score = publish timestamp, query and corpus ignored. `rank_bm25`
(`bm25s`, default lucene BM25, its English stopwords, no stemmer): the index is
built over the whole corpus, i.e. every tagged item in the lookback window
across all teams, so term weights come from a larger sample than one bucket;
scores are then read for the bucket's candidates, and zero scores are dropped.
Document text is `title + " " + cleaned summary`.

`answering/context.py`: `render_context(validated, players)` renders the raw
prompt, week, and scoring format, then one `Could not resolve "<mention>":
<reason>` line per rejected mention, then per player a `name (team)` header.
When the normalized mention (lowercase, straight quotes, collapsed whitespace)
differs from the normalized full name, the header is followed by
`Interpreted "CeeDee Lam" as CeeDee Lamb (DAL WR)`. Then, for any
`roster_status` other than `ACT`, `Roster status: RES (reserve list, not
available to play)` (known codes: `RES` reserve list, not available to play;
`INA` inactive; `PUP` physically unable to perform list, not available to
play; `CUT` released; `DEV` practice squad; `RET` retired; anything else is
`(unrecognized status code)`). Then the injury line, skipped when the roster
status is `RES` or `PUP` (reserve players drop off the report, so "not on the
report" would read as healthy) and when the target
week is a BYE: `Injury report (Week 7): Questionable (Groin). Practice:
Limited Participation in Practice`, `Injury report (Week 7): no game
designation. Practice: ...` (listed, no designation), `Not on the Week 7
injury report`, `Week 7 injury report not available yet` (`empty`), or `Week 7
injury report failed to load: <error>`; the `(injury)` and `Practice: ...`
parts are omitted when null. When the schedule loaded,
next comes the target week (`Week 7: vs IND`, `Week 7: @ BAL`, or `Week 7:
BYE`), then the matchup lines (below), then one line per past week
1..`ctx.week - 1` merging schedule and stats: `Week 6: BYE`; the stats line if
the team played and the player has a stat row; `Week 4 vs MIA: did not play` if
the team played and the player has none; `Week 6 @ SF: game not yet played,
stats pending` if the game has no result yet. Past-week lines use `vs` for home
and `@` for away from the schedule's `home` flag, like the target week line. If `recent_stats` errored while
the schedule loaded, the error line is rendered and played weeks show `stats
unavailable` instead of "did not play". If the schedule is `empty`/`error`, an
explicit line says so (with the error string) and rendering falls back to
stats-only lines, which always use `vs`. Each stats line shows only the points for the request's
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
After the matchup lines (and after the schedule failure / matchup line in the
stats-only fallback) come the news lines: `News (most recent first, before
2026-11-15 18:00 UTC, last 14 days):`, then three groups in order, `About
<player name>:`, `<TEAM> team news:`, `Opponent (<OPP>) news:`, each followed
by one `- [<doc_id>] 2026-11-13 21:30 UTC, rotowire: <title>. <summary>` line
per item (title only when the summary is empty) or `- none`; `No news found in the 14 days before <cutoff>` (`empty`); `News
failed to load: <error>` (`error`); `News unavailable: schedule failed to load,
so no safe cutoff` when not fetched because the schedule isn't `ok`; nothing on
a target-week BYE.
Kickers get raw stats with no points value plus one `fantasy points unavailable
for kickers ...` line, since nflverse doesn't score kicking. `status="empty"`
and `status="error"` render as explicit lines — a player never silently
disappears.

Working mode: **Build** — Sid designs, Claude implements to spec.

## LLM usage

Two LLM touch points, both via `client = get_llm_client()` then
`client.generate_structured(...)`
(`clients/llm_client.py`; the Anthropic implementation uses `temperature=0`,
`messages.parse()` + a Pydantic model). The
prompts and output schemas live in the calling stage modules:
1. `resolution/extract.py` — turns the raw natural-language prompt into an
   `ExtractedRequest` (player mentions **resolved to `gsis_id`s** against the
   season's fantasy roster, week, scoring format), given the current week. The roster (~21k tokens for
   2026) is its own prompt-cached system block. Model: `config.PARSER_MODEL`.
   Its output is untrusted until `resolution/validate.py` checks it.
2. `answering/generate.py` — **makes the start/sit decision.** Gets the rendered
   context (request, unresolved mentions, per-player name interpretation,
   roster status, injury report, schedule, matchup, player/team/opponent news, and recent stats) and returns the `Answer` envelope.
   Model: `config.ANSWER_MODEL`. The system prompt tells it to say plainly when
   a player's data is missing or failed to load rather than fill the gap, that
   a player on bye in the target week cannot score, that a player marked `Out`
   or on a reserve or PUP list will not play (`Doubtful` unlikely, `Questionable`
   uncertain), that the matchup rank
   shouldn't outweigh a player's own usage and production, and to mention
   unresolved players and any name interpretation it relied on. It also treats
   the news items as the most current information on availability and role,
   cites each item it relies on by id in `cited_doc_ids` (only ids in the
   context; others are dropped after generation), and flags news that conflicts
   with the injury report, favoring whichever is more recent. Team and opponent
   news are context (teammate availability, opposing defenders) that shouldn't
   outweigh the player's own news and production, cited the same way.

## Data Sources

Player/team/NFL data comes from **nflreadpy** (Python port of the R `nflreadr`/nflverse
tooling; loaders return Polars DataFrames). LLM calls go through the
`LLMClient` interface in `clients/llm_client.py`, implemented for the Anthropic
SDK in `clients/anthropic_client.py`.

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
- [superseded] 2026-10-19 — Answer output is an envelope with a free-form body: `Answer`
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
- [superseded] 2026-10-24 — `clients/anthropic_client.py` is raw SDK access only: one generic
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
- 2026-10-24 — Current week comes from nflreadpy's schedule-based
  `get_current_week()` (via `clients/nflreadpy_client.py`), computed once in
  `__main__.py` and passed to `extract` and `validate`. `CURRENT_WEEK` removed from
  `config.py`; `use_date=True` rejected (wrong for 2026). `SEASON` stays pinned.
- 2026-10-24 — `ResolvedContext` gains `roster_status` (same roster row as team);
  the answer context renders a `Roster status: <CODE> (<meaning>)` line for any
  status other than `ACT`.
- 2026-10-24 — Added `answering/sources/injuries.py` (`injuries(ctx) ->
  SourceResult[InjuryData]`) and `clients/nflreadpy_client.py`'s `load_injuries`.
  Both roster status and the injury report are shown, since reserve players drop
  off the report. `PlayerInputs` gains `injuries`.
- 2026-10-24 — Answer context renders one injury line per player after the roster
  status line (skipped on a target-week BYE); answer system prompt says
  Out/reserve/PUP won't play, Doubtful is unlikely, Questionable is uncertain.
- 2026-10-24 — Past-week lines use `vs`/`@` from the schedule's `home` flag; the
  stats-only fallback (schedule failed) keeps `vs`.
- 2026-10-24 — `__main__.py` takes the request from the first command-line
  argument, falling back to `REQUEST`.
- [superseded] 2026-10-24 — `parse_structured` returns a `StructuredResponse[T]` (`parsed`,
  `usage`) instead of the bare parsed model, so callers can see cache usage.
- 2026-10-24 — `DEBUG=true` also prints the resolution stage: `extract(...,
  debug=...)` prints the `ExtractedRequest` and the extract call's cache
  creation/read tokens, and `__main__.py` prints validation's `rejected` list.
- 2026-11-06 — v1.0 news collector: `ingest/` stage (`python -m ffassistant.ingest`)
  polls `config.FEEDS` once per invocation and exits; scheduling is external, so
  no frequency in config. Imports nothing from `resolution/`/`answering/`, and
  they import nothing from it.
- 2026-11-06 — Ingest stores feed title and summary only (no article fetching),
  parsed at poll time, append-only forever, no raw XML snapshots; each item keeps
  its original entry fields in `raw` for re-parsing.
- 2026-11-06 — `ingest/store.py` is the only module touching `items.jsonl`
  (`load_doc_ids`, `append_items`, `iter_items`), so the backend can change
  without touching polling or retrieval.
- 2026-11-06 — Feeds kept: RotoWire NFL and ESPN NFL. ProFootballTalk dropped
  (teaser-only descriptions).
- 2026-11-06 — Dedup is on `doc_id` = sha256[:16] of the normalized URL, except
  feeds with an `ID_KEYS` override (RotoWire's links repeat across items, so its
  key adds the raw date string).
- 2026-11-06 — Per-feed oddities live in `ingest/overrides.py` as two independent
  registries, `DATE_PARSERS` and `ID_KEYS`, not in ad hoc code in `poll.py`.
  RotoWire overrides both: its `2:30:00 PM PST` dates are mis-parsed by feedparser
  (reads 2:30 PM as 02:30 UTC), and its links repeat per player.
- 2026-11-06 — `NEWS_DIR` is resolved against the repo root, not cwd, so cron and
  launchd runs write to the same place regardless of working directory.
- 2026-11-10 — v1.1 minimal news retrieval: per player, stored news items about
  that player, before a cutoff, within a lookback window, newest first, top K,
  rendered into the answer context. Recency-only ranking; no index, embeddings,
  or Chroma (the baseline embeddings get compared against later).
- [superseded] 2026-11-10 — News tagging happens at retrieval time by name-key matching
  (RotoWire: title prefix before `": "` only; other sources: whole words in title
  or summary). No separate index or tagging step.
- 2026-11-10 — Knobs in `config.py`: `NEWS_TOP_K = 5`, `NEWS_LOOKBACK_DAYS = 14`,
  `NEWS_MAX_SUMMARY_CHARS = 500`.
- 2026-11-10 — News cutoff is a correctness rule: `min(now, target-week
  kickoff)`. No news on a target-week BYE; no news when the schedule isn't `ok`
  (`error` or `empty`), rendered as "no safe cutoff". `ScheduleWeek` gains
  `kickoff` (ISO 8601 UTC from Eastern `gameday`/`gametime`).
- [superseded] 2026-11-10 — Dependency rule: `answering/` may import `ingest.store`'s read
  function (`iter_items`) and `ingest.models.NewsItem`; `ingest/` still imports
  nothing from the other stages.
- 2026-11-10 — Citations: the answer LLM cites news ids in `cited_doc_ids`;
  ids not in the rendered context are dropped deterministically. `Answer`
  replaces `cited_doc_ids` with `citations: list[Citation]` (`doc_id`, `title`,
  `published_at`, `url`), a decoupled adapter over the rendered `NewsEntry`s;
  `__main__.py` prints them as a `Sources:` block. Supersedes the 2026-10-19
  "always empty `cited_doc_ids`" part of the answer-envelope entry.
- 2026-11-11 — `parse_structured` replaced by a provider-neutral `LLMClient` ABC
  (`clients/llm_client.py`) with `generate_structured`, obtained via
  `get_llm_client()` from `config.LLM_PROVIDER` (`"anthropic"`).
  `AnthropicClient` in `clients/anthropic_client.py` implements it. Supersedes
  the 2026-10-24 `parse_structured` entries.
- 2026-11-11 — The interface uses neutral types: `SystemBlock(text, cache)`
  instead of Anthropic block dicts, and `TokenUsage` (input/output/cache-write/
  cache-read counts) instead of the SDK's `Usage`; the Anthropic implementation
  translates both ways. Extract's debug cache line now prints
  `cache_write_tokens` / `cache_read_tokens`.
- 2026-11-16 — v1.2: news items are tagged at ingest with the players and teams
  they mention, and the answer context carries the player's own news plus news
  about the player's team and the target-week opponent. Supersedes the
  2026-11-10 retrieval-time tagging entry; player news now comes from tags only.
- 2026-11-16 — Tagger is a deterministic gazetteer (roster name keys and team
  name / nickname / unique-city aliases), no LLM. Every rostered position is
  included, so opposing defenders are tagged. A name clash tags every match.
- 2026-11-16 — Tags live in a separate, rebuildable `data/news/tags.jsonl`
  (`NewsTags`: `doc_id`, `player_ids`, `teams`); `items.jsonl` stays raw and
  append-only. `poll` runs a catch-up after appending; `python -m
  ffassistant.ingest.index --rebuild` re-tags everything.
- 2026-11-16 — Team / opponent news is anything tagged with that team,
  including items about its players (a player tag implies their team).
- 2026-11-16 — Separate caps per bucket (`NEWS_TOP_K` 5 player,
  `NEWS_TEAM_TOP_K` 3, `NEWS_OPPONENT_TOP_K` 3); an item appears once, in the
  first bucket it qualifies for, in priority order player > team > opponent.
- 2026-11-16 — Dependency rule: `answering/` may import `ingest.store`'s read
  functions (`iter_items`, `iter_tags`) and `ingest.models.NewsItem` /
  `NewsTags`. Supersedes the 2026-11-10 dependency entry.
- 2026-11-16 — Code style: utility modules and their public API get very short
  docstrings (1 line preferably, 2 at most); still no huge docstrings.
- 2026-11-16 — Team aliases match case-sensitively (`Bills`, not `bills`) so
  ordinary words don't tag teams; player names still match in any case.
- 2026-11-16 — Shared names: tag only the players whose team the item names (a
  team alias in title or summary), falling back to tagging every match. For
  RotoWire, summary team names are used only for this tie-break, never as tags.
  Refines the 2026-11-16 "a name clash tags every match" rule, which is now the
  fallback.
- 2026-11-17 — v1.3: the team and opponent buckets are ranked by BM25
  relevance to a per-bucket query template instead of pure recency, behind
  `config.NEWS_RANKER` (`"bm25"` default, `"recency"` kept for comparison).
  Finding: newest-K let low-relevance items crowd out important ones.
- 2026-11-17 — Team scoping is the only filter; relevance within a bucket
  comes from the query templates (`NEWS_QUERY_TEAM`, `NEWS_QUERY_OPPONENT`,
  `NEWS_POSITION_WORDS`), not position rules.
- 2026-11-17 — BM25 before dense retrieval. `bm25s==0.3.16` with its English
  stopwords and no stemmer. Index over every tagged item in the window (all
  teams); zero scores dropped; ties go to the newer item; the selected items
  render newest first. `NewsEntry` gains `score`, not rendered.
- 2026-11-17 — The player's own bucket stays recency-only.
- 2026-11-17 — `DEBUG=true` prints a `--- News ranking ---` block per player
  (ranker, filled-in query, each selected item's score, date, title).
- 2026-11-17 — The injury line is skipped for `RES` and `PUP` roster statuses:
  the roster status line already says the player is unavailable, and reserve
  players drop off the report, so "Not on the Week N injury report" read as
  healthy. Other non-ACT statuses keep the injury line.
