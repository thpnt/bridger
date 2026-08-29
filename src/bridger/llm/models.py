from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_core import to_jsonable_python

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)

ToolName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class LLMOperation(StrEnum):
    REPO_DISCOVERY = "repo_discovery"
    COMMUNITY_NAMING = "community_naming"
    CONTEXT_PLAN_GENERATION = "context_plan_generation"
    CONTEXT_PLAN_REVIEW = "context_plan_review"
    MEMORY_AGENT_EVIDENCE = "memory_agent_evidence"
    MEMORY_AGENT_RECONCILIATION = "memory_agent_reconciliation"
    MEMORY_AGENT_WORKER = "memory_agent_worker"
    MEMORY_AGENT_REVIEW = "memory_agent_review"
    AGENTS_EXPORT = "agents_export"
    PROMPT_GENERATION = "prompt_generation"
    TICKET_GENERATION = "ticket_generation"
    UPDATE = "update"
    IMPLEMENTATION_PLANNING = "implementation_planning"


class LLMToolCall(BaseModel):
    """One provider tool request, including a recoverable malformed payload."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: ToolName
    arguments: dict[str, JsonValue] | None = None
    raw_arguments: JsonValue | None = None
    argument_error: Literal["invalid_json", "not_json_object"] | None = None

    @model_validator(mode="after")
    def validate_arguments(self) -> "LLMToolCall":
        """Require either an object payload or a preserved parse failure."""
        if self.argument_error is None and self.arguments is None:
            raise ValueError("tool calls require an arguments object")
        if self.argument_error is not None and self.arguments is not None:
            raise ValueError("malformed tool calls cannot contain parsed arguments")
        return self

    @property
    def has_malformed_arguments(self) -> bool:
        """Return whether this call could not form the required JSON object."""
        return self.argument_error is not None


class LLMToolError(BaseModel):
    """Ordinary tool failure that a caller may return to a future model turn."""

    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "unknown_tool",
        "invalid_arguments",
        "malformed_arguments",
        "tool_execution_error",
        "permission_denied",
        "protocol_error",
    ]
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] | None = None


class LLMToolResult(BaseModel):
    """Provider-neutral result correlated with one requested tool call."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    name: ToolName
    output: JsonValue = None
    error: LLMToolError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "LLMToolResult":
        """Prevent a failed result from also carrying a successful output."""
        if self.error is not None and self.output is not None:
            raise ValueError("tool result cannot contain both output and error")
        return self

    def as_message(self) -> "LLMMessage":
        """Convert this result to the existing provider-neutral tool message."""
        result: JsonValue = self.output
        if self.error is not None:
            result = {"error": self.error.model_dump(mode="json", exclude_none=True)}
        return LLMMessage.tool_result_message(
            tool_call_id=self.call_id,
            tool_name=self.name,
            result=result,
            failed=self.error is not None,
        )


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: ToolName | None = None
    tool_result: (
        dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
    ) = None
    tool_failed: bool = False

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "LLMMessage":
        return cls(role="assistant", content=content)

    @classmethod
    def assistant_tool_calls(cls, tool_calls: list[LLMToolCall]) -> "LLMMessage":
        return cls(role="assistant", tool_calls=tool_calls)

    @classmethod
    def tool_result_message(
        cls,
        *,
        tool_call_id: str,
        tool_name: str,
        result: (
            dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
        ),
        failed: bool = False,
    ) -> "LLMMessage":
        return cls(
            role="tool",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result=result,
            tool_failed=failed,
        )

    @model_validator(mode="after")
    def validate_role_payload(self) -> "LLMMessage":
        if self.role in {"system", "user"}:
            if not self.content:
                raise ValueError(f"{self.role} messages require text content")
            if self.tool_calls or self.tool_call_id is not None:
                raise ValueError(f"{self.role} messages cannot contain tool data")
        if self.role == "assistant":
            has_content = self.content is not None and self.content != ""
            has_tool_calls = bool(self.tool_calls)
            if has_content == has_tool_calls:
                raise ValueError(
                    "assistant messages require exactly one of content or tool_calls"
                )
            if self.tool_call_id is not None:
                raise ValueError("assistant messages cannot contain tool results")
        if self.role == "tool":
            if not self.tool_call_id or not self.tool_name:
                raise ValueError("tool results require tool_call_id and tool_name")
            if self.content is not None or self.tool_calls:
                raise ValueError("tool results cannot contain assistant content")
        return self


class LLMToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ToolName
    description: str = Field(min_length=1)
    input_schema: dict[str, JsonValue]
    strict: bool = True

    @field_validator("input_schema")
    @classmethod
    def validate_json_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("tool input_schema must be a JSON Schema object")
        properties = value.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError("tool input_schema properties must be an object")
        return value


class LLMReasoningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    context: Literal["auto", "current_turn", "all_turns"] | None = None
    summary: Literal["auto", "concise", "detailed"] | None = None


class LLMCompactedContext(BaseModel):
    """Opaque provider-owned transient trajectory returned by compaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    payload: JsonValue


class LLMPromptCacheConfig(BaseModel):
    """Provider-neutral prompt-prefix cache intent for exact instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    mode: Literal["explicit"] = "explicit"
    instruction_breakpoints: tuple[int, ...]

    @field_validator("instruction_breakpoints")
    @classmethod
    def validate_breakpoints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        """Require positive, strictly increasing instruction offsets."""
        if not value:
            raise ValueError("prompt cache requires at least one breakpoint")
        if any(offset < 1 for offset in value):
            raise ValueError("prompt cache breakpoints must be positive")
        if tuple(sorted(set(value))) != value:
            raise ValueError("prompt cache breakpoints must be strictly increasing")
        return value


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: LLMOperation
    profile: str = Field(default="balanced", min_length=1)
    messages: list[LLMMessage] = Field(default_factory=list)
    instructions: str | None = Field(default=None, min_length=1)
    continuation_ref: str | None = Field(default=None, min_length=1)
    store: bool = False
    compacted_context: LLMCompactedContext | None = None
    prompt_cache: LLMPromptCacheConfig | None = None
    tools: list[LLMToolDefinition] = Field(default_factory=list)
    tool_choice: str | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning: LLMReasoningConfig | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if len(key) > 64 or len(item) > 512:
                raise ValueError("metadata keys and values exceed provider limits")
        return value

    @model_validator(mode="after")
    def validate_prompt_cache(self) -> "LLMRequest":
        """Keep cache boundaries within the exact instruction surface."""
        if self.prompt_cache is None:
            return self
        if self.instructions is None:
            raise ValueError("prompt cache requires exact instructions")
        if self.prompt_cache.instruction_breakpoints[-1] > len(self.instructions):
            raise ValueError("prompt cache breakpoint exceeds exact instructions")
        return self


class LLMCompactionRequest(BaseModel):
    """Provider-neutral request to compact one active transient trajectory."""

    model_config = ConfigDict(extra="forbid")

    operation: LLMOperation
    profile: str = Field(default="balanced", min_length=1)
    messages: list[LLMMessage] = Field(default_factory=list)
    instructions: str = Field(min_length=1)
    continuation_ref: str = Field(min_length=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if len(key) > 64 or len(item) > 512:
                raise ValueError("metadata keys and values exceed provider limits")
        return value


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(BaseModel, Generic[StructuredOutputT]):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    text: str | None = None
    structured_output: StructuredOutputT | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    refusal: str | None = None
    finish_reason: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    provider: str
    model: str
    response_id: str | None = None
    provider_request_id: str | None = None
    latency_ms: int | None = None
    retry_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> "LLMResponse[StructuredOutputT]":
        outcomes = [
            self.text is not None and self.text != "",
            self.structured_output is not None,
            bool(self.tool_calls),
            self.refusal is not None,
        ]
        if not any(outcomes):
            raise ValueError(
                "LLMResponse requires text, structured output, tool calls, or refusal"
            )
        if self.refusal is not None and any(outcomes[:3]):
            raise ValueError("refusal cannot be combined with successful output")
        return self

    def with_retry_count(self, retry_count: int) -> "LLMResponse[StructuredOutputT]":
        return self.model_copy(update={"retry_count": retry_count})


class LLMCompactionResult(BaseModel):
    """Opaque compacted provider context plus normal model-execution usage."""

    model_config = ConfigDict(extra="forbid")

    context: LLMCompactedContext
    usage: LLMUsage = Field(default_factory=LLMUsage)
    retry_count: int = Field(default=0, ge=0)


def dump_json_value(value: Any) -> JsonValue:
    """Normalize supported runtime values to validated JSON-compatible data."""
    return _JSON_VALUE_ADAPTER.validate_python(to_jsonable_python(value))
