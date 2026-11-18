from __future__ import annotations

import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, ValidationError

from ffassistant.clients.llm_client import (
    LLMClient,
    QueryError,
    QueryRequest,
    StructuredResponse,
    SystemBlock,
    TokenUsage,
)

_POLL_SECONDS = 30


class AnthropicClient(LLMClient):
    """LLMClient over the Anthropic SDK (messages.parse, and Message Batches for query_batch)."""

    def __init__(self, sdk: anthropic.Anthropic | None = None, poll_seconds: float = _POLL_SECONDS):
        self._sdk = sdk
        self._poll_seconds = poll_seconds

    @property
    def sdk(self) -> anthropic.Anthropic:
        # Created on first use so constructing the client never needs credentials.
        if self._sdk is None:
            self._sdk = anthropic.Anthropic()
        return self._sdk

    def query[T: BaseModel](self, request: QueryRequest[T]) -> StructuredResponse[T]:
        response = self.sdk.messages.parse(
            **_message_params(request), output_format=request.output_model
        )
        if response.parsed_output is None:
            raise ValueError(f"no parsed output (stop_reason={response.stop_reason})")
        return StructuredResponse(parsed=response.parsed_output, usage=_usage(response.usage))

    def query_batch(
        self, requests: list[QueryRequest], job_file: Path | None = None
    ) -> list[StructuredResponse | QueryError]:
        if not requests:
            return []
        batch_id = job_file.read_text().strip() if job_file and job_file.exists() else None
        if batch_id is None:
            batch_id = self.sdk.messages.batches.create(
                requests=[_batch_request(str(i), request) for i, request in enumerate(requests)]
            ).id
            if job_file:
                job_file.write_text(batch_id)
            print(f"submitted batch {batch_id} ({len(requests)} requests)")
        else:
            print(f"resuming batch {batch_id}")

        while (batch := self.sdk.messages.batches.retrieve(batch_id)).processing_status != "ended":
            counts = batch.request_counts
            print(f"batch {batch_id}: {counts.processing} processing, {counts.succeeded} succeeded")
            time.sleep(self._poll_seconds)

        results: list[StructuredResponse | QueryError] = [
            QueryError("no result returned") for _ in requests
        ]
        for entry in self.sdk.messages.batches.results(batch_id):
            index = int(entry.custom_id)
            results[index] = _batch_result(entry.result, requests[index].output_model)
        if job_file:
            job_file.unlink(missing_ok=True)
        return results


def _batch_request(custom_id: str, request: QueryRequest) -> Request:
    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            **_message_params(request),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": anthropic.transform_schema(request.output_model),
                }
            },
        ),
    )


def _message_params(request: QueryRequest) -> dict:
    return dict(
        model=request.model,
        max_tokens=request.max_tokens,
        system=[_system_block(block) for block in request.system],
        messages=[{"role": "user", "content": request.user_content}],
    )


def _batch_result(result, output_model: type[BaseModel]) -> StructuredResponse | QueryError:
    if result.type != "succeeded":
        detail = f": {result.error.type}" if result.type == "errored" else ""
        return QueryError(f"{result.type}{detail}")
    message = result.message
    text = next((block.text for block in message.content if block.type == "text"), "")
    try:
        parsed = output_model.model_validate_json(text)
    except ValidationError as exc:
        return QueryError(f"unparseable output (stop_reason={message.stop_reason}): {exc}")
    return StructuredResponse(parsed=parsed, usage=_usage(message.usage))


def _usage(usage) -> TokenUsage:
    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_write_tokens=usage.cache_creation_input_tokens or 0,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
    )


def _system_block(block: SystemBlock) -> dict:
    rendered = {"type": "text", "text": block.text}
    if block.cache:
        rendered["cache_control"] = {"type": "ephemeral"}
    return rendered
