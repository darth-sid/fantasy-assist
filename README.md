# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

- `sources/` — retrieval branches with the `(ctx: ResolvedContext) -> ContextBlock`
  contract. One module per data source (e.g. `recent_stats.py`). Only functions that
  return `ContextBlock` belong here.
- `resolution/` — turns a raw request into resolved identifiers. So far:
  `player_resolver.py` resolves a player name + season + week to a `PlayerMatch`
  (`player_id`, `player_name`, `team`) via that season's rosters. Not yet wired into
  `__main__.py` — the hardcoded stand-in there is still in place.
- `clients/` — raw third-party data access, kept separate from `sources/`/`resolution/`
  so neither has to know how a given data source is actually fetched.
  `nflreadpy_client.py` is the only client so far; both `sources/` and `resolution/`
  call through it instead of importing `nflreadpy` directly.
- `tests/` — pytest suite, mirrors module names (`test_assembler.py`,
  `test_recent_stats.py`, `test_player_resolver.py`). Client calls are mocked at the
  `clients/` boundary — no test hits the network.
- Everything else stays flat at the top level for now:
  - `contracts.py` — the `ResolvedContext` / `ContextBlock` dataclasses.
  - `config.py` — dev-time static pins (e.g. the pinned `SEASON`).
  - `assembler.py` — joins a `list[ContextBlock]` into one prompt string.
  - `__main__.py` — runnable example wiring a hardcoded request through a branch.

Run tests with `pytest` from the repo root.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
