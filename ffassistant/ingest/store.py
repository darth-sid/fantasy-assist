"""The only reader and writer of data/news/ (items.jsonl and tags.jsonl)."""

import os
from collections.abc import Iterator
from pathlib import Path

from ffassistant.ingest.models import NewsItem, NewsTags


def _items_path(news_dir: Path) -> Path:
    return news_dir / "items.jsonl"


def _tags_path(news_dir: Path) -> Path:
    return news_dir / "tags.jsonl"


def load_doc_ids(news_dir: Path) -> set[str]:
    """Returns the doc_id of every stored item."""
    return {item.doc_id for item in iter_items(news_dir)}


def append_items(news_dir: Path, items: list[NewsItem]) -> None:
    """Appends items to items.jsonl, creating it if needed."""
    if not items:
        return
    news_dir.mkdir(parents=True, exist_ok=True)
    with _items_path(news_dir).open("a", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def iter_items(news_dir: Path) -> Iterator[NewsItem]:
    """Yields every stored item in append order; nothing if the file is missing."""
    path = _items_path(news_dir)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield NewsItem.model_validate_json(line)


def iter_tags(news_dir: Path) -> Iterator[NewsTags]:
    """Yields every stored tags row; nothing if the file is missing."""
    path = _tags_path(news_dir)
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield NewsTags.model_validate_json(line)


def append_tags(news_dir: Path, tags: list[NewsTags]) -> None:
    """Appends tags rows to tags.jsonl, creating it if needed."""
    if not tags:
        return
    news_dir.mkdir(parents=True, exist_ok=True)
    with _tags_path(news_dir).open("a", encoding="utf-8") as f:
        for entry in tags:
            f.write(entry.model_dump_json() + "\n")


def replace_tags(news_dir: Path, tags: list[NewsTags]) -> None:
    """Atomically replaces tags.jsonl with the given rows."""
    news_dir.mkdir(parents=True, exist_ok=True)
    tags_path = _tags_path(news_dir)
    tmp_path = tags_path.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for entry in tags:
            f.write(entry.model_dump_json() + "\n")
    # Rename over the old file so a failed rebuild never leaves it half-written.
    os.replace(tmp_path, tags_path)
