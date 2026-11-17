"""News rankers: index a corpus once, then rank candidate documents against any number of queries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import bm25s
import Stemmer


@dataclass
class RankDoc:
    """A document to rank: its id, searchable text, and publish time."""

    doc_id: str
    text: str
    published_at: datetime


def _ordered(scored: list[tuple[RankDoc, float]]) -> list[tuple[RankDoc, float]]:
    # Ties go to the newer document.
    return sorted(scored, key=lambda pair: (pair[1], pair[0].published_at), reverse=True)


class Ranker(ABC):
    """Built once over a corpus; rank() orders candidates for a query as (doc, score) pairs."""

    def __init__(self, corpus: list[RankDoc]):
        self.corpus = corpus

    @abstractmethod
    def rank(self, query: str, candidates: list[RankDoc]) -> list[tuple[RankDoc, float]]: ...


class RecencyRanker(Ranker):
    """Newest first; the score is the publish timestamp. Ignores the query and corpus."""

    def rank(self, query: str, candidates: list[RankDoc]) -> list[tuple[RankDoc, float]]:
        return _ordered([(doc, doc.published_at.timestamp()) for doc in candidates])


_STEMMER = Stemmer.Stemmer("english")


def _tokenize(texts: str | list[str], return_ids: bool = True):
    return bm25s.tokenize(
        texts, stopwords="en", stemmer=_STEMMER, return_ids=return_ids, show_progress=False
    )


class BM25Ranker(Ranker):
    """Stemmed BM25 indexed over the whole corpus; scores read for candidates, zeros dropped."""

    def __init__(self, corpus: list[RankDoc]):
        super().__init__(corpus)
        self._retriever = bm25s.BM25()
        if corpus:
            self._retriever.index(_tokenize([doc.text for doc in corpus]), show_progress=False)

    def rank(self, query: str, candidates: list[RankDoc]) -> list[tuple[RankDoc, float]]:
        if not candidates:
            return []
        query_tokens = _tokenize(query, return_ids=False)[0]
        scores = dict(
            zip((doc.doc_id for doc in self.corpus), self._retriever.get_scores(query_tokens))
        )
        return _ordered(
            [(doc, float(scores[doc.doc_id])) for doc in candidates if scores[doc.doc_id] > 0]
        )


RANKERS: dict[str, type[Ranker]] = {"recency": RecencyRanker, "bm25": BM25Ranker}
