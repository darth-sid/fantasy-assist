# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

The pipeline: a natural-language request → `resolution/request_parser.py`
extracts structured fields → `resolution/player_resolver.py` resolves each player
→ `sources/` fetch structured data → `answer.py` renders that data into a text
context and has an LLM write the answer, including the start/sit call.

All code lives in the `ffassistant/` package:

- `sources/` — retrieval branches with the `(ctx: ResolvedContext) -> SourceResult[T]`
  contract. One module per data source (e.g. `recent_stats.py`), each defining its
  own rich, source-specific data type (e.g. `RecentStatsData`) as the `T` — branches
  are not forced into a shared output shape beyond the `SourceResult` envelope
  (`source`, `status`, `as_of`, `data`, `error`).
- `resolution/` — turns a raw request into resolved identifiers.
  `request_parser.py` turns a natural-language prompt into a `ParsedRequest`
  (player names, week, scoring format) via an LLM structured-extraction call
  (see CLAUDE.md § LLM usage). `player_resolver.py` resolves a player name +
  season + week to a `ResolvedContext` via that season's rosters, restricted to
  QB/RB/WR/TE/K.
- `clients/` — raw third-party access, kept separate from `sources/`/`resolution/`
  so neither has to know how a given dependency is actually called.
  `nflreadpy_client.py` (nflreadpy) and `anthropic_client.py` (Anthropic SDK);
  `sources/`/`resolution/` call through these instead of importing either
  library directly.
- `answer.py` — the end of the pipeline. `render_context` turns the parsed request
  and each player's `(ResolvedContext, SourceResult)` into a text context (empty
  and errored results render as explicit lines, so no player silently drops out);
  each game row shows fantasy points for the request's scoring format, labeled;
  `answer` sends it to the LLM and returns an `Answer` (`answer` markdown,
  `cited_doc_ids`).
- `contracts.py` — the `ParsedRequest` / `ResolvedContext` / `SourceResult[T]` /
  `Answer` dataclasses.
- `config.py` — dev-time static pins (`SEASON`, `CURRENT_WEEK`) and the
  `PARSER_MODEL` / `ANSWER_MODEL` choices.
- `__main__.py` — runnable example wiring a natural-language request through
  the pipeline.

`tests/` is a pytest suite mirroring the package folders (`tests/sources/`,
`tests/resolution/`, ...). Client calls are mocked at the `clients/` boundary —
no test hits the network.

Run tests with `pytest` from the repo root. Run the pipeline with
`python -m ffassistant` from the repo root; it needs Anthropic API credentials:
`ANTHROPIC_API_KEY` in a `.env` at the repo root (loaded by `__main__.py`), in the
environment, or an `ant auth login` profile.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
