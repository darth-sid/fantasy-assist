from __future__ import annotations

import argparse

from ffassistant.config import SEASON
from ffassistant.ingest import store
from ffassistant.ingest.gazetteer import load_gazetteer
from ffassistant.ingest.tag import tag


def index(rebuild: bool = False) -> int:
    """Tags untagged items (or re-tags all with rebuild) and returns how many were tagged."""
    gazetteer = load_gazetteer(SEASON)
    items = list(store.iter_items())
    if rebuild:
        tags = [tag(item, gazetteer) for item in items]
        store.replace_tags(tags)
        return len(tags)
    tagged = {entry.doc_id for entry in store.iter_tags()}
    tags = [tag(item, gazetteer) for item in items if item.doc_id not in tagged]
    store.append_tags(tags)
    return len(tags)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m ffassistant.ingest.index")
    parser.add_argument("--rebuild", action="store_true", help="re-tag every stored item")
    args = parser.parse_args()
    print(f"tagged {index(rebuild=args.rebuild)} items")
