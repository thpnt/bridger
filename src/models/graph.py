"""Layer 3 and Layer 4 deterministic graph contracts."""

from datetime import datetime
from pathlib import Path
from typing import Literal, TypeAlias

import networkx as nx  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

RepositoryGraph: TypeAlias = nx.DiGraph


class GraphConstructionConfig(BaseModel):
    """Deterministic configuration for Graphify graph intelligence."""

    model_config = ConfigDict(extra="forbid")

    community_algorithm: Literal["leiden"] = "leiden"
    community_resolution: float = Field(default=1.0, gt=0)
    hub_exclusion_percentile: float | None = Field(default=None, ge=0, le=100)
    god_node_limit: int = Field(default=10, ge=1)
    surprising_connections_limit: int = Field(default=5, ge=1)
    suggested_questions_limit: int = Field(default=7, ge=1)


class GraphDiagnostics(BaseModel):
    """Graph construction quality and validation result for one revision."""

    model_config = ConfigDict(extra="forbid")

    input_node_count: int = Field(ge=0)
    output_node_count: int = Field(ge=0)
    input_edge_count: int = Field(ge=0)
    output_edge_count: int = Field(ge=0)
    input_hyperedge_count: int = Field(ge=0)
    output_hyperedge_count: int = Field(ge=0)
    invalid_records: list[str] = Field(default_factory=list)
    dropped_records: list[str] = Field(default_factory=list)
    dangling_endpoints: list[str] = Field(default_factory=list)
    possible_same_endpoint_edge_collapse_count: int = Field(ge=0)
    isolated_node_count: int = Field(ge=0)
    community_count: int = Field(ge=0)
    single_node_community_count: int = Field(ge=0)
    community_coverage_complete: bool
    file_index_consistency_failures: list[str] = Field(default_factory=list)
    structural_analysis_reference_failures: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning", "error"]
    publication_blocking: bool


class ArtifactReference(BaseModel):
    """Integrity metadata for one payload artifact in a graph snapshot."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class GraphSnapshotManifest(BaseModel):
    """Bridger's immutable lifecycle authority for one graph snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    scope_path: str = Field(min_length=1)
    file_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_contract_version: str = Field(min_length=1)
    graphify_engine_version: str = Field(min_length=1)
    extractor_fingerprint: str = Field(min_length=1)
    inventory_policy_version: str = Field(min_length=1)
    build_configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    build_mode: Literal["full", "incremental"]
    parent_snapshot_id: str | None = Field(default=None, min_length=1)
    artifacts: dict[str, ArtifactReference]
    created_at: datetime
    validation_status: Literal["validated"]
    diagnostics_summary: dict[str, int | str | bool]


class GraphBuildResult(BaseModel):
    """Runtime graph result returned by Layer 4 build and load operations."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    operation_mode: Literal["full", "incremental", "loaded"]
    graph: RepositoryGraph
    manifest: GraphSnapshotManifest
    diagnostics: GraphDiagnostics
    snapshot_root: Path
