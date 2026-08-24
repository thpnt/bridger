"""Bounded projections used by the memory-harness trace."""

from __future__ import annotations

import hashlib

from bridger.llm.models import (
    LLMCompactionRequest,
    LLMMessage,
    LLMReasoningConfig,
    LLMRequest,
    LLMToolCall,
    LLMToolDefinition,
    LLMToolResult,
    LLMUsage,
)
from bridger.memory.runtime.trace import (
    bounded_error_message,
    model_request_trace_context,
    project_tool_arguments,
    summarize_tool_result,
)


def test_tool_arguments_preserve_structure_but_omit_large_free_form_values() -> None:
    source = "source-content-" * 100
    call = LLMToolCall(
        id="call-1",
        name="write_target_artifact",
        arguments={
            "path": "architecture.md",
            "expected_revision": 2,
            "content": source,
            "tags": ["architecture", "runtime"],
        },
    )

    projected = project_tool_arguments(call)

    assert projected["arguments"]["path"] == "architecture.md"
    assert projected["arguments"]["expected_revision"] == 2
    assert projected["arguments"]["content"] == {
        "_omitted": "string",
        "chars": len(source),
        "bytes": len(source.encode()),
        "sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    assert source not in str(projected)


def test_malformed_arguments_are_tightly_bounded_and_digestible() -> None:
    raw = "{" + "x" * 10_000
    call = LLMToolCall(
        id="call-2",
        name="read_source_range",
        raw_arguments=raw,
        argument_error="invalid_json",
    )

    projected = project_tool_arguments(call)

    assert projected["argument_error"] == "invalid_json"
    assert len(projected["raw_arguments_preview"]) == 2_048
    assert projected["raw_arguments_bytes"] == len(raw.encode())
    assert projected["raw_arguments_digest"] == hashlib.sha256(raw.encode()).hexdigest()


def test_tool_result_summary_contains_sizes_tokens_shape_and_stable_ids_only() -> None:
    source = "def hidden_source(): pass"
    raw = LLMToolResult(
        call_id="call-3",
        name="inspect_file",
        output={
            "path": "src/bridger/runtime.py",
            "node_id": "node-1",
            "symbol_ids": ["symbol-1", "symbol-2"],
            "content": source,
        },
    )
    delivered = raw.model_copy(
        update={
            "output": {
                "path": "src/bridger/runtime.py",
                "node_id": "node-1",
                "truncated": True,
            }
        }
    )

    summary = summarize_tool_result(raw, delivered, lambda value: len(value))

    assert summary["raw_bytes"] > summary["delivered_bytes"]
    assert summary["token_estimate"] > 0
    assert summary["shape"] == "object"
    assert summary["item_count"] is None
    assert summary["truncated"] is True
    assert summary["identifiers"] == {
        "paths": ["src/bridger/runtime.py"],
        "node_ids": ["node-1"],
    }
    assert source not in str(summary)


def test_model_request_trace_context_exposes_reasoning_cache_and_request_shape() -> (
    None
):
    request = LLMRequest(
        operation="memory_agent_worker",
        profile="worker-v1",
        messages=[LLMMessage.user("tool result")],
        instructions="stable instructions",
        continuation_ref="response-1",
        prompt_cache={
            "key": "cache-key",
            "instruction_breakpoints": (8, 19),
        },
        tools=[
            LLMToolDefinition(
                name="inspect_file",
                description="Inspect one file.",
                input_schema={"type": "object", "properties": {}},
            )
        ],
        reasoning=LLMReasoningConfig(effort="low", context="all_turns"),
    )

    context = model_request_trace_context(
        request,
        local_request_input_tokens=123,
        count_tokens=len,
        canonical_base_tokens=40,
        execution_overlay_tokens=12,
        pending_tool_result_tokens=7,
        cycle_id="cycle-1",
        cycle_turn=3,
    )

    assert context["llm_operation"] == "memory_agent_worker"
    assert context["call_kind"] == "generate"
    assert context["reasoning_effort"] == "low"
    assert context["reasoning_context"] == "all_turns"
    assert context["cycle_id"] == "cycle-1"
    assert context["cycle_turn"] == 3
    assert context["request_shape"] == {
        "local_request_input_tokens": 123,
        "canonical_base_tokens": 40,
        "execution_overlay_tokens": 12,
        "message_tokens": 133,
        "tool_definition_tokens": 122,
        "continuation_present": True,
        "compacted_context_present": False,
        "prompt_cache_key": "cache-key",
        "prompt_cache_breakpoint_count": 2,
        "pending_tool_result_tokens": 7,
    }


def test_provider_usage_projection_keeps_reasoning_tokens_diagnostic() -> None:
    usage = LLMUsage(
        input_tokens=10,
        cached_input_tokens=4,
        cache_write_tokens=2,
        output_tokens=5,
        reasoning_tokens=3,
        total_tokens=15,
    )

    assert usage.reasoning_tokens == 3


def test_compaction_request_trace_is_distinguished_from_generation() -> None:
    request = LLMCompactionRequest(
        operation="memory_agent_worker",
        profile="worker-v1",
        instructions="stable instructions",
        continuation_ref="response-1",
    )

    context = model_request_trace_context(
        request,
        local_request_input_tokens=44,
        count_tokens=len,
        call_kind="compact",
        cycle_id="cycle-1",
        cycle_turn=2,
    )

    assert context["call_kind"] == "compact"
    assert context["cycle_id"] == "cycle-1"
    assert context["cycle_turn"] == 2
    assert context["reasoning_effort"] is None
    assert context["request_shape"]["continuation_present"] is True


def test_error_projection_keeps_exact_prefix_and_original_size() -> None:
    message = "tool failed: " + ("x" * 10_000)

    projected = bounded_error_message(message)

    assert projected["error_message"] == message[:2_048]
    assert projected["error_message_truncated"] is True
    assert projected["error_message_original_chars"] == len(message)
    assert projected["error_message_original_bytes"] == len(message.encode())
