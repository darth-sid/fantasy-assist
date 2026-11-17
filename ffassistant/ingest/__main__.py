import argparse
import logging
import sys
from pathlib import Path

from ffassistant.config import CONFIG_PATH, load_config
from ffassistant.ingest.poll import poll

parser = argparse.ArgumentParser(prog="python -m ffassistant.ingest")
parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file to use")
args = parser.parse_args()

logging.basicConfig(format="%(levelname)s %(message)s")
sys.exit(poll(load_config(args.config)))
