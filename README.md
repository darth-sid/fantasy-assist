# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

The pipeline: a natural-language request → `resolution/request_parser.py`
extracts structured fields → `resolution/player_resolver.py` resolves each player
→ `sources/` fetch structured data → `answer.py` renders that data into a text
context and has an LLM write the answer, including the start/sit call. A
placeholder ranking (`features/` → `feature_vector.py` → `decision.py`) is still
printed alongside but is not on the answer path.

- `sources/` — retrieval branches with the `(ctx: ResolvedContext) -> SourceResult[T]`
  contract. One module per data source (e.g. `recent_stats.py`), each defining its
  own rich, source-specific data type (e.g. `RecentStatsData`) as the `T` — branches
  are not forced into a shared output shape beyond the `SourceResult` envelope
  (`source`, `status`, `as_of`, `data`, `error`).
- `features/` — one module per source, turning that source's `SourceResult[T]` into
  a `FeatureVector` contribution (`dict[str, float]`, keys prefixed with the source
  name). Not on the answer path.
- `feature_vector.py` — `merge_features` combines each source's feature
  contributions into one `FeatureVector` per player; raises on a key collision
  rather than silently overwriting.
- `decision.py` — placeholder ranking of players from their `FeatureVector`s
  (`predict_points` reads `recent_stats.avg_fantasy_points_ppr` directly). Printed
  in `__main__.py`, but not on the answer path.
- `answer.py` — the end of the pipeline. `render_context` turns the parsed request
  and each player's `(ResolvedContext, SourceResult)` into a text context (empty
  and errored results render as explicit lines, so no player silently drops out);
  each game row shows fantasy points for the request's scoring format, labeled;
  `answer` sends it to the LLM and returns an `Answer` (`answer` markdown,
  `cited_doc_ids`).
- `resolution/` — turns a raw request into resolved identifiers.
  `request_parser.py` turns a natural-language prompt into a `ParsedRequest`
  (player names, week, scoring format) via an LLM structured-extraction call
  (see CLAUDE.md § LLM usage).
  `player_resolver.py` resolves a player name + season + week to a
  `ResolvedContext` via that season's rosters, restricted to QB/RB/WR/TE/K. Both wired into `__main__.py`.
- `clients/` — raw third-party access, kept separate from `sources/`/`resolution/`
  so neither has to know how a given dependency is actually called.
  `nflreadpy_client.py` (nflreadpy) and `anthropic_client.py` (Anthropic SDK);
  `sources/`/`resolution/` call through these instead of importing either
  library directly.
- `tests/` — pytest suite, mirrors module names. Client calls are mocked at the
  `clients/` boundary — no test hits the network.
- Everything else stays flat at the top level for now:
  - `contracts.py` — the `ResolvedContext` / `SourceResult[T]` / `ParsedRequest` /
    `Answer` dataclasses and the `FeatureVector` type alias.
  - `config.py` — dev-time static pins (`SEASON`, `CURRENT_WEEK`) and the
    `PARSER_MODEL` / `ANSWER_MODEL` choices.
  - `__main__.py` — runnable example wiring a natural-language request through
    the pipeline.

Run tests with `pytest` from the repo root. Running `__main__.py` requires
Anthropic API credentials: `ANTHROPIC_API_KEY` in a `.env` at the repo root
(loaded by `__main__.py`), in the environment, or an `ant auth login` profile.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
