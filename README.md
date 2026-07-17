# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

The pipeline: a natural-language request → `resolution/request_parser.py`
extracts structured fields → `sources/` fetch structured data → `features/` turn
each source's data into named numeric contributions → `feature_vector.py` merges
those into one `FeatureVector` per player → `decision.py` scores and ranks
players. The scoring step is currently a placeholder standing in for a future
trained deterministic model (e.g. a decision tree).

- `sources/` — retrieval branches with the `(ctx: ResolvedContext) -> SourceResult[T]`
  contract. One module per data source (e.g. `recent_stats.py`), each defining its
  own rich, source-specific data type (e.g. `RecentStatsData`) as the `T` — branches
  are not forced into a shared output shape beyond the `SourceResult` envelope
  (`source`, `status`, `as_of`, `data`, `error`).
- `features/` — one module per source, turning that source's `SourceResult[T]` into
  a `FeatureVector` contribution (`dict[str, float]`, keys prefixed with the source
  name). Encoding decisions live here — this is also where an LLM would live for a
  future *unstructured* source (e.g. parsing injury-report prose into a number); the
  LLM is confined to this layer and never reaches the final decision.
- `feature_vector.py` — `merge_features` combines each source's feature
  contributions into one `FeatureVector` per player; raises on a key collision
  rather than silently overwriting.
- `decision.py` — scores and ranks players from their `FeatureVector`s.
  `predict_points` is currently a placeholder (reads
  `recent_stats.avg_fantasy_points_ppr` directly) proving the pipeline shape; not
  yet a trained model.
- `resolution/` — turns a raw request into resolved identifiers.
  `request_parser.py` turns a natural-language prompt into a `ParsedRequest`
  (player names, week, scoring format) via an LLM structured-extraction call —
  the third allowed LLM touch point, alongside unstructured `features/` sources,
  both confined to upstream of the decision layer (see CLAUDE.md § LLM usage).
  `player_resolver.py` resolves a player name + season + week to a
  `ResolvedContext` via that season's rosters. Both wired into `__main__.py`.
- `clients/` — raw third-party access, kept separate from `sources/`/`resolution/`
  so neither has to know how a given dependency is actually called.
  `nflreadpy_client.py` (nflreadpy) and `anthropic_client.py` (Anthropic SDK);
  `sources/`/`resolution/` call through these instead of importing either
  library directly.
- `tests/` — pytest suite, mirrors module names. Client calls are mocked at the
  `clients/` boundary — no test hits the network.
- Everything else stays flat at the top level for now:
  - `contracts.py` — the `ResolvedContext` / `SourceResult[T]` / `ParsedRequest`
    dataclasses and the `FeatureVector` type alias.
  - `config.py` — dev-time static pins (the pinned `SEASON` and `CURRENT_WEEK`).
  - `__main__.py` — runnable example wiring a natural-language request through
    the pipeline.

Run tests with `pytest` from the repo root. Running `__main__.py` requires
Anthropic API credentials (`ANTHROPIC_API_KEY`, or an `ant auth login` profile).

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
