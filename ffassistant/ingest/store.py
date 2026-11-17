"""The only reader and writer of data/news/ (items.jsonl and tags.jsonl)."""

import os
from collections.abc import Iterator
from pathlib import Path

from ffassistant.config import NEWS_DIR
from ffassistant.ingest.models import NewsItem, NewsTags

ITEMS_PATH = Path(__file__).resolve().parents[2] / NEWS_DIR / "items.jsonl"
TAGS_PATH = Path(__file__).resolve().parents[2] / NEWS_DIR / "tags.jsonl"


def load_doc_ids() -> set[str]:
    """Returns the doc_id of every stored item."""
    return {item.doc_id for item in iter_items()}


def append_items(items: list[NewsItem]) -> None:
    """Appends items to items.jsonl, creating it if needed."""
    if not items:
        return
    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ITEMS_PATH.open("a", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def iter_items() -> Iterator[NewsItem]:
    """Yields every stored item in append order; nothing if the file is missing."""
    if not ITEMS_PATH.exists():
        return
    with ITEMS_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield NewsItem.model_validate_json(line)


def iter_tags() -> Iterator[NewsTags]:
    """Yields every stored tags row; nothing if the file is missing."""
    if not TAGS_PATH.exists():
        return
    with TAGS_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield NewsTags.model_validate_json(line)


def append_tags(tags: list[NewsTags]) -> None:
    """Appends tags rows to tags.jsonl, creating it if needed."""
    if not tags:
        return
    TAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TAGS_PATH.open("a", encoding="utf-8") as f:
        for entry in tags:
            f.write(entry.model_dump_json() + "\n")


def replace_tags(tags: list[NewsTags]) -> None:
    """Atomically replaces tags.jsonl with the given rows."""
    TAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = TAGS_PATH.with_suffix(".jsonl.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for entry in tags:
            f.write(entry.model_dump_json() + "\n")
    # Rename over the old file so a failed rebuild never leaves it half-written.
    os.replace(tmp_path, TAGS_PATH)
