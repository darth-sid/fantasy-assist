# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

The pipeline has two stages with one handoff type, `ValidatedRequest`:

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
    the player's position before the target week.
  - `context.py` — `render_context` turns the `ValidatedRequest` and each
    player's `PlayerInputs` into a text context: the request header, a line per
    unresolved mention, then per player an "Interpreted as" line when the
    mention differs from the roster name, the target week's opponent or bye,
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
- `config.py` — dev-time static pins (`SEASON`, `CURRENT_WEEK`), the
  `DEFAULT_SCORING_FORMAT`, and the `PARSER_MODEL` / `ANSWER_MODEL` choices.
- `__main__.py` — orchestration only: a natural-language `REQUEST` → extract →
  validate → answer. A rejected request prints its errors and exits non-zero.

`tests/` is a pytest suite mirroring the package folders (`tests/resolution/`,
`tests/answering/`, `tests/answering/sources/`). Client calls are mocked at the `clients/` boundary —
no test hits the network.

Run tests with `pytest` from the repo root. Run the pipeline with
`python -m ffassistant` from the repo root; it needs Anthropic API credentials:
`ANTHROPIC_API_KEY` in a `.env` at the repo root (loaded by `__main__.py`), in the
environment, or an `ant auth login` profile.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
