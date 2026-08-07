import os

from pydantic import BaseModel, ConfigDict, Field

from llm.errors import LLMConfigurationError


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    initial_backoff_seconds: float = Field(default=0.25, gt=0)
    max_backoff_seconds: float = Field(default=2.0, gt=0)


class LLMProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    reasoning: dict[str, str] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


def resolve_llm_profile(profile_name: str = "balanced") -> LLMProfile:
    """Resolve a deterministic profile from environment-backed settings."""
    if profile_name != "balanced":
        raise LLMConfigurationError(f"Unsupported LLM profile: {profile_name}")

    model = os.environ.get("BRIDGER_OPENAI_MODEL", "").strip()
    if not model:
        raise LLMConfigurationError(
            "BRIDGER_OPENAI_MODEL is required for the balanced LLM profile"
        )

    return LLMProfile(
        name="balanced",
        provider="openai",
        model=model,
        max_output_tokens=_optional_int("BRIDGER_OPENAI_MAX_OUTPUT_TOKENS"),
        timeout_seconds=_optional_float("BRIDGER_OPENAI_TIMEOUT_SECONDS"),
    )


def _optional_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise LLMConfigurationError(f"{name} must be an integer") from error


def _optional_float(name: str) -> float | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise LLMConfigurationError(f"{name} must be a number") from error
