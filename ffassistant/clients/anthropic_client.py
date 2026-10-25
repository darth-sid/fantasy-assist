from __future__ import annotations

from dataclasses import dataclass

import anthropic
from anthropic.types import Usage
from pydantic import BaseModel


@dataclass
class StructuredResponse[T: BaseModel]:
    parsed: T
    usage: Usage


def parse_structured[T: BaseModel](
    model: str,
    system: list[dict],
    user_content: str,
    output_model: type[T],
    max_tokens: int,
) -> StructuredResponse[T]:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_format=output_model,
    )
    return StructuredResponse(parsed=response.parsed_output, usage=response.usage)
