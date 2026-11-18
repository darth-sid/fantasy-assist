from types import SimpleNamespace as NS
from typing import Literal

from pydantic import BaseModel

from ffassistant.clients.anthropic_client import AnthropicClient
from ffassistant.clients.llm_client import (
    LLMClient,
    QueryError,
    QueryRequest,
    StructuredResponse,
    SystemBlock,
)


class Verdict(BaseModel):
    choice: Literal["left", "right"]


def _request(text: str) -> QueryRequest:
    return QueryRequest(
        model="m", system=[SystemBlock("rubric", cache=True)], user_content=text,
        output_model=Verdict, max_tokens=100,
    )


class EchoClient(LLMClient):
    def query(self, request):
        if request.user_content == "boom":
            raise RuntimeError("down")
        return StructuredResponse(parsed=request.output_model(choice=request.user_content), usage=None)


def test_query_many_keeps_order_and_turns_failures_into_errors():
    results = EchoClient().query_many([_request("left"), _request("boom"), _request("right")], workers=3)

    assert [r.parsed.choice if isinstance(r, StructuredResponse) else r for r in results] == [
        "left", QueryError("RuntimeError: down"), "right",
    ]


def test_query_batch_defaults_to_query_many():
    assert EchoClient().query_batch([_request("left")])[0].parsed.choice == "left"


USAGE = NS(input_tokens=1, output_tokens=2, cache_creation_input_tokens=None, cache_read_input_tokens=3)


def _succeeded(text: str, stop_reason: str = "end_turn"):
    message = NS(content=[NS(type="text", text=text)], stop_reason=stop_reason, usage=USAGE)
    return NS(type="succeeded", message=message)


class FakeBatches:
    def __init__(self, results):
        self.results_by_id = results
        self.created = []
        self.polls = 0

    def create(self, requests):
        self.created.append(requests)
        return NS(id="batch-1")

    def retrieve(self, batch_id):
        self.polls += 1
        status = "ended" if self.polls > 1 else "in_progress"
        return NS(processing_status=status, request_counts=NS(processing=1, succeeded=0))

    def results(self, batch_id):
        return [NS(custom_id=cid, result=r) for cid, r in self.results_by_id.items()]


def _client(results) -> tuple[AnthropicClient, FakeBatches]:
    batches = FakeBatches(results)
    return AnthropicClient(sdk=NS(messages=NS(batches=batches)), poll_seconds=0), batches


def test_batch_maps_results_by_custom_id_and_reports_failures(tmp_path):
    client, batches = _client({
        "2": _succeeded('{"choice": "right"}'),
        "0": _succeeded('{"choice": "left"}'),
        "1": NS(type="errored", error=NS(type="overloaded_error")),
        "3": _succeeded('{"choice": "lef', stop_reason="max_tokens"),
    })

    results = client.query_batch([_request(str(i)) for i in range(5)], job_file=tmp_path / "job")

    assert results[0].parsed.choice == "left" and results[2].parsed.choice == "right"
    assert results[0].usage.cache_read_tokens == 3
    assert results[1] == QueryError("errored: overloaded_error")
    assert "max_tokens" in results[3].message
    assert results[4] == QueryError("no result returned")
    params = batches.created[0][0]["params"]
    assert params["output_config"]["format"]["schema"]["required"] == ["choice"]
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert not (tmp_path / "job").exists()  # cleared once results are in


def test_batch_resumes_from_job_file_without_resubmitting(tmp_path):
    client, batches = _client({"0": _succeeded('{"choice": "left"}')})
    job = tmp_path / "job"
    job.write_text("batch-0\n")

    client.query_batch([_request("x")], job_file=job)

    assert batches.created == []


def test_query_sends_the_request_through_messages_parse():
    seen = {}

    def parse(**kwargs):
        seen.update(kwargs)
        return NS(parsed_output=Verdict(choice="left"), stop_reason="end_turn", usage=USAGE)

    client = AnthropicClient(sdk=NS(messages=NS(parse=parse)))

    response = client.query(_request("pair text"))

    assert response.parsed.choice == "left"
    assert seen["output_format"] is Verdict
    assert seen["messages"] == [{"role": "user", "content": "pair text"}]
    assert (seen["model"], seen["max_tokens"]) == ("m", 100)


def test_query_without_parsed_output_raises():
    def parse(**kwargs):
        return NS(parsed_output=None, stop_reason="max_tokens", usage=USAGE)

    client = AnthropicClient(sdk=NS(messages=NS(parse=parse)))

    try:
        client.query(_request("x"))
    except ValueError as exc:
        assert "max_tokens" in str(exc)
    else:
        raise AssertionError("expected ValueError")
