from typing import Protocol, TypeVar

from pydantic import BaseModel

from bridger.llm.models import (
    LLMCompactionRequest,
    LLMCompactionResult,
    LLMRequest,
    LLMResponse,
)

StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class LLMClient(Protocol):
    """Provider-independent interface for one asynchronous model turn."""

    async def generate(
        self,
        request: LLMRequest,
        *,
        output_type: type[StructuredOutputT] | None = None,
    ) -> LLMResponse[StructuredOutputT]:
        """Generate one normalized LLM response for the supplied request."""

    async def compact(
        self,
        request: LLMCompactionRequest,
    ) -> LLMCompactionResult:
        """Compact one active provider trajectory into opaque transient context."""
