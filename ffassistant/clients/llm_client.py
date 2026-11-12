from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

from ffassistant.config import LLM_PROVIDER


@dataclass
class SystemBlock:
    text: str
    cache: bool = False  # a hint; providers without prompt caching ignore it


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int


@dataclass
class StructuredResponse[T: BaseModel]:
    parsed: T
    usage: TokenUsage


class LLMClient(ABC):
    @abstractmethod
    def generate_structured[T: BaseModel](
        self,
        model: str,
        system: list[SystemBlock],
        user_content: str,
        output_model: type[T],
        max_tokens: int,
    ) -> StructuredResponse[T]: ...


def get_llm_client() -> LLMClient:
    # Imported here because each provider module imports LLMClient from this one.
    if LLM_PROVIDER == "anthropic":
        from ffassistant.clients.anthropic_client import AnthropicClient

        return AnthropicClient()
    raise ValueError(f"unknown LLM_PROVIDER: {LLM_PROVIDER!r}")
