import runpy
import sys

import ffassistant.answering.generate as generate_module
import ffassistant.clients.nflreadpy_client as nflreadpy_client
import ffassistant.resolution.extract as extract_module
import ffassistant.resolution.validate as validate_module
from ffassistant.answering.models import Answer


def _run_main(monkeypatch, argv: list[str]) -> dict:
    seen = {}

    def fake_extract(prompt, current_week, debug=False):
        seen.update(prompt=prompt, extract_week=current_week)
        return "extracted"

    def fake_validate(extracted, raw_prompt, current_week):
        seen.update(raw_prompt=raw_prompt, validate_week=current_week)
        return "validated"

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setattr(nflreadpy_client, "get_current_week", lambda: 9)
    monkeypatch.setattr(extract_module, "extract", fake_extract)
    monkeypatch.setattr(validate_module, "validate", fake_validate)
    monkeypatch.setattr(
        generate_module, "answer", lambda validated, debug: Answer(answer="ok", cited_doc_ids=[])
    )
    module_globals = runpy.run_module("ffassistant.__main__", run_name="__main__")
    seen["REQUEST"] = module_globals["REQUEST"]
    return seen


def test_request_comes_from_first_argument(monkeypatch):
    seen = _run_main(monkeypatch, ["ffassistant", "Bijan or Gibbs?"])

    assert seen["prompt"] == "Bijan or Gibbs?"
    assert seen["raw_prompt"] == "Bijan or Gibbs?"


def test_falls_back_to_hardcoded_request(monkeypatch):
    seen = _run_main(monkeypatch, ["ffassistant"])

    assert seen["prompt"] == seen["REQUEST"]
    assert seen["raw_prompt"] == seen["REQUEST"]


def test_extract_and_validate_share_the_current_week(monkeypatch):
    seen = _run_main(monkeypatch, ["ffassistant", "Bijan?"])

    assert seen["extract_week"] == seen["validate_week"] == 9
