"""Typed token-usage contracts shared by model-driven Bridger stages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TokenUsage(BaseModel):
    """Provider-reported token counters without derived totals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_cached_input(self) -> "TokenUsage":
        """Require cached input to remain a subset of provider input."""
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return self

    @property
    def uncached_input_tokens(self) -> int:
        """Return input tokens excluding the cached subset."""
        return self.input_tokens - self.cached_input_tokens

    @property
    def derived_uncached_input_tokens(self) -> int:
        """Return the explicitly derived uncached-input value."""
        return self.uncached_input_tokens

    def add(self, other: "TokenUsage") -> "TokenUsage":
        """Return the component-wise sum of two usage values."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=(self.cached_input_tokens + other.cached_input_tokens),
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )

    def subtract(self, other: "TokenUsage") -> "TokenUsage":
        """Return a non-negative component-wise difference."""
        values = {
            field_name: getattr(self, field_name) - getattr(other, field_name)
            for field_name in TOKEN_USAGE_FIELDS
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("token usage difference cannot be negative")
        return TokenUsage(**values)


TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
)


class TokenUsageTarget(BaseModel):
    """Usage attributed to one ordered memory target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_task_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    usage: TokenUsage


class TokenUsageReport(BaseModel):
    """Persisted token audit for one model-driven Repository Brain init."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    init_mode: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    enrichment_overlay_id: str = Field(min_length=1)
    layer5_enrichment: TokenUsage
    targets: list[TokenUsageTarget]
    fleet_only_memory_overhead: TokenUsage
    memory_total: TokenUsage
    init_total: TokenUsage

    @model_validator(mode="after")
    def validate_report_identities_and_totals(self) -> "TokenUsageReport":
        """Require deterministic target identity and accounting totals."""
        task_ids = [target.target_task_id for target in self.targets]
        target_ids = [target.target_id for target in self.targets]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("token usage target task IDs must be unique")
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("token usage target IDs must be unique")

        target_total = TokenUsage()
        for target in self.targets:
            target_total = target_total.add(target.usage)
        if self.memory_total != target_total.add(self.fleet_only_memory_overhead):
            raise ValueError("memory token usage total is inconsistent")
        if self.init_total != self.layer5_enrichment.add(self.memory_total):
            raise ValueError("init token usage total is inconsistent")
        return self

    @property
    def layer5_usage(self) -> TokenUsage:
        """Return the Layer 5 usage under its concise audit name."""
        return self.layer5_enrichment

    @property
    def target_usage(self) -> list[TokenUsageTarget]:
        """Return ordered per-target usage entries."""
        return self.targets

    @property
    def fleet_only_overhead(self) -> TokenUsage:
        """Return the fleet-only memory overhead."""
        return self.fleet_only_memory_overhead


__all__ = [
    "TOKEN_USAGE_FIELDS",
    "TokenUsage",
    "TokenUsageReport",
    "TokenUsageTarget",
]
