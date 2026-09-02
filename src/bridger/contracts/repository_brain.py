"""Typed publication contract for one accepted Repository Brain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RepositoryBrainManifest(BaseModel):
    """Immutable provenance required to reopen one accepted memory fleet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    repository_id: str = Field(min_length=1)
    repository_revision: str = Field(min_length=1)
    graph_snapshot_id: str = Field(min_length=1)
    graph_snapshot_root: str = Field(min_length=1)
    enrichment_overlay_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    memory_runtime_root: str = Field(min_length=1)
    memory_output_root: str = Field(min_length=1)
    accepted_memory_fleet_result_id: str = Field(min_length=1)
    memory_target_catalog_id: str = Field(min_length=1)
    memory_target_catalog_version: str = Field(min_length=1)
    accepted_target_result_refs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_accepted_target_refs(self) -> RepositoryBrainManifest:
        """Require a non-empty, unambiguous accepted target inventory."""
        if any(not reference for reference in self.accepted_target_result_refs):
            raise ValueError("accepted target result references must be non-empty")
        if len(self.accepted_target_result_refs) != len(
            set(self.accepted_target_result_refs)
        ):
            raise ValueError("accepted target result references must be unique")
        return self


__all__ = ["RepositoryBrainManifest"]
