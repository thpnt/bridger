"""OpenAI-compatible request token visibility for the memory harness."""

from __future__ import annotations

import tiktoken

from bridger.contracts.memory.hydration import (
    ContextWindowDiagnostics,
    RequestContextWindowDiagnostics,
    WorkerProfile,
)
from bridger.memory.errors import ContextWindowConfigurationError


class ContextWindowManager:
    """Count V0 request input and expose model-aware context headroom."""

    def __init__(
        self,
        profile: WorkerProfile,
        *,
        fixed_request_input: str = "",
        provider_framing_tokens: int = 0,
    ) -> None:
        if provider_framing_tokens < 0:
            raise ContextWindowConfigurationError(
                "provider_framing_tokens cannot be negative"
            )
        try:
            self._encoding = tiktoken.get_encoding(profile.tokenizer_encoding)
        except (KeyError, ValueError) as error:
            raise ContextWindowConfigurationError(
                f"unknown OpenAI tokenizer encoding: {profile.tokenizer_encoding}"
            ) from error
        self._profile = profile
        self._fixed_request_input_tokens = (
            self.count_text(fixed_request_input) + provider_framing_tokens
        )
        if (
            self._fixed_request_input_tokens
            > profile.provider_input_hard_cap_tokens
        ):
            raise ContextWindowConfigurationError(
                "fixed request input exceeds the provider-input hard cap"
            )

    @property
    def profile(self) -> WorkerProfile:
        """Return the exact immutable profile used for token accounting."""
        return self._profile

    @property
    def fixed_request_input_tokens(self) -> int:
        """Return non-WorkerContext input reserved in the initial request."""
        return self._fixed_request_input_tokens

    @property
    def maximum_worker_context_tokens(self) -> int:
        """Return the hard WorkerContext allowance without attempting to fill it."""
        return (
            self._profile.provider_input_hard_cap_tokens
            - self._fixed_request_input_tokens
        )

    def count_text(self, value: str) -> int:
        """Count text with the configured OpenAI BPE tokenizer."""
        return len(self._encoding.encode(value, disallowed_special=()))

    def inspect_initial_worker_context(
        self,
        serialized_worker_context: str,
    ) -> ContextWindowDiagnostics:
        """Measure one complete mandatory initial provider input."""
        worker_context_tokens = self.count_text(serialized_worker_context)
        complete_input_tokens = self._fixed_request_input_tokens + worker_context_tokens
        provider_input_cap = self._profile.provider_input_hard_cap_tokens
        model_remaining = (
            self._profile.model_context_window_tokens
            - self._profile.reserved_response_tokens
            - complete_input_tokens
        )
        return ContextWindowDiagnostics(
            model_context_window_tokens=self._profile.model_context_window_tokens,
            reserved_response_tokens=self._profile.reserved_response_tokens,
            provider_input_hard_cap_tokens=provider_input_cap,
            fixed_request_input_tokens=self._fixed_request_input_tokens,
            maximum_worker_context_tokens=self.maximum_worker_context_tokens,
            worker_context_tokens=worker_context_tokens,
            complete_initial_provider_input_tokens=complete_input_tokens,
            remaining_provider_input_tokens=max(
                0, provider_input_cap - complete_input_tokens
            ),
            remaining_model_context_tokens=max(0, model_remaining),
            within_provider_input_limit=complete_input_tokens <= provider_input_cap,
            within_model_context_limit=model_remaining >= 0,
        )

    def inspect_request(
        self,
        serialized_request_input: str,
        *,
        provider_framing_tokens: int = 0,
        reserved_response_tokens: int | None = None,
    ) -> RequestContextWindowDiagnostics:
        """Expose input count, remaining capacity, and fit for a future model call."""
        if provider_framing_tokens < 0:
            raise ContextWindowConfigurationError(
                "provider_framing_tokens cannot be negative"
            )
        input_tokens = self.count_text(serialized_request_input)
        input_tokens += provider_framing_tokens
        response_tokens = (
            self._profile.reserved_response_tokens
            if reserved_response_tokens is None
            else reserved_response_tokens
        )
        if response_tokens < 0:
            raise ContextWindowConfigurationError(
                "reserved_response_tokens cannot be negative"
            )
        remaining = (
            self._profile.model_context_window_tokens - response_tokens - input_tokens
        )
        return RequestContextWindowDiagnostics(
            model_context_window_tokens=self._profile.model_context_window_tokens,
            current_request_input_tokens=input_tokens,
            reserved_response_tokens=response_tokens,
            remaining_context_tokens=max(0, remaining),
            within_context_limit=remaining >= 0,
        )


__all__ = ["ContextWindowManager"]
