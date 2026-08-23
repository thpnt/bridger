"""Small provider-neutral tool binding and execution primitives."""

import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ValidationError

from bridger.llm.models import (
    LLMToolCall,
    LLMToolDefinition,
    LLMToolError,
    LLMToolResult,
    dump_json_value,
)

ToolArgumentsT = TypeVar("ToolArgumentsT", bound=BaseModel)
ToolHandler = Callable[[BaseModel], object | Awaitable[object]]


@dataclass(frozen=True, slots=True)
class LLMTool:
    """One definition, argument validator, and bound Python handler."""

    definition: LLMToolDefinition
    arguments_type: type[BaseModel]
    handler: ToolHandler

    @classmethod
    def bind(
        cls,
        *,
        name: str,
        description: str,
        arguments_type: type[ToolArgumentsT],
        handler: Callable[[ToolArgumentsT], object | Awaitable[object]],
    ) -> "LLMTool":
        """Bind a typed handler and derive its provider-neutral JSON Schema."""

        def invoke(arguments: BaseModel) -> object | Awaitable[object]:
            return handler(cast(ToolArgumentsT, arguments))

        return cls(
            definition=LLMToolDefinition(
                name=name,
                description=description,
                input_schema=arguments_type.model_json_schema(mode="validation"),
            ),
            arguments_type=arguments_type,
            handler=invoke,
        )


class ToolExecutor:
    """Validate and execute explicit bound tools without owning any LLM loop."""

    def __init__(
        self,
        tools: Iterable[LLMTool],
        *,
        handled_errors: tuple[type[Exception], ...] = (ValueError, KeyError),
    ) -> None:
        tool_list = list(tools)
        self._tools = {tool.definition.name: tool for tool in tool_list}
        if len(self._tools) != len(tool_list):
            raise ValueError("tool names must be unique")
        self._handled_errors = handled_errors

    @property
    def definitions(self) -> list[LLMToolDefinition]:
        """Return definitions in their explicit registration order."""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, call: LLMToolCall) -> LLMToolResult:
        """Execute one validated call and return a correlated structured result."""
        if call.has_malformed_arguments:
            return _failed_result(
                call,
                code="malformed_arguments",
                message=(
                    f"Invalid arguments for {call.name}: retry this call with a "
                    "valid JSON object matching the tool schema."
                ),
            )

        tool = self._tools.get(call.name)
        if tool is None:
            return _failed_result(
                call,
                code="unknown_tool",
                message=f"Unknown tool: {call.name}",
            )

        try:
            arguments = tool.arguments_type.model_validate(call.arguments)
        except ValidationError as error:
            return _failed_result(
                call,
                code="invalid_arguments",
                message=(
                    f"Invalid arguments for {call.name}: "
                    f"{error.error_count()} validation error(s)"
                ),
            )

        try:
            output = tool.handler(arguments)
            if inspect.isawaitable(output):
                output = await output
        except self._handled_errors as error:
            return _failed_result(
                call,
                code="tool_execution_error",
                message=_error_message(error),
            )

        return LLMToolResult(
            call_id=call.id,
            name=call.name,
            output=dump_json_value(output),
        )


def _failed_result(
    call: LLMToolCall,
    *,
    code: Literal[
        "unknown_tool",
        "invalid_arguments",
        "malformed_arguments",
        "tool_execution_error",
    ],
    message: str,
) -> LLMToolResult:
    return LLMToolResult(
        call_id=call.id,
        name=call.name,
        error=LLMToolError(code=code, message=message),
    )


def _error_message(error: Exception) -> str:
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error) or type(error).__name__


__all__ = ["LLMTool", "ToolExecutor"]
