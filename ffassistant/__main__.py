import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ffassistant.answering.generate import answer
from ffassistant.clients.nflreadpy_client import get_current_week
from ffassistant.config import CONFIG_PATH, load_config
from ffassistant.resolution.extract import extract
from ffassistant.resolution.models import RequestValidationError
from ffassistant.resolution.validate import validate

load_dotenv()

# --- Natural-language request (stands in for a real request surface) ---
REQUEST = "CeeDee Lamb or Justin Jefferson? Or maybe Ja'Marr Chase?"
# -------------------------------------------------------------------------

parser = argparse.ArgumentParser(prog="python -m ffassistant")
parser.add_argument("request", nargs="?", default=REQUEST, help="the question to answer")
parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="config file to use")
args = parser.parse_args()

request = args.request
debug = os.getenv("DEBUG", "").lower() == "true"
cfg = load_config(args.config)

print(f"Request: {request}")
print()

current_week = get_current_week()
try:
    extracted = extract(request, current_week, cfg, debug=debug)
    validated = validate(extracted, request, current_week, cfg)
except RequestValidationError as exc:
    print("Could not answer this request:")
    for error in exc.errors:
        print(f"- {error}")
    sys.exit(1)

if debug:
    print("--- Rejected mentions ---")
    for rejected in validated.rejected:
        print(f'"{rejected.mention}": {rejected.reason}')
    if not validated.rejected:
        print("(none)")
    print("-------------------------")
    print()

result = answer(validated, cfg, debug=debug)
print(result.answer)
if result.citations:
    print()
    print("Sources:")
    for citation in result.citations:
        print(f"- {citation.title} ({citation.published_at[:10]}): {citation.url}")
