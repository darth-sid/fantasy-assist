from __future__ import annotations

import anthropic
from pydantic import BaseModel


def parse_structured[T: BaseModel](
    model: str,
    system: list[dict],
    user_content: str,
    output_model: type[T],
    max_tokens: int,
) -> T:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_format=output_model,
    )
    return response.parsed_output
