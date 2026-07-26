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
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
)
from bridger.llm.profiles import LLMProfile, RetryPolicy
from bridger.llm.providers.openai import OpenAILLMClient
from bridger.models.context_plan import ContextPlan


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


def context_plan_request(prompt: str) -> LLMRequest:
    return LLMRequest(
        operation=LLMOperation.CONTEXT_PLAN_GENERATION,
        messages=[
            LLMMessage.system("Return the requested Context Plan."),
            LLMMessage.user(prompt),
        ],
    )


def context_plan() -> ContextPlan:
    return ContextPlan.model_validate(
        {
            "generated_at": "2026-07-23T12:00:00Z",
            "repo": {"root_name": "fixture", "revision": "test"},
            "summary": {
                "repository_purpose": "Fixture application",
                "project_type": "Python application",
                "detected_stack": ["Python"],
                "main_runtime_flow": "The app module starts the fixture.",
                "confidence": 0.9,
            },
            "packages": [
                {
                    "package_id": "pkg.application",
                    "title": "Application",
                    "purpose": "Explain the application entrypoint.",
                    "priority": 1,
                    "topics": ["application-runtime"],
                    "ordered_items": [
                        {
                            "path": "src/app.py",
                            "line_start": 1,
                            "line_end": 2,
                            "role": "entrypoint",
                            "reason": "Contains application startup.",
                            "expected_use": "Trace the runtime flow.",
                        }
                    ],
                    "provenance": [
                        {
                            "source_type": "file_excerpt",
                            "path": "src/app.py",
                            "line_start": 1,
                            "line_end": 2,
                            "evidence_note": "Inspected entrypoint excerpt.",
                        }
                    ],
                    "confidence": 0.9,
                    "warnings": [],
                    "unknowns": [],
                }
            ],
            "intentionally_excluded": [],
            "global_warnings": [],
            "global_unknowns": [],
        }
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
    assert payload["input"][2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "read_file",
        "arguments": '{"path": "a.py"}',
    }
    assert payload["input"][3]["type"] == "function_call_output"
    assert payload["input"][3]["call_id"] == "call_1"
    assert json.loads(payload["input"][3]["output"])["ok"] is True
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read a safe file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    assert payload["metadata"] == {"workflow_id": "wf_1"}
    assert "secret_path" not in payload["metadata"]
    assert isinstance(response, LLMResponse)
    assert response.text == "hello"
    assert response.usage.input_tokens == 3
    assert response.usage.output_tokens == 5
    assert response.usage.total_tokens == 8
    assert response.usage.cached_input_tokens == 1
    assert response.usage.reasoning_tokens == 2
    assert response.model == "gpt-test-returned"
    assert response.response_id == "resp_1"
    assert response.provider_request_id == "req_1"
    assert response.latency_ms in {99, 100}
    assert isinstance(response.model_dump(), dict)


def test_openai_adapter_normalizes_optional_nested_tool_schema_for_strict_mode() -> (
    None
):
    tool = LLMToolDefinition(
        name="list_files",
        description="List files",
        input_schema={
            "$defs": {
                "Filters": {
                    "type": "object",
                    "properties": {
                        "extension": {
                            "type": ["string", "null"],
                            "default": None,
                        }
                    },
                }
            },
            "type": "object",
            "properties": {"filters": {"$ref": "#/$defs/Filters"}},
        },
    )
    fake = FakeOpenAI([text_response()])
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    run_generate(
        client,
        LLMRequest(
            operation=LLMOperation.REPO_DISCOVERY,
            messages=[LLMMessage.user("List files")],
            tools=[tool],
        ),
    )

    parameters = fake.responses.calls[0]["tools"][0]["parameters"]
    assert parameters["required"] == ["filters"]
    assert parameters["additionalProperties"] is False
    assert parameters["$defs"]["Filters"]["required"] == ["extension"]
    assert parameters["$defs"]["Filters"]["additionalProperties"] is False
    assert "default" not in parameters["$defs"]["Filters"]["properties"]["extension"]


def test_openai_adapter_omits_required_for_empty_tool_schema() -> None:
    tool = LLMToolDefinition(
        name="inspect_repo_discovery",
        description="Inspect repository discovery",
        input_schema={"type": "object", "properties": {}},
    )
    fake = FakeOpenAI([text_response()])
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    run_generate(
        client,
        LLMRequest(
            operation=LLMOperation.REPO_DISCOVERY,
            messages=[LLMMessage.user("Inspect the repository")],
            tools=[tool],
        ),
    )

    parameters = fake.responses.calls[0]["tools"][0]["parameters"]
    assert parameters["properties"] == {}
    assert "required" not in parameters
    assert parameters["additionalProperties"] is False


def test_openai_adapter_parses_tool_calls_and_rejects_malformed_arguments() -> None:
    response_payload = text_response(
        output=[
            {
                "type": "function_call",
                "call_id": "call_2",
                "name": "search_with_context",
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
                "name": "search_with_context",
                "arguments": "{bad",
            }
        ]
    )
    bad_client = OpenAILLMClient(openai_client=FakeOpenAI([bad]), profile=profile())
    with pytest.raises(LLMInvalidResponseError):
        run_generate(bad_client, request_with_tools())


def test_openai_adapter_preserves_multiple_ordered_tool_calls() -> None:
    response_payload = text_response(
        output=[
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "read_file",
                "arguments": '{"path":"src/a.py"}',
            },
            {
                "type": "function_call",
                "id": "fc_2",
                "call_id": "call_2",
                "name": "read_file",
                "arguments": '{"path":"src/b.py"}',
            },
        ]
    )
    client = OpenAILLMClient(
        openai_client=FakeOpenAI([response_payload]),
        profile=profile(),
    )

    response = run_generate(client, request_with_tools())

    assert [call.id for call in response.tool_calls] == ["call_1", "call_2"]
    assert [call.arguments for call in response.tool_calls] == [
        {"path": "src/a.py"},
        {"path": "src/b.py"},
    ]


@pytest.mark.parametrize(
    ("tool_call", "message"),
    [
        (
            {"type": "function_call", "name": "read_file", "arguments": "{}"},
            "stable call ID",
        ),
        (
            {
                "type": "function_call",
                "call_id": "call_1",
                "arguments": "{}",
            },
            "name",
        ),
    ],
)
def test_openai_adapter_rejects_tool_calls_without_required_fields(
    tool_call: dict[str, Any],
    message: str,
) -> None:
    client = OpenAILLMClient(
        openai_client=FakeOpenAI([text_response(output=[tool_call])]),
        profile=profile(),
    )

    with pytest.raises(LLMInvalidResponseError, match=message):
        run_generate(client, request_with_tools())


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
        clock=_clock(),
    )
    with pytest.raises(LLMStructuredOutputError) as invalid_json_error:
        run_generate(invalid_json, request_with_tools(), output_type=ExampleResult)
    assert invalid_json_error.value.invalid_output == "{bad"
    assert invalid_json_error.value.usage.total_tokens == 8
    assert invalid_json_error.value.latency_ms in {99, 100}

    invalid_schema = OpenAILLMClient(
        openai_client=FakeOpenAI([text_response(output_text='{"wrong":"ok"}')]),
        profile=profile(),
    )
    with pytest.raises(LLMStructuredOutputError) as invalid_schema_error:
        run_generate(invalid_schema, request_with_tools(), output_type=ExampleResult)
    assert invalid_schema_error.value.invalid_output == {"wrong": "ok"}

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
    with pytest.raises(LLMStructuredOutputError) as incomplete_error:
        run_generate(incomplete, request_with_tools(), output_type=ExampleResult)
    assert incomplete_error.value.usage.input_tokens == 3


def test_openai_adapter_uses_context_plan_schema_for_synthesis_and_repair() -> None:
    plan = context_plan()
    fake = FakeOpenAI(
        [
            text_response(output_text=plan.model_dump_json()),
            text_response(id="resp_2", output_text=plan.model_dump_json()),
        ]
    )
    client = OpenAILLMClient(openai_client=fake, profile=profile())

    synthesis = run_generate(
        client,
        context_plan_request("Synthesize the Context Plan."),
        output_type=ContextPlan,
    )
    repair = run_generate(
        client,
        context_plan_request("Repair the invalid Context Plan."),
        output_type=ContextPlan,
    )

    assert synthesis.structured_output == plan
    assert repair.structured_output == plan
    for payload in fake.responses.calls:
        assert "tools" not in payload
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["name"] == "ContextPlan"
        schema = payload["text"]["format"]["schema"]
        assert schema["required"] == list(schema["properties"])
        assert schema["additionalProperties"] is False
        assert "default" not in schema["properties"]["artifact"]


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

    rate_limit_client = OpenAILLMClient(
        openai_client=FakeOpenAI([_rate_limit(), _rate_limit(), _rate_limit()]),
        profile=profile(),
        sleep=_record_sleep([]),
    )
    with pytest.raises(LLMRateLimitError):
        run_generate(rate_limit_client, request_with_tools())

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

    invalid_request_client = OpenAILLMClient(
        openai_client=FakeOpenAI([_bad_request("invalid_request_error")]),
        profile=profile(),
    )
    with pytest.raises(LLMProviderError) as invalid_request_error:
        run_generate(invalid_request_client, request_with_tools())
    assert invalid_request_error.value.retryable is False


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


def test_openai_request_timeout_overrides_profile_timeout() -> None:
    fake = FakeOpenAI([text_response()])
    timeout_profile = profile().model_copy(update={"timeout_seconds": 30.0})
    client = OpenAILLMClient(openai_client=fake, profile=timeout_profile)
    request = request_with_tools().model_copy(update={"timeout_seconds": 5.0})

    run_generate(client, request)

    assert fake.responses.calls[0]["timeout"] == 5.0


@pytest.mark.parametrize(
    ("provider_response", "error_type"),
    [
        (text_response(status="failed", output=[]), LLMProviderError),
        (text_response(output=[], output_text=None), LLMInvalidResponseError),
    ],
)
def test_openai_adapter_normalizes_failed_or_empty_responses(
    provider_response: dict[str, Any],
    error_type: type[Exception],
) -> None:
    client = OpenAILLMClient(
        openai_client=FakeOpenAI([provider_response]),
        profile=profile(),
    )

    with pytest.raises(error_type):
        run_generate(client, request_with_tools())


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
