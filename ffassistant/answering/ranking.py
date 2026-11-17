"""News rankers: order candidate documents for a query, returning (doc, score) in rank order."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import bm25s


@dataclass
class RankDoc:
    """A document to rank: its id, searchable text, and publish time."""

    doc_id: str
    text: str
    published_at: datetime


Ranker = Callable[[str, list[RankDoc], list[RankDoc]], list[tuple[RankDoc, float]]]


def _ordered(scored: list[tuple[RankDoc, float]]) -> list[tuple[RankDoc, float]]:
    # Ties go to the newer document.
    return sorted(scored, key=lambda pair: (pair[1], pair[0].published_at), reverse=True)


def rank_recency(
    query: str, candidates: list[RankDoc], corpus: list[RankDoc]
) -> list[tuple[RankDoc, float]]:
    """Newest first; the score is the publish timestamp. Ignores the query and corpus."""
    return _ordered([(doc, doc.published_at.timestamp()) for doc in candidates])


def rank_bm25(
    query: str, candidates: list[RankDoc], corpus: list[RankDoc]
) -> list[tuple[RankDoc, float]]:
    """BM25 over the whole corpus, scores read for the candidates; zero scores are dropped."""
    if not candidates:
        return []
    retriever = bm25s.BM25()
    retriever.index(
        bm25s.tokenize([doc.text for doc in corpus], stopwords="en", show_progress=False),
        show_progress=False,
    )
    query_tokens = bm25s.tokenize(query, stopwords="en", return_ids=False, show_progress=False)[0]
    scores = dict(zip((doc.doc_id for doc in corpus), retriever.get_scores(query_tokens)))
    return _ordered(
        [(doc, float(scores[doc.doc_id])) for doc in candidates if scores[doc.doc_id] > 0]
    )


RANKERS: dict[str, Ranker] = {"recency": rank_recency, "bm25": rank_bm25}
