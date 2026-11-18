"""Records the eval tools read and write: samples, run metadata, and judgments."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Side = Literal["a", "b"]
Outcome = Literal["a", "b", "tie"]


class EvalSample(BaseModel):
    """One player to retrieve news for, pinned to a season, week, and corpus snapshot."""

    season: int
    week: int
    as_of: str  # generation time (ISO 8601 UTC); news is cut off and frozen at it
    gsis_id: str  # unique within a samples file, so it keys every judgment
    full_name: str
    position: str


class RunMeta(BaseModel):
    """What a run directory compares, written once to its meta.json."""

    samples: str
    a_config: str
    b_config: str
    judge_model: str | None = None  # set for LLM-judged runs


class Judgment(BaseModel):
    """One blind judgment of a pair: each side's retrieved doc_ids and the winner.
    Identical sides (a == b) are recorded as a tie without being judged."""

    gsis_id: str
    cutoff: str
    a: list[str]  # doc_ids in retrieved order
    b: list[str]
    winner: Outcome

    @property
    def identical(self) -> bool:
        return self.a == self.b


class LLMJudgment(Judgment):
    """A pair judged in both orders: the agreed winner, or a tie with reason "inconsistent"."""

    reason: str | None = None  # None for identical pairs, which aren't sent


class AgreementJudgment(BaseModel):
    """A human judgment of an LLM-judged pair, beside the LLM's verdict (inconsistent as tie)."""

    gsis_id: str
    human: Outcome
    llm: Outcome
