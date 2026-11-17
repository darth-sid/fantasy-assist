from pathlib import Path

from ffassistant.ingest.gazetteer import Gazetteer

import pytest

import ffassistant.ingest.index as index_module
import ffassistant.ingest.poll as poll_module
from tests.helpers import CFG, with_news_dir

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg(tmp_path):
    """The real config with news under tmp_path and two test feeds."""
    ingest = CFG.ingest.model_copy(
        update={"feeds": {k: f"https://{k}.test/feed" for k in ("rotowire", "generic")}}
    )
    return with_news_dir(tmp_path / "news").model_copy(update={"ingest": ingest})


@pytest.fixture
def feeds(monkeypatch, cfg):
    """Maps feed key -> fixture filename or Exception; fetch_feed serves them."""
    served: dict[str, str | Exception] = {}
    gazetteer = Gazetteer(players={"micah parsons": [("00-9", "GB")]}, teams={"Packers": "GB"})
    monkeypatch.setattr(index_module, "load_gazetteer", lambda season: gazetteer)

    def fake_fetch(url):
        key = url.split("//")[1].split(".")[0]
        result = served[key]
        if isinstance(result, Exception):
            raise result
        return (FIXTURES / result).read_bytes()

    monkeypatch.setattr(poll_module, "fetch_feed", fake_fetch)
    served.update(rotowire="rotowire.xml", generic="generic.xml")
    return served
