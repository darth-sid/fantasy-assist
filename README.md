# Fantasy Football Start/Sit RAG Assistant

Purpose: learn RAG by building a start/sit decision tool.

## Project Structure

- `sources/` — retrieval branches with the `(ctx: ResolvedContext) -> ContextBlock`
  contract. One module per data source (e.g. `recent_stats.py`). Only functions that
  return `ContextBlock` belong here.
- `resolution/` — turns a raw request into a `ResolvedContext`. Not created yet — entity
  resolution is currently a hardcoded stand-in inline in `__main__.py`.
- Everything else stays flat at the top level for now:
  - `contracts.py` — the `ResolvedContext` / `ContextBlock` dataclasses.
  - `config.py` — dev-time static pins (e.g. the pinned `SEASON`).
  - `assembler.py` — joins a `list[ContextBlock]` into one prompt string.
  - `__main__.py` — runnable example wiring a hardcoded request through a branch.

See [CLAUDE.md](CLAUDE.md) for the working agreement and decision log, and
[API_CONTEXT.md](API_CONTEXT.md) for the nflreadpy data-source reference.
