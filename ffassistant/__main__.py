import os
import sys

from dotenv import load_dotenv

from ffassistant.answering.generate import answer
from ffassistant.clients.nflreadpy_client import get_current_week
from ffassistant.resolution.extract import extract
from ffassistant.resolution.models import RequestValidationError
from ffassistant.resolution.validate import validate

load_dotenv()

# --- Natural-language request (stands in for a real request surface) ---
REQUEST = "CeeDee Lamb or Justin Jefferson for Week 7? Or maybe Ja'Marr Chase?"
REQUEST = "Davante or Downs for week 7?"
# -------------------------------------------------------------------------

request = sys.argv[1] if len(sys.argv) > 1 else REQUEST
debug = os.getenv("DEBUG", "").lower() == "true"

print(f"Request: {request}")
print()

current_week = get_current_week()
try:
    extracted = extract(request, current_week, debug=debug)
    validated = validate(extracted, request, current_week)
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

print(answer(validated, debug=debug).answer)
