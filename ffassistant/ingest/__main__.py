import logging
import sys

from ffassistant.ingest.poll import poll

logging.basicConfig(format="%(levelname)s %(message)s")
sys.exit(poll())
