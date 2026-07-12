# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

The pipeline: `sources/` fetch structured data → `features/` turn each source's
data into named numeric contributions → `feature_vector.py` merges those into one
`FeatureVector` per player. A future deterministic model (e.g. a decision tree)
consumes that vector; it isn't built yet.

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
- `resolution/` — turns a raw request into resolved identifiers. So far:
  `player_resolver.py` resolves a player name + season + week to a `ResolvedContext`
  via that season's rosters. Wired into `__main__.py`.
- `clients/` — raw third-party data access, kept separate from `sources/`/`resolution/`
  so neither has to know how a given data source is actually fetched.
  `nflreadpy_client.py` is the only client so far; both `sources/` and `resolution/`
  call through it instead of importing `nflreadpy` directly.
- `tests/` — pytest suite, mirrors module names. Client calls are mocked at the
  `clients/` boundary — no test hits the network.
- Everything else stays flat at the top level for now:
  - `contracts.py` — the `ResolvedContext` / `SourceResult[T]` dataclasses and the
    `FeatureVector` type alias.
  - `config.py` — dev-time static pins (e.g. the pinned `SEASON`).
  - `__main__.py` — runnable example wiring a hardcoded request through the pipeline.

Run tests with `pytest` from the repo root.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
