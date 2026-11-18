"""Provider-neutral LLM interface; stages call get_llm_client() and never a provider SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from tqdm import tqdm

from ffassistant.config import LLMConfig


@dataclass
class SystemBlock:
    """One system prompt block; cache marks it for prompt caching where supported."""

    text: str
    cache: bool = False  # a hint; providers without prompt caching ignore it


@dataclass
class TokenUsage:
    """Token counts for one call, including prompt-cache writes and reads."""

    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int


@dataclass
class StructuredResponse[T: BaseModel]:
    """The parsed output model plus the call's token usage."""

    parsed: T
    usage: TokenUsage


@dataclass
class QueryRequest[T: BaseModel]:
    """One structured-output call: model, system blocks, one user message, and the output schema."""

    model: str
    system: list[SystemBlock]
    user_content: str
    output_model: type[T]
    max_tokens: int


@dataclass
class QueryError:
    """Why one query in a batch produced no parsed output."""

    message: str


class LLMClient(ABC):
    """A provider that can return structured output for one system + user message."""

    @abstractmethod
    def query[T: BaseModel](self, request: QueryRequest[T]) -> StructuredResponse[T]:
        """Sends one request and returns the reply parsed into its output_model."""

    def query_many(
        self, requests: list[QueryRequest], workers: int = 8, progress: bool = False
    ) -> list[StructuredResponse | QueryError]:
        """Runs queries concurrently; results in request order, failures as QueryError.
        progress shows a bar that advances as each query finishes."""

        def run(request: QueryRequest) -> StructuredResponse | QueryError:
            try:
                return self.query(request)
            except Exception as exc:
                return QueryError(f"{type(exc).__name__}: {exc}")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run, request) for request in requests]
            for _ in tqdm(as_completed(futures), total=len(futures), disable=not progress):
                pass
        return [future.result() for future in futures]

    def query_batch(
        self, requests: list[QueryRequest], job_file: Path | None = None
    ) -> list[StructuredResponse | QueryError]:
        """Like query_many, via the provider's batch API where it has one; blocks until done.
        A provider that submits a job records its id in job_file and resumes it on rerun."""
        return self.query_many(requests)


def get_llm_client(llm: LLMConfig) -> LLMClient:
    """Returns the client for llm.provider."""
    # Imported here because each provider module imports LLMClient from this one.
    if llm.provider == "anthropic":
        from ffassistant.clients.anthropic_client import AnthropicClient

        return AnthropicClient()
    raise ValueError(f"unknown LLM provider: {llm.provider!r}")
