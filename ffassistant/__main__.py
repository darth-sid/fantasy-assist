import os
import sys

from dotenv import load_dotenv

from ffassistant.answering.generate import answer
from ffassistant.resolution.extract import extract
from ffassistant.resolution.models import RequestValidationError
from ffassistant.resolution.validate import validate

load_dotenv()

# --- Natural-language request (stands in for a real request surface) ---
REQUEST = "CeeDee Lamb or Justin Jefferson for Week 7? Or maybe Ja'Marr Chase?"
# -------------------------------------------------------------------------

print(f"Request: {REQUEST}")
print()

try:
    validated = validate(extract(REQUEST), REQUEST)
except RequestValidationError as exc:
    print("Could not answer this request:")
    for error in exc.errors:
        print(f"- {error}")
    sys.exit(1)

print(answer(validated, debug=os.getenv("DEBUG", "").lower() == "true").answer)
