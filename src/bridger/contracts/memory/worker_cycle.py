"""Durable contracts introduced by memory-harness Stage 4."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from bridger.contracts.enrichment import EnrichmentTargetType
from bridger.contracts.memory.core import SourceBinding


class EvidenceKind(StrEnum):
    """Exact V0 source-authority families accepted as durable evidence."""

    FILE = "file"
    SOURCE_RANGE = "source-range"
    SYMBOL = "symbol"
    GRAPH_ENTITY = "graph-entity"


class FileEvidenceLocator(BaseModel):
    """One indexed repository file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)


class SourceRangeEvidenceLocator(BaseModel):
    """One exact revision-bound source range."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_range(self) -> SourceRangeEvidenceLocator:
        """Reject inverted source ranges."""
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        return self


class SymbolEvidenceLocator(BaseModel):
    """One exact symbol-index identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol_id: str = Field(min_length=1)


class GraphEntityEvidenceLocator(BaseModel):
    """One entity in the bound deterministic graph view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_type: EnrichmentTargetType
    target_ref: str | dict[str, JsonValue]


EvidenceLocator = (
    FileEvidenceLocator
    | SourceRangeEvidenceLocator
    | SymbolEvidenceLocator
    | GraphEntityEvidenceLocator
)


class EvidenceReference(BaseModel):
    """Immutable target- and source-bound evidence identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    source: SourceBinding
    kind: EvidenceKind
    locator: EvidenceLocator

    @model_validator(mode="after")
    def validate_locator_kind(self) -> EvidenceReference:
        """Keep the evidence family and typed locator mechanically aligned."""
        expected_type = {
            EvidenceKind.FILE: FileEvidenceLocator,
            EvidenceKind.SOURCE_RANGE: SourceRangeEvidenceLocator,
            EvidenceKind.SYMBOL: SymbolEvidenceLocator,
            EvidenceKind.GRAPH_ENTITY: GraphEntityEvidenceLocator,
        }[self.kind]
        if not isinstance(self.locator, expected_type):
            raise ValueError("evidence kind does not match locator type")
        return self


class OpenQuestion(BaseModel):
    """Immutable target-local question whose openness is state-projected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @property
    def content(self) -> str:
        """Expose the Stage 3 projection vocabulary without duplicating state."""
        return self.text

    @property
    def is_open(self) -> bool:
        """Current openness is represented by TargetTaskState references."""
        return True


__all__ = [
    "EvidenceKind",
    "EvidenceLocator",
    "EvidenceReference",
    "FileEvidenceLocator",
    "GraphEntityEvidenceLocator",
    "OpenQuestion",
    "SourceRangeEvidenceLocator",
    "SymbolEvidenceLocator",
]
