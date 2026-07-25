"""Deterministic record of evidence supplied to Context Plan synthesis."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from bridger.models.repository_path import RepositoryPath, validate_repository_path
from bridger.models.working_state import EvidenceLineRange

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
StableId = NonEmptyString


class SynthesisManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


class SynthesisSelectionLimits(SynthesisManifestModel):
    max_evidence_records: Annotated[int, Field(gt=0)] = 200
    max_estimated_characters: Annotated[int, Field(gt=0)] = 120_000
    max_verbatim_excerpts: Annotated[int, Field(gt=0)] = 80


class SynthesisVerbatimExcerpt(SynthesisManifestModel):
    evidence_ids: Annotated[list[StableId], Field(min_length=1)]
    path: RepositoryPath
    line_range: EvidenceLineRange
    content: str

    _validate_path = field_validator("path")(validate_repository_path)


class SynthesisOmission(SynthesisManifestModel):
    evidence_id: StableId
    kind: NonEmptyString
    area_key: NonEmptyString
    path: RepositoryPath | None = None
    reason: NonEmptyString

    @field_validator("path")
    @classmethod
    def validate_optional_path(cls, path: str | None) -> str | None:
        return validate_repository_path(path) if path is not None else None


class SynthesisInputManifest(SynthesisManifestModel):
    schema_version: Literal[1] = 1
    manifest_id: StableId
    run_id: NonEmptyString
    working_state_revision: NonEmptyString
    selected_candidate_ids: list[StableId] = Field(default_factory=list)
    selected_finding_ids: list[StableId] = Field(default_factory=list)
    selected_relationship_ids: list[StableId] = Field(default_factory=list)
    selected_question_ids: list[StableId] = Field(default_factory=list)
    selected_evidence_ids: list[StableId] = Field(default_factory=list)
    selected_verbatim_excerpts: list[SynthesisVerbatimExcerpt] = Field(
        default_factory=list
    )
    priority_paths: list[RepositoryPath] = Field(default_factory=list)
    represented_area_keys: list[NonEmptyString] = Field(default_factory=list)
    selection_limits: SynthesisSelectionLimits
    estimated_size: Annotated[int, Field(ge=0)]
    available_record_count: Annotated[int, Field(ge=0)]
    selected_record_count: Annotated[int, Field(ge=0)]
    omitted_record_count: Annotated[int, Field(ge=0)]
    omitted_counts: dict[str, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)
    omitted_by_kind: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )
    omitted_by_area: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )
    omitted_by_path: dict[str, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )
    omission_reasons: list[SynthesisOmission] = Field(default_factory=list)
    created_at: datetime

    _validate_priority_paths = field_validator("priority_paths")(
        lambda paths: [validate_repository_path(path) for path in paths]
    )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value
