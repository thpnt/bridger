import asyncio
import copy
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

import openai
from pydantic import BaseModel, ValidationError

from llm.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMContextLimitError,
    LLMError,
    LLMInvalidResponseError,
    LLMProviderError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from llm.models import (
    LLMCompactedContext,
    LLMCompactionRequest,
    LLMCompactionResult,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    LLMUsage,
    dump_json_value,
)
from llm.profiles import LLMProfile
from llm.retry import SleepCallable, run_with_retries

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)

logger = logging.getLogger(__name__)
FORWARDED_METADATA_KEYS = {"workflow_id", "run_id"}


class OpenAILLMClient:
    """OpenAI Responses API implementation of the Bridger LLMClient."""

    def __init__(
        self,
        *,
        openai_client: Any,
        profile: LLMProfile,
        sleep: SleepCallable | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = openai_client
        self._profile = profile
        self._sleep = sleep
        self._clock = clock

    async def generate(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        async def operation() -> LLMResponse[StructuredOutputT]:
            return await self._generate_once(request, output_type=output_type)

        sleep = self._sleep if self._sleep is not None else _sleep
        try:
            response, retry_count = await run_with_retries(
                operation,
                policy=self._profile.retry_policy,
                sleep=sleep,
            )
        except LLMError as error:
            logger.info(
                "llm.generate.failure",
                extra={
                    "operation": request.operation.value,
                    "provider": self._profile.provider,
                    "model": self._profile.model,
                    "profile": self._profile.name,
                    "error_type": type(error).__name__,
                    "retryable": error.retryable,
                },
            )
            raise

        normalized = response.with_retry_count(retry_count)
        prompt_cache = (
            request.prompt_cache
            if _supports_explicit_prompt_caching(self._profile.model)
            else None
        )
        logger.info(
            "llm.generate.success",
            extra={
                "operation": request.operation.value,
                "provider": normalized.provider,
                "model": normalized.model,
                "profile": self._profile.name,
                "latency_ms": normalized.latency_ms,
                "input_tokens": normalized.usage.input_tokens,
                "cached_input_tokens": normalized.usage.cached_input_tokens,
                "cache_write_tokens": normalized.usage.cache_write_tokens,
                "cache_hit_ratio": _cache_hit_ratio(normalized.usage),
                "prompt_cache_key": (
                    prompt_cache.key if prompt_cache is not None else None
                ),
                "prompt_cache_breakpoints": (
                    len(prompt_cache.instruction_breakpoints)
                    if prompt_cache is not None
                    else 0
                ),
                "output_tokens": normalized.usage.output_tokens,
                "retry_count": retry_count,
                "structured_output": output_type.__name__ if output_type else None,
                "tool_call_count": len(normalized.tool_calls),
            },
        )
        return normalized

    async def _generate_once(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None,
    ) -> LLMResponse[StructuredOutputT]:
        started = self._clock()
        payload = self._build_payload(request, output_type)
        try:
            provider_response = await self._client.responses.create(**payload)
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.BadRequestError,
            openai.APIStatusError,
            openai.APIError,
        ) as error:
            raise self._map_openai_error(error, request) from error

        latency_ms = int((self._clock() - started) * 1000)
        return self._normalize_response(
            provider_response,
            request=request,
            output_type=output_type,
            latency_ms=latency_ms,
        )

    async def compact(
        self,
        request: LLMCompactionRequest,
    ) -> LLMCompactionResult:
        """Compact one stored response chain into opaque provider output items."""

        async def operation() -> LLMCompactionResult:
            return await self._compact_once(request)

        sleep = self._sleep if self._sleep is not None else _sleep
        result, retry_count = await run_with_retries(
            operation,
            policy=self._profile.retry_policy,
            sleep=sleep,
        )
        return result.model_copy(update={"retry_count": retry_count})

    async def _compact_once(
        self,
        request: LLMCompactionRequest,
    ) -> LLMCompactionResult:
        started = self._clock()
        try:
            provider_response = await self._client.responses.compact(
                **self._build_compaction_payload(request)
            )
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.BadRequestError,
            openai.APIStatusError,
            openai.APIError,
        ) as error:
            raise self._map_openai_error(error, request) from error
        logger.info(
            "llm.compact.success",
            extra={
                "operation": request.operation.value,
                "provider": self._profile.provider,
                "model": self._profile.model,
                "profile": self._profile.name,
                "latency_ms": int((self._clock() - started) * 1000),
            },
        )
        output = _get(provider_response, "output")
        return LLMCompactionResult(
            context=LLMCompactedContext(
                provider=self._profile.provider,
                payload=dump_json_value(output if output is not None else []),
            ),
            usage=_extract_usage(provider_response),
        )

    def _build_payload(
        self,
        request: LLMRequest,
        output_type: type[BaseModel] | None,
    ) -> dict[str, Any]:
        timeout_seconds = request.timeout_seconds or self._profile.timeout_seconds
        max_output_tokens = request.max_output_tokens or self._profile.max_output_tokens
        temperature = request.temperature
        if temperature is None:
            temperature = self._profile.temperature

        input_items = _messages_to_openai(request.messages)
        if request.compacted_context is not None:
            compacted = request.compacted_context
            if compacted.provider != self._profile.provider:
                raise LLMConfigurationError(
                    "compacted context provider does not match active provider"
                )
            if not isinstance(compacted.payload, list) or any(
                not isinstance(item, dict) for item in compacted.payload
            ):
                raise LLMConfigurationError(
                    "OpenAI compacted context payload must be an input-item list"
                )
            compacted_items = cast(list[dict[str, Any]], compacted.payload)
            input_items = [*compacted_items, *input_items]

        use_prompt_cache = request.prompt_cache is not None and (
            _supports_explicit_prompt_caching(self._profile.model)
        )
        instruction_items: list[dict[str, Any]] = []
        if use_prompt_cache:
            instruction_items = _instructions_to_openai(request)
            input_items = [*instruction_items, *input_items]

        payload: dict[str, Any] = {
            "model": self._profile.model,
            "input": input_items,
            "store": request.store,
        }
        if request.instructions is not None and not use_prompt_cache:
            payload["instructions"] = request.instructions
        if use_prompt_cache:
            assert request.prompt_cache is not None
            payload["prompt_cache_key"] = request.prompt_cache.key
            payload["prompt_cache_options"] = {
                "mode": request.prompt_cache.mode,
            }
        if request.continuation_ref is not None:
            payload["previous_response_id"] = request.continuation_ref
        if timeout_seconds is not None:
            payload["timeout"] = timeout_seconds
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if request.reasoning is not None:
            payload["reasoning"] = request.reasoning.model_dump(exclude_none=True)
        if request.tools:
            payload["tools"] = [_tool_to_openai(tool) for tool in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        if output_type is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": output_type.__name__,
                    "schema": _openai_strict_schema(output_type.model_json_schema()),
                    "strict": True,
                }
            }

        metadata = {
            key: value
            for key, value in request.metadata.items()
            if key in FORWARDED_METADATA_KEYS
        }
        if metadata:
            payload["metadata"] = metadata
        return payload

    def _build_compaction_payload(
        self,
        request: LLMCompactionRequest,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._profile.model,
            "input": _messages_to_openai(request.messages),
            "instructions": request.instructions,
            "previous_response_id": request.continuation_ref,
        }
        timeout_seconds = request.timeout_seconds or self._profile.timeout_seconds
        if timeout_seconds is not None:
            payload["timeout"] = timeout_seconds
        return payload

    def _normalize_response(
        self,
        provider_response: Any,
        *,
        request: LLMRequest,
        output_type: type[StructuredOutputT] | None,
        latency_ms: int,
    ) -> LLMResponse[StructuredOutputT]:
        status = _get(provider_response, "status")
        incomplete_reason = _get(
            _get(provider_response, "incomplete_details"), "reason"
        )
        text = _extract_text(provider_response)
        usage = _extract_usage(provider_response)
        if status == "failed":
            raise LLMProviderError(
                "OpenAI response failed",
                retryable=False,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        if output_type is not None and status == "incomplete":
            raise LLMStructuredOutputError(
                f"Structured output was incomplete: {incomplete_reason or 'unknown'}",
                invalid_output=text,
                usage=usage,
                latency_ms=latency_ms,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )

        refusal = _extract_refusal(provider_response)
        if output_type is not None and refusal is not None:
            raise LLMStructuredOutputError(
                "Provider refused a structured-output request",
                invalid_output=text,
                usage=usage,
                latency_ms=latency_ms,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )

        tool_calls = self._extract_tool_calls(provider_response, request)
        if output_type is None and not text and not tool_calls and refusal is None:
            raise LLMInvalidResponseError(
                "Provider response did not contain text, tool calls, or a refusal",
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        structured_output: StructuredOutputT | None = None
        if output_type is not None and not tool_calls:
            if not text:
                raise LLMStructuredOutputError(
                    "Structured-output request returned empty output",
                    invalid_output=text,
                    usage=usage,
                    latency_ms=latency_ms,
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            try:
                raw_data = json.loads(text)
            except json.JSONDecodeError as error:
                raise LLMStructuredOutputError(
                    "Structured-output request returned invalid JSON",
                    invalid_output=text,
                    usage=usage,
                    latency_ms=latency_ms,
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                ) from error
            try:
                structured_output = output_type.model_validate(raw_data)
            except ValidationError as error:
                raise LLMStructuredOutputError(
                    "Structured-output request failed schema validation",
                    invalid_output=raw_data,
                    usage=usage,
                    latency_ms=latency_ms,
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                ) from error

        model = _get(provider_response, "model") or self._profile.model
        return LLMResponse[StructuredOutputT](
            text=text if output_type is None else None,
            structured_output=structured_output,
            tool_calls=tool_calls,
            refusal=refusal,
            finish_reason=status or incomplete_reason,
            usage=usage,
            provider=self._profile.provider,
            model=model,
            response_id=_get(provider_response, "id"),
            provider_request_id=_get(provider_response, "_request_id"),
            latency_ms=latency_ms,
        )

    async def generate_once(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        """Perform one provider attempt for a runtime-owned retry loop."""
        return await self._generate_once(request, output_type=output_type)

    def _extract_tool_calls(
        self, provider_response: Any, request: LLMRequest
    ) -> list[LLMToolCall]:
        tool_calls: list[LLMToolCall] = []
        for item in _iter_output(provider_response):
            if _get(item, "type") != "function_call":
                continue
            call_id = _get(item, "call_id") or _get(item, "id")
            name = _get(item, "name")
            if not isinstance(call_id, str) or not call_id:
                raise LLMInvalidResponseError(
                    "Provider tool call did not include a stable call ID",
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            if not isinstance(name, str) or not name:
                raise LLMInvalidResponseError(
                    "Provider tool call did not include a name",
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            raw_arguments = _get(item, "arguments")
            if not isinstance(raw_arguments, str):
                raise LLMInvalidResponseError(
                    "Provider tool call did not include JSON arguments",
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise LLMInvalidResponseError(
                    "Provider tool call arguments were not valid JSON",
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                ) from error
            if not isinstance(arguments, dict):
                raise LLMInvalidResponseError(
                    "Provider tool call arguments must be a JSON object",
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            tool_calls.append(
                LLMToolCall(
                    id=call_id,
                    name=name,
                    arguments=arguments,
                    raw_arguments=raw_arguments,
                )
            )
        return tool_calls

    def _map_openai_error(
        self,
        error: Exception,
        request: LLMRequest | LLMCompactionRequest,
    ) -> LLMError:
        status_code = getattr(error, "status_code", None)
        code = _extract_error_code(error)
        detail = _extract_error_message(error)
        message = _safe_provider_message(status_code, code, detail)

        if isinstance(
            error, (openai.AuthenticationError, openai.PermissionDeniedError)
        ):
            return LLMAuthenticationError(
                message,
                retryable=False,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        if isinstance(error, openai.RateLimitError):
            if code == "insufficient_quota":
                return LLMQuotaError(
                    message,
                    retryable=False,
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            retry_error = LLMRateLimitError(
                message,
                retryable=True,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
            retry_after = _extract_retry_after(error)
            if retry_after is not None:
                setattr(retry_error, "retry_after_seconds", retry_after)
            return retry_error
        if isinstance(error, openai.APITimeoutError):
            return LLMTimeoutError(
                message,
                retryable=True,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        if isinstance(error, openai.APIConnectionError):
            return LLMConnectionError(
                message,
                retryable=True,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        if isinstance(error, openai.BadRequestError):
            if code in {"context_length_exceeded", "context_window_exceeded"}:
                return LLMContextLimitError(
                    message,
                    retryable=False,
                    provider=self._profile.provider,
                    model=self._profile.model,
                    operation=request.operation,
                )
            return LLMProviderError(
                message,
                retryable=False,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        if isinstance(error, openai.APIStatusError) and status_code is not None:
            return LLMProviderError(
                message,
                retryable=status_code >= 500,
                provider=self._profile.provider,
                model=self._profile.model,
                operation=request.operation,
            )
        return LLMProviderError(
            message,
            retryable=False,
            provider=self._profile.provider,
            model=self._profile.model,
            operation=request.operation,
        )


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _messages_to_openai(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        items.extend(_message_to_openai_items(message))
    return items


def _instructions_to_openai(request: LLMRequest) -> list[dict[str, Any]]:
    instructions = request.instructions
    prompt_cache = request.prompt_cache
    if instructions is None or prompt_cache is None:
        return []
    content: list[dict[str, Any]] = []
    start = 0
    for end in prompt_cache.instruction_breakpoints:
        content.append(
            {
                "type": "input_text",
                "text": instructions[start:end],
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        )
        start = end
    if start < len(instructions):
        content.append({"type": "input_text", "text": instructions[start:]})
    return [{"type": "message", "role": "developer", "content": content}]


def _message_to_openai_items(message: LLMMessage) -> list[dict[str, Any]]:
    if message.role in {"system", "user"}:
        return [{"role": message.role, "content": message.content}]
    if message.role == "assistant" and message.content is not None:
        return [{"role": "assistant", "content": message.content}]
    if message.role == "assistant":
        return [
            {
                "type": "function_call",
                "call_id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.raw_arguments or json.dumps(tool_call.arguments),
            }
            for tool_call in message.tool_calls
        ]
    return [
        {
            "type": "function_call_output",
            "call_id": message.tool_call_id,
            "output": json.dumps(
                {
                    "ok": not message.tool_failed,
                    "tool_name": message.tool_name,
                    "result": message.tool_result,
                }
            ),
        }
    ]


def _tool_to_openai(tool: LLMToolDefinition) -> dict[str, Any]:
    parameters = (
        _openai_strict_schema(tool.input_schema) if tool.strict else tool.input_schema
    )
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": _canonicalize_json(parameters),
        "strict": tool.strict,
    }


def _openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapt a Pydantic JSON Schema to OpenAI strict structured-output rules."""
    normalized = copy.deepcopy(schema)
    _normalize_schema_node(normalized)
    return normalized


def _normalize_schema_node(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("default", None)
        properties = node.get("properties")
        if isinstance(properties, dict):
            if properties:
                node["required"] = list(properties)
            else:
                node.pop("required", None)
            node["additionalProperties"] = False
        elif node.get("type") == "object":
            node["additionalProperties"] = False
        for value in node.values():
            _normalize_schema_node(value)
    elif isinstance(node, list):
        for value in node:
            _normalize_schema_node(value)


def _extract_usage(provider_response: Any) -> LLMUsage:
    usage = _get(provider_response, "usage")
    if usage is None:
        return LLMUsage()
    input_details = _get(usage, "input_tokens_details")
    output_details = _get(usage, "output_tokens_details")
    return LLMUsage(
        input_tokens=_get(usage, "input_tokens"),
        output_tokens=_get(usage, "output_tokens"),
        total_tokens=_get(usage, "total_tokens"),
        cached_input_tokens=_get(input_details, "cached_tokens"),
        cache_write_tokens=_get(input_details, "cache_write_tokens"),
        reasoning_tokens=_get(output_details, "reasoning_tokens"),
    )


def _cache_hit_ratio(usage: LLMUsage) -> float | None:
    if not usage.input_tokens:
        return None
    return (usage.cached_input_tokens or 0) / usage.input_tokens


def _supports_explicit_prompt_caching(model: str) -> bool:
    match = re.match(r"^gpt-(\d+)\.(\d+)(?:$|-)", model.lower())
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2))) >= (5, 6)


def _canonicalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_json(item) for item in value]
    return value


def _extract_text(provider_response: Any) -> str | None:
    output_text = _get(provider_response, "output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    parts: list[str] = []
    for item in _iter_output(provider_response):
        if _get(item, "type") != "message":
            continue
        for content in _get(item, "content") or []:
            if _get(content, "type") == "output_text":
                text = _get(content, "text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts) or None


def _extract_refusal(provider_response: Any) -> str | None:
    for item in _iter_output(provider_response):
        if _get(item, "type") != "message":
            continue
        for content in _get(item, "content") or []:
            if _get(content, "type") == "refusal":
                refusal = _get(content, "refusal")
                return refusal if isinstance(refusal, str) else "refused"
    return None


def _iter_output(provider_response: Any) -> list[Any]:
    output = _get(provider_response, "output")
    if isinstance(output, list):
        return output
    return []


def _get(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _extract_error_code(error: Exception) -> str | None:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict) and isinstance(nested.get("code"), str):
            return nested["code"]
        if isinstance(body.get("code"), str):
            return body["code"]
    code = getattr(error, "code", None)
    if isinstance(code, str):
        return code
    return None


def _extract_error_message(error: Exception) -> str | None:
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return None
    nested = body.get("error")
    source = nested if isinstance(nested, dict) else body
    message = source.get("message")
    if not isinstance(message, str):
        return None
    normalized = " ".join(message.split())
    return normalized[:1_000] or None


def _extract_retry_after(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _safe_provider_message(
    status_code: int | None,
    code: str | None,
    detail: str | None,
) -> str:
    if code:
        message = f"OpenAI request failed with code {code}"
    elif status_code is not None:
        message = f"OpenAI request failed with HTTP status {status_code}"
    else:
        message = "OpenAI request failed"
    if detail is not None:
        return f"{message}: {detail}"
    return message
