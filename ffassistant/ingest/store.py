from collections.abc import Iterator
from pathlib import Path

from ffassistant.config import NEWS_DIR
from ffassistant.ingest.models import NewsItem

ITEMS_PATH = Path(__file__).resolve().parents[2] / NEWS_DIR / "items.jsonl"


def load_doc_ids() -> set[str]:
    return {item.doc_id for item in iter_items()}


def append_items(items: list[NewsItem]) -> None:
    if not items:
        return
    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ITEMS_PATH.open("a", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def iter_items() -> Iterator[NewsItem]:
    if not ITEMS_PATH.exists():
        return
    with ITEMS_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield NewsItem.model_validate_json(line)
