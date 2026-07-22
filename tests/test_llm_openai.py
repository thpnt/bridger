import asyncio
import json
import logging
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel

from bridger.llm.errors import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMContextLimitError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMQuotaError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMRequest,
    LLMToolCall,
    LLMToolDefinition,
)
from bridger.llm.profiles import LLMProfile, RetryPolicy
from bridger.llm.providers.openai import OpenAILLMClient


class ExampleResult(BaseModel):
    answer: str


class FakeResponses:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeOpenAI:
    def __init__(self, outcomes: list[Any]) -> None:
        self.responses = FakeResponses(outcomes)


def profile() -> LLMProfile:
    return LLMProfile(
        name="balanced",
        provider="openai",
        model="gpt-test",
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
        ),
    )


def request_with_tools() -> LLMRequest:
    call = LLMToolCall(id="call_1", name="read_file", arguments={"path": "a.py"})
    return LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[
            LLMMessage.system("System prompt SECRET"),
            LLMMessage.user("User prompt SOURCE"),
            LLMMessage.assistant_tool_calls([call]),
            LLMMessage.tool_result_message(
                tool_call_id="call_1",
                tool_name="read_file",
                result={"content": "tool result SOURCE"},
            ),
        ],
        tools=[
            LLMToolDefinition(
                name="read_file",
                description="Read a safe file",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
            )
        ],
        tool_choice="auto",
        metadata={"workflow_id": "wf_1", "secret_path": "/private/repo/file.py"},
    )


def text_response(**overrides: Any) -> dict[str, Any]:
    response = {
        "id": "resp_1",
        "_request_id": "req_1",
        "status": "completed",
        "model": "gpt-test-returned",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "hello"}],
            }
        ],
        "usage": {
            "input_tokens": 3,
            "output_tokens": 5,
            "total_tokens": 8,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }
    response.update(overrides)
    return response


def run_generate(client: OpenAILLMClient, request: LLMRequest, **kwargs: Any) -> Any:
    return asyncio.run(client.generate(request, **kwargs))


def test_openai_adapter_translates_messages_tools_privacy_and_normalizes_text() -> None:
    fake = FakeOpenAI([text_response()])
    client = OpenAILLMClient(openai_client=fake, profile=profile(), clock=_clock())

    response = run_generate(client, request_with_tools())
    payload = fake.responses.calls[0]

    assert payload["store"] is False
    assert payload["model"] == "gpt-test"
    assert payload["input"][0] == {"role": "system", "content": "System prompt SECRET"}
    assert payload["input"][2]["type"] == "function_call"
    assert payload["input"][2]["call_id"] == "call_1"
    assert payload["input"][3]["type"] == "function_call_output"
    assert json.loads(payload["input"][3]["output"])["ok"] is True
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["strict"] is True
    assert payload["metadata"] == {"workflow_id": "wf_1"}
    assert "secret_path" not in payload["metadata"]
    assert response.text == "hello"
    assert response.usage.cached_input_tokens == 1
    assert response.usage.reasoning_tokens == 2
    assert response.model == "gpt-test-returned"
    assert response.response_id == "resp_1"
    assert response.provider_request_id == "req_1"
    assert response.latency_ms in {99, 100}


def test_openai_adapter_parses_tool_calls_and_rejects_malformed_arguments() -> None:
    response_payload = text_response(
        output=[
            {
                "type": "function_call",
                "call_id": "call_2",
                "name": "search_paths",
                "arguments": '{"query":"main"}',
            }
        ]
    )
    fake = FakeOpenAI([response_payload])
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    response = run_generate(client, request_with_tools())

    assert response.tool_calls[0].id == "call_2"
    assert response.tool_calls[0].arguments == {"query": "main"}
    assert response.text is None

    bad = text_response(
        output=[
            {
                "type": "function_call",
                "call_id": "call_3",
                "name": "search_paths",
                "arguments": "{bad",
            }
        ]
    )
    bad_client = OpenAILLMClient(openai_client=FakeOpenAI([bad]), profile=profile())
    with pytest.raises(LLMInvalidResponseError):
        run_generate(bad_client, request_with_tools())


def test_openai_adapter_validates_structured_output() -> None:
    fake = FakeOpenAI([text_response(output_text='{"answer":"ok"}')])
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    response = run_generate(client, request_with_tools(), output_type=ExampleResult)

    assert response.structured_output == ExampleResult(answer="ok")
    assert response.text is None
    payload = fake.responses.calls[0]
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["name"] == "ExampleResult"

    invalid_json = OpenAILLMClient(
        openai_client=FakeOpenAI([text_response(output_text="{bad")]),
        profile=profile(),
    )
    with pytest.raises(LLMStructuredOutputError):
        run_generate(invalid_json, request_with_tools(), output_type=ExampleResult)

    invalid_schema = OpenAILLMClient(
        openai_client=FakeOpenAI([text_response(output_text='{"wrong":"ok"}')]),
        profile=profile(),
    )
    with pytest.raises(LLMStructuredOutputError):
        run_generate(invalid_schema, request_with_tools(), output_type=ExampleResult)

    incomplete = OpenAILLMClient(
        openai_client=FakeOpenAI(
            [
                text_response(
                    status="incomplete",
                    incomplete_details={"reason": "max_output_tokens"},
                )
            ]
        ),
        profile=profile(),
    )
    with pytest.raises(LLMStructuredOutputError):
        run_generate(incomplete, request_with_tools(), output_type=ExampleResult)


def test_openai_adapter_maps_errors_and_retries_without_real_sleep() -> None:
    sleeps: list[float] = []
    transient = _rate_limit()
    fake = FakeOpenAI([transient, text_response()])
    client = OpenAILLMClient(
        openai_client=fake,
        profile=profile(),
        sleep=_record_sleep(sleeps),
    )

    response = run_generate(client, request_with_tools())

    assert response.retry_count == 1
    assert len(fake.responses.calls) == 2
    assert sleeps == [0.01]

    auth_client = OpenAILLMClient(
        openai_client=FakeOpenAI([_auth_error()]),
        profile=profile(),
        sleep=_record_sleep([]),
    )
    with pytest.raises(LLMAuthenticationError):
        run_generate(auth_client, request_with_tools())

    quota_client = OpenAILLMClient(
        openai_client=FakeOpenAI([_rate_limit(code="insufficient_quota")]),
        profile=profile(),
    )
    with pytest.raises(LLMQuotaError):
        run_generate(quota_client, request_with_tools())

    timeout_client = OpenAILLMClient(
        openai_client=FakeOpenAI(
            [
                openai.APITimeoutError(request=_http_request()),
                openai.APITimeoutError(request=_http_request()),
                openai.APITimeoutError(request=_http_request()),
            ]
        ),
        profile=profile(),
    )
    with pytest.raises(LLMTimeoutError):
        run_generate(timeout_client, request_with_tools())

    connection_client = OpenAILLMClient(
        openai_client=FakeOpenAI(
            [
                openai.APIConnectionError(request=_http_request()),
                openai.APIConnectionError(request=_http_request()),
                openai.APIConnectionError(request=_http_request()),
            ]
        ),
        profile=profile(),
    )
    with pytest.raises(LLMConnectionError):
        run_generate(connection_client, request_with_tools())

    context_client = OpenAILLMClient(
        openai_client=FakeOpenAI([_bad_request("context_length_exceeded")]),
        profile=profile(),
    )
    with pytest.raises(LLMContextLimitError):
        run_generate(context_client, request_with_tools())


def test_openai_retry_exhaustion_returns_final_normalized_error() -> None:
    fake = FakeOpenAI([_server_error(), _server_error(), _server_error()])
    client = OpenAILLMClient(
        openai_client=fake,
        profile=profile(),
        sleep=_record_sleep([]),
    )

    with pytest.raises(LLMProviderError) as error:
        run_generate(client, request_with_tools())

    assert error.value.retryable is True
    assert len(fake.responses.calls) == 3


def test_openai_logging_excludes_prompts_keys_and_tool_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="bridger.llm.providers.openai")
    fake = FakeOpenAI([text_response()])
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    run_generate(client, request_with_tools())
    logged = caplog.text

    assert "llm.generate.success" in logged
    assert "SOURCE" not in logged
    assert "SECRET" not in logged
    assert "sk-" not in logged


def _http_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/responses")


def _http_response(
    status_code: int, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status_code, request=_http_request(), headers=headers)


def _auth_error() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "auth failed",
        response=_http_response(401),
        body={"error": {"code": "invalid_api_key"}},
    )


def _rate_limit(code: str = "rate_limit_exceeded") -> openai.RateLimitError:
    return openai.RateLimitError(
        "rate limited",
        response=_http_response(429),
        body={"error": {"code": code}},
    )


def _bad_request(code: str) -> openai.BadRequestError:
    return openai.BadRequestError(
        "bad request",
        response=_http_response(400),
        body={"error": {"code": code}},
    )


def _server_error() -> openai.InternalServerError:
    return openai.InternalServerError(
        "server failed",
        response=_http_response(500),
        body={"error": {"code": "server_error"}},
    )


def _record_sleep(sleeps: list[float]) -> Any:
    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return sleep


def _clock() -> Any:
    values = iter([10.0, 10.1])

    def clock() -> float:
        return next(values)

    return clock
