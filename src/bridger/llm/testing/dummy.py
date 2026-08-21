from collections.abc import Sequence
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from bridger.llm.errors import LLMStructuredOutputError
from bridger.llm.models import (
    LLMCompactionRequest,
    LLMCompactionResult,
    LLMRequest,
    LLMResponse,
)

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class DummyLLMExhaustedError(AssertionError):
    """Raised when a scripted dummy client has no remaining outcomes."""


class DummyLLMClient:
    """Deterministic scripted LLM client for unit and orchestration tests."""

    def __init__(
        self,
        outcomes: Sequence[LLMResponse[BaseModel] | BaseException],
        *,
        compaction_outcomes: Sequence[LLMCompactionResult | BaseException] = (),
    ) -> None:
        self._outcomes = list(outcomes)
        self._compaction_outcomes = list(compaction_outcomes)
        self.requests: list[LLMRequest] = []
        self.compaction_requests: list[LLMCompactionRequest] = []
        self.output_types: list[type[BaseModel] | None] = []

    async def generate(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        self.requests.append(request)
        self.output_types.append(output_type)
        if not self._outcomes:
            raise DummyLLMExhaustedError("DummyLLMClient has no scripted outcomes left")

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if output_type is not None:
            if outcome.structured_output is None:
                raise LLMStructuredOutputError(
                    "Scripted response did not include structured output"
                )
            try:
                structured_output = output_type.model_validate(
                    outcome.structured_output
                )
            except ValidationError as error:
                invalid_output = outcome.structured_output.model_dump(mode="json")
                raise LLMStructuredOutputError(
                    "Scripted structured output failed schema validation",
                    invalid_output=invalid_output,
                    usage=outcome.usage,
                    latency_ms=outcome.latency_ms,
                    provider=outcome.provider,
                    model=outcome.model,
                ) from error
            return cast(
                LLMResponse[StructuredOutputT],
                outcome.model_copy(update={"structured_output": structured_output}),
            )
        return cast(LLMResponse[StructuredOutputT], outcome)

    async def compact(self, request: LLMCompactionRequest) -> LLMCompactionResult:
        """Return one scripted compaction result and record the exact request."""
        self.compaction_requests.append(request)
        if not self._compaction_outcomes:
            raise DummyLLMExhaustedError(
                "DummyLLMClient has no scripted compaction outcomes left"
            )
        outcome = self._compaction_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
