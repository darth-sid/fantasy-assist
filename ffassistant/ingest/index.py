from __future__ import annotations

import argparse
from pathlib import Path

from ffassistant.config import CONFIG_PATH, Config, load_config
from ffassistant.ingest import store
from ffassistant.ingest.gazetteer import load_gazetteer
from ffassistant.ingest.tag import tag


def index(cfg: Config, rebuild: bool = False) -> int:
    """Tags untagged items (or re-tags all with rebuild) and returns how many were tagged."""
    gazetteer = load_gazetteer(cfg.season)
    items = list(store.iter_items(cfg.news_dir))
    if rebuild:
        tags = [tag(item, gazetteer) for item in items]
        store.replace_tags(cfg.news_dir, tags)
        return len(tags)
    tagged = {entry.doc_id for entry in store.iter_tags(cfg.news_dir)}
    tags = [tag(item, gazetteer) for item in items if item.doc_id not in tagged]
    store.append_tags(cfg.news_dir, tags)
    return len(tags)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m ffassistant.ingest.index")
    parser.add_argument("--rebuild", action="store_true", help="re-tag every stored item")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file to use")
    args = parser.parse_args()
    print(f"tagged {index(load_config(args.config), rebuild=args.rebuild)} items")
