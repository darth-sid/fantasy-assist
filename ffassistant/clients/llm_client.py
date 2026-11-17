"""Provider-neutral LLM interface; stages call get_llm_client() and never a provider SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

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


class LLMClient(ABC):
    """A provider that can return structured output for one system + user message."""

    @abstractmethod
    def generate_structured[T: BaseModel](
        self,
        model: str,
        system: list[SystemBlock],
        user_content: str,
        output_model: type[T],
        max_tokens: int,
    ) -> StructuredResponse[T]:
        """Sends one user message and returns the reply parsed into output_model."""


def get_llm_client(llm: LLMConfig) -> LLMClient:
    """Returns the client for llm.provider."""
    # Imported here because each provider module imports LLMClient from this one.
    if llm.provider == "anthropic":
        from ffassistant.clients.anthropic_client import AnthropicClient

        return AnthropicClient()
    raise ValueError(f"unknown LLM provider: {llm.provider!r}")
