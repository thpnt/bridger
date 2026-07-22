import asyncio
import json

import pytest
from pydantic import BaseModel, ValidationError

from bridger.llm.errors import LLMConfigurationError, LLMProviderError
from bridger.llm.factory import create_llm_client
from bridger.llm.models import (
    LLMMessage,
    LLMOperation,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    LLMUsage,
)
from bridger.llm.profiles import resolve_llm_profile
from bridger.llm.testing import DummyLLMClient, DummyLLMExhaustedError
from bridger.project import ProjectConfig


class ExampleResult(BaseModel):
    answer: str


def valid_request() -> LLMRequest:
    return LLMRequest(
        operation=LLMOperation.REPO_DISCOVERY,
        messages=[
            LLMMessage.system("Investigate repositories."),
            LLMMessage.user("Find entrypoints."),
        ],
    )


def test_request_models_accept_valid_text_conversations() -> None:
    request = valid_request()

    assert request.operation == LLMOperation.REPO_DISCOVERY
    assert request.messages[0].role == "system"
    assert request.messages[1].content == "Find entrypoints."


def test_invalid_message_tool_combinations_are_rejected() -> None:
    tool_call = LLMToolCall(id="call_1", name="read_file", arguments={"path": "x.py"})

    with pytest.raises(ValidationError):
        LLMMessage(role="user", content="hello", tool_calls=[tool_call])

    with pytest.raises(ValidationError):
        LLMMessage(role="assistant", content="hello", tool_calls=[tool_call])

    with pytest.raises(ValidationError):
        LLMMessage(role="tool", tool_name="read_file", tool_result={})


def test_tool_definitions_validate_schema_and_names() -> None:
    tool = LLMToolDefinition(
        name="read_file",
        description="Read a safe file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )

    assert tool.strict is True

    with pytest.raises(ValidationError):
        LLMToolDefinition(
            name="bad name",
            description="Bad",
            input_schema={"type": "object"},
        )

    with pytest.raises(ValidationError):
        LLMToolDefinition(
            name="bad_schema",
            description="Bad",
            input_schema={"type": "array"},
        )


def test_tool_results_preserve_call_ids() -> None:
    message = LLMMessage.tool_result_message(
        tool_call_id="call_1",
        tool_name="read_file",
        result={"ok": True, "content": "hidden"},
    )

    assert message.tool_call_id == "call_1"
    assert message.tool_name == "read_file"
    assert message.tool_failed is False


def test_response_invariants_and_usage_optional_fields() -> None:
    with pytest.raises(ValidationError):
        LLMResponse(provider="openai", model="test")

    response = LLMResponse(
        text="ok",
        provider="openai",
        model="test",
        usage=LLMUsage(input_tokens=1),
    )

    assert response.usage.input_tokens == 1
    assert response.usage.output_tokens is None


def test_profiles_and_factory_validate_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BRIDGER_OPENAI_MODEL", "gpt-test")
    profile = resolve_llm_profile()
    assert profile.name == "balanced"
    assert profile.model == "gpt-test"

    monkeypatch.delenv("BRIDGER_OPENAI_MODEL")
    with pytest.raises(LLMConfigurationError):
        resolve_llm_profile()

    monkeypatch.setenv("BRIDGER_OPENAI_MODEL", "gpt-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigurationError):
        create_llm_client()

    with pytest.raises(LLMConfigurationError):
        resolve_llm_profile("quality")


def test_project_config_keeps_llm_optional_and_never_stores_credentials() -> None:
    config = ProjectConfig.model_validate_json(
        json.dumps(
            {
                "schema_version": "1",
                "project_name": "demo",
                "project_mode": "existing",
                "created_at": "2026-07-21T00:00:00Z",
                "updated_at": "2026-07-21T00:00:00Z",
            }
        )
    )

    dumped = config.model_dump(mode="json")
    assert dumped["llm"]["default_profile"] == "balanced"
    assert "OPENAI_API_KEY" not in json.dumps(dumped)


def test_dummy_client_returns_scripted_outcomes_and_records_requests() -> None:
    tool_call = LLMToolCall(id="call_1", name="read_file", arguments={"path": "x.py"})
    client = DummyLLMClient(
        outcomes=[
            LLMResponse(text="first", provider="dummy", model="scripted"),
            LLMResponse(tool_calls=[tool_call], provider="dummy", model="scripted"),
            LLMResponse(
                structured_output=ExampleResult(answer="done"),
                provider="dummy",
                model="scripted",
            ),
            LLMProviderError("boom"),
        ]
    )
    request = valid_request()

    first = asyncio.run(client.generate(request))
    second = asyncio.run(client.generate(request))
    third = asyncio.run(client.generate(request, output_type=ExampleResult))

    assert first.text == "first"
    assert second.tool_calls == [tool_call]
    assert third.structured_output == ExampleResult(answer="done")
    assert client.requests == [request, request, request]
    with pytest.raises(LLMProviderError):
        asyncio.run(client.generate(request))
    with pytest.raises(DummyLLMExhaustedError):
        asyncio.run(client.generate(request))
