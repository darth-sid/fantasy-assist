import pytest
import yaml
from pydantic import ValidationError

from ffassistant.config import CONFIG_PATH, REPO_ROOT, load_config


def _write(tmp_path, data: dict):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def _raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def test_repo_config_loads_with_news_dir_under_repo_root():
    cfg = load_config()

    assert cfg.news_dir == REPO_ROOT / "data" / "news"
    assert cfg.news.ranker in {"bm25", "recency"}


def test_unknown_key_raises(tmp_path):
    data = _raw()
    data["news"]["rankr"] = "bm25"

    with pytest.raises(ValidationError, match="rankr"):
        load_config(_write(tmp_path, data))


def test_missing_key_raises(tmp_path):
    data = _raw()
    del data["news"]["top_k"]

    with pytest.raises(ValidationError, match="top_k"):
        load_config(_write(tmp_path, data))


def test_config_is_frozen():
    with pytest.raises(ValidationError):
        load_config().news.top_k = 1


def test_override_deep_merges_nested_keys(tmp_path):
    override = tmp_path / "override.yaml"
    override.write_text("news:\n  ranker: recency\n")

    cfg = load_config(CONFIG_PATH, [override])

    assert cfg.news.ranker == "recency"
    assert cfg.news.top_k == load_config().news.top_k
    assert cfg.llm.judge_model == load_config().llm.judge_model


def test_unknown_key_in_override_raises(tmp_path):
    override = tmp_path / "override.yaml"
    override.write_text("news:\n  rankr: recency\n")

    with pytest.raises(ValidationError, match="rankr"):
        load_config(CONFIG_PATH, [override])
