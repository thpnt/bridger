from collections.abc import Sequence
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from bridger.llm.errors import LLMStructuredOutputError
from bridger.llm.models import LLMRequest, LLMResponse

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class DummyLLMExhaustedError(AssertionError):
    """Raised when a scripted dummy client has no remaining outcomes."""


class DummyLLMClient:
    """Deterministic scripted LLM client for unit and orchestration tests."""

    def __init__(self, outcomes: Sequence[LLMResponse[BaseModel] | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[LLMRequest] = []

    async def generate(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        self.requests.append(request)
        if not self._outcomes:
            raise DummyLLMExhaustedError("DummyLLMClient has no scripted outcomes left")

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
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
                raise LLMStructuredOutputError(
                    "Scripted structured output failed schema validation"
                ) from error
            return cast(
                LLMResponse[StructuredOutputT],
                outcome.model_copy(update={"structured_output": structured_output}),
            )
        return cast(LLMResponse[StructuredOutputT], outcome)
