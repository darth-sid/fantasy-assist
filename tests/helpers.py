from pathlib import Path

from ffassistant.config import Config, load_config

CFG = load_config()


def with_news(cfg: Config = CFG, **overrides) -> Config:
    """A copy of cfg with some news settings replaced."""
    return cfg.model_copy(update={"news": cfg.news.model_copy(update=overrides)})


def with_news_dir(news_dir: Path, cfg: Config = CFG) -> Config:
    """A copy of cfg reading and writing news under news_dir."""
    return cfg.model_copy(update={"news_dir": news_dir})
