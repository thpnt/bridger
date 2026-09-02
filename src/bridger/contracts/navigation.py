"""Runtime-only contracts for Layer 6 repository navigation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from bridger.contracts.enrichment import (
    EnrichmentRecord,
    EnrichmentTargetReference,
    EnrichmentTargetType,
)
from bridger.contracts.files import FileIndexPath, FileRecord

RepositorySearchKind = Literal["node", "community", "hyperedge", "file", "symbol"]
GraphDirection = Literal["incoming", "outgoing", "both"]


class CompositeEntityView(BaseModel):
    """One deterministic graph entity and its exactly targeted enrichment."""

    model_config = ConfigDict(extra="forbid")

    target_type: EnrichmentTargetType
    target_ref: EnrichmentTargetReference
    deterministic: dict[str, JsonValue]
    enrichment: list[EnrichmentRecord] = Field(default_factory=list)


class RepositorySearchHit(BaseModel):
    """Bounded discovery result for one existing structured repository entity."""

    model_config = ConfigDict(extra="forbid")

    kind: RepositorySearchKind
    ref: EnrichmentTargetReference
    label: str = Field(min_length=1)
    source_path: FileIndexPath | None = None
    score: float | None = Field(default=None, ge=0, le=100)


class GraphTraversalView(BaseModel):
    """Bounded graph materialization with an explicit completeness signal.

    ``truncated`` is true when eligible graph topology was omitted because a
    configured traversal or materialization bound prevented exhaustive
    representation. It is false when no known eligible topology was omitted
    under the requested traversal constraints.
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[CompositeEntityView] = Field(default_factory=list)
    edges: list[CompositeEntityView] = Field(default_factory=list)
    hyperedges: list[CompositeEntityView] = Field(default_factory=list)
    truncated: bool = False


class GraphCommunityView(BaseModel):
    """Bounded community membership and its internal and external connections."""

    model_config = ConfigDict(extra="forbid")

    community: CompositeEntityView
    members: list[CompositeEntityView] = Field(default_factory=list)
    internal_edges: list[CompositeEntityView] = Field(default_factory=list)
    cross_community_edges: list[CompositeEntityView] = Field(default_factory=list)
    truncated: bool = False


class FileOverview(BaseModel):
    """Small Layer 1-grounded view of one file's indexed associations."""

    model_config = ConfigDict(extra="forbid")

    file: FileRecord
    symbol_ids: list[str] = Field(default_factory=list)
    graph_node_ids: list[str] = Field(default_factory=list)
    symbols_truncated: bool = False
    graph_nodes_truncated: bool = False


class FileIndexListing(BaseModel):
    """One bounded slice of the pinned canonical FileIndex."""

    model_config = ConfigDict(extra="forbid")

    files: tuple[FileRecord, ...] = ()
    truncated: bool = False


class SourceContentMatch(BaseModel):
    """One line-addressable match from authorized repository source content."""

    model_config = ConfigDict(extra="forbid")

    path: FileIndexPath
    line_number: int = Field(ge=1)
    line_text: str
    context_start_line: int = Field(ge=1)
    context_end_line: int = Field(ge=1)
    context: str
    source_truncated: bool = False


__all__ = [
    "CompositeEntityView",
    "FileIndexListing",
    "FileOverview",
    "GraphCommunityView",
    "GraphDirection",
    "GraphTraversalView",
    "RepositorySearchHit",
    "RepositorySearchKind",
    "SourceContentMatch",
]
