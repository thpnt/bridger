from pathlib import Path

from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.discovery_tools import (
    DiscoveryToolExecutor,
    tool_call_request_from_llm_call,
    tool_result_to_llm_message,
)
from bridger.llm.models import LLMToolCall
from bridger.llm.providers.openai import _openai_strict_schema


def test_llm_adapters_keep_call_identity_and_result_status(tmp_path: Path) -> None:
    _, context = inherited_tool_repo.__wrapped__(tmp_path)
    request = tool_call_request_from_llm_call(
        LLMToolCall(
            id="call_1",
            name="list_files",
            arguments={"prefix": "src"},
        )
    )
    result = DiscoveryToolExecutor(context).execute(request)
    message = tool_result_to_llm_message(result)

    assert message.tool_call_id == "call_1"
    assert message.tool_name == "list_files"
    assert message.tool_failed is False
    assert message.tool_result["status"] == "completed"


def test_read_file_ranges_declares_typed_range_properties(tmp_path: Path) -> None:
    _, context = inherited_tool_repo.__wrapped__(tmp_path)
    definition = DiscoveryToolExecutor(context).registry.get("read_file_ranges")

    assert definition is not None
    schema = _openai_strict_schema(definition.to_llm_definition().input_schema)
    range_schema = schema["$defs"]["LineRangeInput"]

    assert schema["required"] == ["path", "ranges"]
    assert schema["properties"]["ranges"]["items"] == {"$ref": "#/$defs/LineRangeInput"}
    assert range_schema["properties"] == {
        "line_start": {"minimum": 1, "title": "Line Start", "type": "integer"},
        "line_end": {"minimum": 1, "title": "Line End", "type": "integer"},
    }
    assert range_schema["required"] == ["line_start", "line_end"]
    assert range_schema["additionalProperties"] is False
