from bridger.llm.models import LLMOperation


class LLMError(RuntimeError):
    """Base class for normalized Bridger LLM failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        operation: LLMOperation | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.operation = operation
        self.retryable = retryable
        self.safe_message = message


class LLMConfigurationError(LLMError):
    """Configuration is missing or invalid."""


class LLMAuthenticationError(LLMError):
    """Provider authentication failed."""


class LLMRateLimitError(LLMError):
    """Provider rate limit was reached."""


class LLMQuotaError(LLMError):
    """Provider quota or credits are exhausted."""


class LLMTimeoutError(LLMError):
    """Provider request timed out."""


class LLMConnectionError(LLMError):
    """Provider connection failed."""


class LLMContextLimitError(LLMError):
    """Request exceeded the provider context limit."""


class LLMInvalidResponseError(LLMError):
    """Provider returned an unusable response."""


class LLMStructuredOutputError(LLMInvalidResponseError):
    """Provider output failed requested structured-output validation."""


class LLMProviderError(LLMError):
    """Provider returned an otherwise normalized error."""
