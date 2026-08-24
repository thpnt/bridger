"""Small bounded projections for the memory-harness event trace."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import orjson

from bridger.contracts.memory.hydration import WorkerCycleFocus
from bridger.llm.models import (
    LLMCompactionRequest,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolResult,
    LLMUsage,
)

TRACE_STRING_LIMIT = 512
TRACE_ERROR_LIMIT = 2_048
TRACE_ARGUMENT_PREVIEW_LIMIT = 2_048
TRACE_LIST_LIMIT = 16
TRACE_IDENTIFIER_LIMIT = 16

_FREE_FORM_ARGUMENT_KEYS = frozenset(
    {"content", "replacement", "working_summary", "resolution_note"}
)
_IDENTIFIER_KEYS: dict[str, str] = {
    "node_id": "node_ids",
    "node_ids": "node_ids",
    "community_id": "community_ids",
    "community_ids": "community_ids",
    "symbol_id": "symbol_ids",
    "symbol_ids": "symbol_ids",
    "path": "paths",
    "paths": "paths",
    "relative_path": "paths",
    "relative_paths": "paths",
    "artifact_id": "artifact_ids",
    "artifact_ids": "artifact_ids",
    "evidence_id": "evidence_ids",
    "evidence_ids": "evidence_ids",
    "question_id": "question_ids",
    "question_ids": "question_ids",
}


def bounded_trace_string(
    value: str, *, limit: int = TRACE_STRING_LIMIT
) -> dict[str, Any] | str:
    """Keep short diagnostic text exact and digest longer text."""
    if len(value) <= limit:
        return value
    encoded = value.encode("utf-8")
    return {
        "_omitted": "string",
        "chars": len(value),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "preview": value[: min(128, limit)],
    }


def bounded_error_message(message: str) -> dict[str, Any]:
    """Return one bounded tool/provider error projection."""
    encoded = message.encode("utf-8")
    bounded = message[:TRACE_ERROR_LIMIT]
    return {
        "error_message": bounded,
        "error_message_truncated": len(bounded) != len(message),
        "error_message_original_chars": len(message),
        "error_message_original_bytes": len(encoded),
    }


def project_tool_arguments(call: LLMToolCall) -> dict[str, Any]:
    """Project one tool call's arguments without copying large free-form data."""
    if call.has_malformed_arguments:
        raw = "" if call.raw_arguments is None else str(call.raw_arguments)
        encoded = raw.encode("utf-8")
        preview = raw[:TRACE_ARGUMENT_PREVIEW_LIMIT]
        return {
            "argument_error": call.argument_error,
            "raw_arguments_preview": preview,
            "raw_arguments_bytes": len(encoded),
            "raw_arguments_digest": hashlib.sha256(encoded).hexdigest(),
            "raw_arguments_truncated": len(preview) != len(raw),
        }
    arguments = call.arguments or {}
    return {
        "arguments": _project_value(arguments),
        "argument_bytes": len(orjson.dumps(arguments)),
    }


def summarize_tool_result(
    raw_result: LLMToolResult,
    delivered_result: LLMToolResult,
    count_tokens: Callable[[str], int],
) -> dict[str, Any]:
    """Summarize raw and model-delivered tool results without retaining output."""
    raw_bytes = len(orjson.dumps(raw_result.model_dump(mode="json")))
    delivered_bytes = len(orjson.dumps(delivered_result.model_dump(mode="json")))
    output = delivered_result.output if delivered_result.error is None else None
    if output is None:
        shape = "null"
        item_count = None
    elif isinstance(output, dict):
        shape = "object"
        item_count = None
    elif isinstance(output, list):
        shape = "list"
        item_count = len(output)
    else:
        shape = "scalar"
        item_count = None
    return {
        "raw_bytes": raw_bytes,
        "delivered_bytes": delivered_bytes,
        "token_estimate": count_tokens(
            orjson.dumps(
                delivered_result.as_message().model_dump(mode="json"),
                option=orjson.OPT_SORT_KEYS,
            ).decode()
        ),
        "truncated": raw_bytes != delivered_bytes or _output_is_truncated(output),
        "shape": shape,
        "item_count": item_count,
        "identifiers": _identifiers(output),
    }


def model_request_trace_context(
    request: LLMRequest | LLMCompactionRequest,
    *,
    local_request_input_tokens: int,
    count_tokens: Callable[[str], int],
    canonical_base_tokens: int = 0,
    execution_overlay_tokens: int = 0,
    pending_tool_result_tokens: int | None = None,
    cycle_id: str | None = None,
    cycle_turn: int | None = None,
    call_kind: str = "generate",
) -> dict[str, Any]:
    """Build the common bounded request metadata carried by model attempts."""
    messages = request.messages
    tool_definitions = getattr(request, "tools", [])
    request_shape: dict[str, Any] = {
        "local_request_input_tokens": local_request_input_tokens,
        "canonical_base_tokens": canonical_base_tokens,
        "execution_overlay_tokens": execution_overlay_tokens,
        "message_tokens": count_tokens(
            orjson.dumps(
                [message.model_dump(mode="json") for message in messages],
                option=orjson.OPT_SORT_KEYS,
            ).decode()
        ),
        "tool_definition_tokens": count_tokens(
            orjson.dumps(
                [tool.model_dump(mode="json") for tool in tool_definitions],
                option=orjson.OPT_SORT_KEYS,
            ).decode()
        ),
        "continuation_present": request.continuation_ref is not None,
        "compacted_context_present": getattr(request, "compacted_context", None)
        is not None,
        "prompt_cache_key": (
            request.prompt_cache.key
            if isinstance(request, LLMRequest) and request.prompt_cache is not None
            else None
        ),
        "prompt_cache_breakpoint_count": (
            len(request.prompt_cache.instruction_breakpoints)
            if isinstance(request, LLMRequest) and request.prompt_cache is not None
            else 0
        ),
    }
    if pending_tool_result_tokens is not None:
        request_shape["pending_tool_result_tokens"] = pending_tool_result_tokens
    context: dict[str, Any] = {
        "llm_operation": request.operation.value,
        "call_kind": call_kind,
        "profile": request.profile,
        "reasoning_effort": (
            request.reasoning.effort if getattr(request, "reasoning", None) else None
        ),
        "reasoning_context": (
            request.reasoning.context if getattr(request, "reasoning", None) else None
        ),
        "request_shape": request_shape,
    }
    if cycle_id is not None:
        context["cycle_id"] = cycle_id
    if cycle_turn is not None:
        context["cycle_turn"] = cycle_turn
    return context


def provider_usage_payload(usage: LLMUsage) -> dict[str, int | None]:
    """Expose provider usage, including reasoning tokens, as diagnostics."""
    return usage.model_dump(mode="json")


def model_response_trace_payload(response: LLMResponse[Any]) -> dict[str, Any]:
    """Project provider response metadata without model text or reasoning."""
    return {
        "provider": response.provider,
        "model": response.model,
        "response_id": response.response_id,
        "provider_request_id": response.provider_request_id,
        "latency_ms": response.latency_ms,
        "retry_count": response.retry_count,
        "provider_attempt": response.retry_count + 1,
        "finish_reason": response.finish_reason,
        "tool_call_count": len(response.tool_calls),
        "tool_names": [call.name for call in response.tool_calls[:TRACE_LIST_LIMIT]],
        "provider_usage": provider_usage_payload(response.usage),
    }


def model_error_trace_payload(error: BaseException) -> dict[str, Any]:
    """Project safe normalized provider/runtime error metadata."""
    payload: dict[str, Any] = {}
    provider = getattr(error, "provider", None)
    model = getattr(error, "model", None)
    if provider is not None:
        payload["provider"] = provider
    if model is not None:
        payload["model"] = model
    usage = getattr(error, "usage", None)
    if isinstance(usage, LLMUsage):
        payload["provider_usage"] = provider_usage_payload(usage)
    payload.update(bounded_error_message(str(error) or type(error).__name__))
    return payload


def focus_payload(focus: WorkerCycleFocus) -> dict[str, Any]:
    """Serialize deterministic cycle focus in the trace's stable shape."""
    return focus.model_dump(mode="json")


def _project_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, str):
        if key in _FREE_FORM_ARGUMENT_KEYS and len(value) > 128:
            return _string_metadata(value)
        return bounded_trace_string(value)
    if isinstance(value, dict):
        return {
            str(name): _project_value(item, key=str(name))
            for name, item in value.items()
        }
    if isinstance(value, list):
        projected = [_project_value(item, key=key) for item in value[:TRACE_LIST_LIMIT]]
        if len(value) > TRACE_LIST_LIMIT:
            projected.append({"_omitted": "array_items", "count": len(value)})
        return projected
    return value


def _string_metadata(value: str) -> dict[str, Any]:
    encoded = value.encode("utf-8")
    return {
        "_omitted": "string",
        "chars": len(value),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _output_is_truncated(output: Any) -> bool:
    return isinstance(output, dict) and output.get("truncated") is True


def _identifiers(value: Any) -> dict[str, list[Any]]:
    found: dict[str, list[Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                family = _IDENTIFIER_KEYS.get(str(key))
                if family is not None:
                    values = child if isinstance(child, list) else [child]
                    for identifier in values:
                        if isinstance(identifier, (str, int, float, bool)):
                            bucket = found.setdefault(family, [])
                            if (
                                identifier not in bucket
                                and len(bucket) < TRACE_IDENTIFIER_LIMIT
                            ):
                                bucket.append(identifier)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


__all__ = [
    "bounded_error_message",
    "bounded_trace_string",
    "focus_payload",
    "model_error_trace_payload",
    "model_request_trace_context",
    "model_response_trace_payload",
    "project_tool_arguments",
    "provider_usage_payload",
    "summarize_tool_result",
]
