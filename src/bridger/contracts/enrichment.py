"""Layer 5 AI enrichment overlay contracts."""

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from bridger.contracts.token_usage import TokenUsage

EnabledEnrichmentFeature = Literal["community_names"]
EnrichmentTargetType = Literal["node", "edge", "hyperedge", "community", "graph"]
EnrichmentTargetReference = str | dict[str, JsonValue]


def _default_enabled_features() -> list[EnabledEnrichmentFeature]:
    return ["community_names"]


class GraphEnrichmentConfig(BaseModel):
    """Configuration for one Layer 5 enrichment pass."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    enabled_features: list[EnabledEnrichmentFeature] = Field(
        default_factory=_default_enabled_features,
        min_length=1,
    )
    max_concurrency: int = Field(default=4, ge=1)

    @field_validator("enabled_features")
    @classmethod
    def validate_enabled_features(
        cls,
        value: list[EnabledEnrichmentFeature],
    ) -> list[EnabledEnrichmentFeature]:
        """Require each activated V0 feature exactly once."""
        if len(value) != len(set(value)):
            raise ValueError("enabled enrichment features must be unique")
        return value


class CommunityRepresentative(BaseModel):
    """One bounded deterministic graph node supplied as naming evidence."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    node_type: str | None = Field(default=None, min_length=1)
    source_path: str | None = Field(default=None, min_length=1)


class CommunityEvidence(BaseModel):
    """Canonical deterministic model input for one community name."""

    model_config = ConfigDict(extra="forbid")

    community_id: int = Field(ge=0)
    important_representatives: list[CommunityRepresentative] = Field(
        default_factory=list
    )
    other_representatives: list[CommunityRepresentative] = Field(default_factory=list)


class CommunityName(BaseModel):
    """Structured model output for one community."""

    model_config = ConfigDict(extra="forbid")

    community_id: int = Field(ge=0)
    name: str = Field(min_length=1)


class CommunityNameBatch(BaseModel):
    """Structured model output for one community-naming batch."""

    model_config = ConfigDict(extra="forbid")

    communities: list[CommunityName]


class EnrichmentRecord(BaseModel):
    """One AI annotation over one deterministic graph target."""

    model_config = ConfigDict(extra="forbid")

    enrichment_id: str = Field(min_length=1)
    target_type: EnrichmentTargetType
    target_ref: EnrichmentTargetReference
    annotation_type: str = Field(min_length=1)
    value: JsonValue
    confidence: float | None = Field(default=None, ge=0, le=1)
    deterministic_features: dict[str, JsonValue]


class FailedEnrichmentBatch(BaseModel):
    """Bounded persisted diagnostics for one exhausted model batch."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=1)
    target_refs: list[EnrichmentTargetReference] = Field(min_length=1)
    attempts: int = Field(ge=1, le=3)
    error_category: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class FeatureGenerationSummary(BaseModel):
    """Execution coverage for one enabled enrichment feature."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "partial"]
    target_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    failed_target_count: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    failed_batch_count: int = Field(ge=0)
    failed_batches: list[FailedEnrichmentBatch] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)

    @model_validator(mode="after")
    def validate_counts(self) -> "FeatureGenerationSummary":
        """Enforce local generation coverage and failed-batch invariants."""
        covered = self.generated_count + self.reused_count + self.failed_target_count
        if covered != self.target_count:
            raise ValueError("feature generation counts do not cover all targets")
        if self.failed_batch_count != len(self.failed_batches):
            raise ValueError("failed_batch_count does not match failed_batches")
        if self.failed_batch_count > self.batch_count:
            raise ValueError("failed_batch_count exceeds batch_count")
        expected_status = "partial" if self.failed_target_count else "complete"
        if self.status != expected_status:
            raise ValueError("feature generation status does not match failures")
        return self


class EnrichmentGenerationSummary(BaseModel):
    """Execution coverage for every enabled feature in one overlay."""

    model_config = ConfigDict(extra="forbid")

    features: dict[str, FeatureGenerationSummary]


class GraphEnrichmentOverlay(BaseModel):
    """One immutable AI enrichment pass over one graph snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    overlay_id: str = Field(min_length=1)
    graph_snapshot_id: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    enabled_features: list[str] = Field(min_length=1)
    created_at: datetime
    generation_summary: EnrichmentGenerationSummary
    records: list[EnrichmentRecord]

    @field_validator("enabled_features")
    @classmethod
    def validate_enabled_features(cls, value: list[str]) -> list[str]:
        """Reject ambiguous repeated feature declarations."""
        if len(value) != len(set(value)):
            raise ValueError("enabled enrichment features must be unique")
        return value


__all__ = [
    "CommunityEvidence",
    "CommunityName",
    "CommunityNameBatch",
    "CommunityRepresentative",
    "EnabledEnrichmentFeature",
    "EnrichmentGenerationSummary",
    "EnrichmentRecord",
    "EnrichmentTargetReference",
    "EnrichmentTargetType",
    "FailedEnrichmentBatch",
    "FeatureGenerationSummary",
    "GraphEnrichmentConfig",
    "GraphEnrichmentOverlay",
]
