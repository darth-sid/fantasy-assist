# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

A separate collector, `ingest/` (stage 0), polls NFL news RSS feeds and stores
the items for later retrieval; it shares no code with the two request-time
stages below.

The request pipeline has two stages with one handoff type, `ValidatedRequest`:

1. **Resolution** (`resolution/`) — a natural-language request → an LLM
   extracts an `ExtractedRequest` (player mentions resolved to `gsis_id`s
   against the season's fantasy roster, week, scoring format) → deterministic
   validation turns it into a `ValidatedRequest`, or rejects the request with
   specific errors.
2. **Answering** (`answering/`) — each valid player becomes a `ResolvedContext`
   → `sources/` fetch structured data → the data is rendered into a text context
   → an LLM writes the answer, including the start/sit call.

`answering/` may import `resolution.models` (the handoff type); `resolution/`
never imports from `answering/`.

All code lives in the `ffassistant/` package:

- `ingest/` — stage 0, feeds → stored news items. `poll.py` polls every feed in
  `config.FEEDS` once and appends new items; `store.py` is the only code that
  touches `data/news/items.jsonl`; `models.py` has `NewsItem`; `overrides.py` holds
  per-feed date-parsing and id-key overrides (see CLAUDE.md § Stage 0).
- `resolution/` — stage 1, prompt → `ValidatedRequest`.
  - `models.py` — `ExtractedRequest` / `ExtractedPlayer` (the LLM's output
    schema), `ValidatedRequest` / `ValidPlayer` / `RejectedMention`, and
    `RequestValidationError`.
  - `roster.py` — the season's fantasy roster (QB/RB/WR/TE/K, every status,
    one entry per `gsis_id`), rendered as LLM context and used as the
    `gsis_id` lookup for validation.
  - `extract.py` — the LLM call that fills `ExtractedRequest`, with the roster
    in a prompt-cached system block (see CLAUDE.md § LLM usage).
  - `validate.py` — `ExtractedRequest` → `ValidatedRequest`. Request-level
    problems (no players, week outside 1–18, unknown scoring format, every
    mention rejected) raise; unresolvable mentions are collected as
    `rejected` and the rest are still answered.
- `answering/` — stage 2, `ValidatedRequest` → `Answer`.
  - `models.py` — `ResolvedContext`, `SourceResult[T]`, `PlayerInputs`,
    `Answer`.
  - `player_context.py` — a `ValidPlayer` + the request's season, week, and
    format → `ResolvedContext`, with the team as of the target week.
  - `sources/` — retrieval branches with the
    `(ctx: ResolvedContext) -> SourceResult[T]` contract. One module per data
    source, each defining its own rich, source-specific data type as the `T` —
    branches are not forced into a shared output shape beyond the
    `SourceResult` envelope (`source`, `status`, `as_of`, `data`, `error`).
    `recent_stats.py` (`RecentStatsData`) has the player's per-game stats
    before the target week; `schedule.py` (`ScheduleData`) has the player's
    team's opponent, home/away, and played status for each week through the
    target week, with `None` opponent meaning bye; `defense.py` (`DefenseData`)
    has the league table of fantasy points each defense allowed per game to
    the player's position before the target week; `injuries.py`
    (`InjuryData`) has the player's injury report entry for the target week,
    or whether the team's report isn't out yet.
  - `context.py` — `render_context` turns the `ValidatedRequest` and each
    player's `PlayerInputs` into a text context: the request header, a line per
    unresolved mention, then per player an "Interpreted as" line when the
    mention differs from the roster name, the roster status when it isn't
    active (e.g. reserve list), the target week's injury report designation,
    the target week's opponent or bye,
    the opponent's points allowed to the player's position with a league rank,
    and one line per past week merging schedule and stats. Empty and errored
    results render as explicit lines, so no player silently drops out.
  - `generate.py` — `answer(validated)`, the stage entry point: gathers each
    player's inputs, renders the context, and has the LLM return an `Answer`
    (`answer` markdown, `cited_doc_ids`).
- `clients/` — raw third-party access, so the stages never have to know how a
  dependency is actually called. `nflreadpy_client.py` (nflreadpy) and
  `anthropic_client.py` (one generic structured-output call; prompts and output
  schemas live in the stages).
- `config.py` — the dev-time `SEASON` pin (the current week comes from the
  schedule at run time), the
  `DEFAULT_SCORING_FORMAT`, and the `PARSER_MODEL` / `ANSWER_MODEL` choices.
- `__main__.py` — orchestration only: a natural-language request (the first
  command-line argument, or the hardcoded `REQUEST`) → extract → validate →
  answer. A rejected request prints its errors and exits non-zero.

`tests/` is a pytest suite mirroring the package folders (`tests/resolution/`,
`tests/answering/`, `tests/answering/sources/`). Client calls are mocked at the `clients/` boundary —
no test hits the network.

Run tests with `pytest` from the repo root. Run the pipeline from the repo root
with `python -m ffassistant "Lamb or Jefferson this week?"` (no argument falls
back to the hardcoded `REQUEST`; `DEBUG=true` prints the resolution stage,
prompt-cache usage, and the answer context). It needs Anthropic API credentials:
`ANTHROPIC_API_KEY` in a `.env` at the repo root (loaded by `__main__.py`), in the
environment, or an `ant auth login` profile.

## Running the news collector

```
python -m ffassistant.ingest
```

Each run polls every feed once, appends new items to `data/news/items.jsonl`
(gitignored), prints one status line per feed, and exits (non-zero only if every
feed failed). It does not loop; schedule it. RotoWire's feed holds only the last
few updates, so poll often (every 15 minutes or so is safer than hourly).

Hourly with cron (`crontab -e`):

```
0 * * * * cd /Users/sid/code/personal/projects/WIP/FFassistant && /Users/sid/code/personal/projects/WIP/FFassistant/.venv/bin/python -m ffassistant.ingest >> /Users/sid/code/personal/projects/WIP/FFassistant/data/ingest.log 2>&1
```

Hourly with launchd, saved as `~/Library/LaunchAgents/com.ffassistant.ingest.plist`
and loaded with `launchctl load ~/Library/LaunchAgents/com.ffassistant.ingest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ffassistant.ingest</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/sid/code/personal/projects/WIP/FFassistant/.venv/bin/python</string>
    <string>-m</string>
    <string>ffassistant.ingest</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/sid/code/personal/projects/WIP/FFassistant</string>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>/Users/sid/code/personal/projects/WIP/FFassistant/data/ingest.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/sid/code/personal/projects/WIP/FFassistant/data/ingest.log</string>
</dict>
</plist>
```

The cron line and the plist both write `data/ingest.log`; create `data/` first if
the collector hasn't run yet.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
