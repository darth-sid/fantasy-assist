from pathlib import Path

import pytest

import ffassistant.ingest.poll as poll_module
import ffassistant.ingest.store as store

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def feeds(monkeypatch, tmp_path):
    """Maps feed key -> fixture filename or Exception; fetch_feed serves them."""
    served: dict[str, str | Exception] = {}
    monkeypatch.setattr(store, "ITEMS_PATH", tmp_path / "news" / "items.jsonl")
    monkeypatch.setattr(poll_module, "FEEDS", {k: f"https://{k}.test/feed" for k in ("rotowire", "generic")})

    def fake_fetch(url):
        key = url.split("//")[1].split(".")[0]
        result = served[key]
        if isinstance(result, Exception):
            raise result
        return (FIXTURES / result).read_bytes()

    monkeypatch.setattr(poll_module, "fetch_feed", fake_fetch)
    served.update(rotowire="rotowire.xml", generic="generic.xml")
    return served
