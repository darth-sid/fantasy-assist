from __future__ import annotations

import anthropic
from pydantic import BaseModel

from ffassistant.clients.llm_client import LLMClient, StructuredResponse, SystemBlock, TokenUsage


class AnthropicClient(LLMClient):
    def generate_structured[T: BaseModel](
        self,
        model: str,
        system: list[SystemBlock],
        user_content: str,
        output_model: type[T],
        max_tokens: int,
    ) -> StructuredResponse[T]:
        response = anthropic.Anthropic().messages.parse(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=[_system_block(block) for block in system],
            messages=[{"role": "user", "content": user_content}],
            output_format=output_model,
        )
        usage = response.usage
        return StructuredResponse(
            parsed=response.parsed_output,
            usage=TokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
            ),
        )


def _system_block(block: SystemBlock) -> dict:
    rendered = {"type": "text", "text": block.text}
    if block.cache:
        rendered["cache_control"] = {"type": "ephemeral"}
    return rendered
