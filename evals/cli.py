"""Command-line options shared by the tools that compare two configs."""

from __future__ import annotations

import argparse
from pathlib import Path

from ffassistant.config import CONFIG_PATH, Config, load_config


def add_config_args(parser: argparse.ArgumentParser) -> None:
    """--config base plus -a / -b override files merged over it."""
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="base config")
    parser.add_argument("-a", type=Path, required=True, help="override file for config A")
    parser.add_argument("-b", type=Path, required=True, help="override file for config B")


def load_configs(args: argparse.Namespace) -> tuple[Config, Config]:
    """Configs A and B: the base config with each override merged over it."""
    return load_config(args.config, [args.a]), load_config(args.config, [args.b])
