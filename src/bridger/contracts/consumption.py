"""Typed contracts for the simplified Bridger V0 consumption interface."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bridger.contracts.files import FileIndexPath
from bridger.contracts.symbols import SymbolRecord


class ConsumptionRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository_id: str = Field(min_length=1)
    repository_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    graph_snapshot_id: str = Field(min_length=1)
    enrichment_overlay_id: str = Field(min_length=1)


class Completeness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_truncated: bool = False
    graph_truncated: bool = False


class BrainContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    heading: str | None = Field(default=None, min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    semantic_owner: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> "BrainContext":
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        return self


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    symbol_ids: list[str] = Field(default_factory=list)
    source_path: FileIndexPath | None = None
    source_start_line: int | None = Field(default=None, ge=1)
    source_end_line: int | None = Field(default=None, ge=1)
    community_id: int | None = None

    @model_validator(mode="after")
    def validate_source_range(self) -> "GraphNode":
        if (self.source_start_line is None) != (self.source_end_line is None):
            raise ValueError(
                "source_start_line and source_end_line must be provided together"
            )

        if self.source_start_line is not None:
            if self.source_path is None:
                raise ValueError("source line range requires source_path")
            if self.source_end_line < self.source_start_line:
                raise ValueError(
                    "source_end_line must not be before source_start_line"
                )

        return self


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    evidence: str | None = Field(default=None, min_length=1)
    evidence_path: FileIndexPath | None = None
    evidence_start_line: int | None = Field(default=None, ge=1)
    evidence_end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_evidence_range(self) -> "GraphEdge":
        if (self.evidence_start_line is None) != (self.evidence_end_line is None):
            raise ValueError(
                "evidence_start_line and evidence_end_line must be provided together"
            )

        if self.evidence_start_line is not None:
            if self.evidence_path is None:
                raise ValueError("evidence line range requires evidence_path")
            if self.evidence_end_line < self.evidence_start_line:
                raise ValueError(
                    "evidence_end_line must not be before evidence_start_line"
                )

        return self


class GraphCommunity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    community_id: int
    label: str = Field(min_length=1)


class UnderstandGraphContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seed_node_ids: list[str] = Field(default_factory=list)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    communities: list[GraphCommunity] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context(self) -> "UnderstandGraphContext":
        node_ids = {node.node_id for node in self.nodes}

        if any(seed_id not in node_ids for seed_id in self.seed_node_ids):
            raise ValueError("every seed_node_id must exist in nodes")

        if any(
            edge.source_node_id not in node_ids
            or edge.target_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("every graph edge endpoint must exist in nodes")

        community_ids = {community.community_id for community in self.communities}

        if any(
            node.community_id is not None
            and node.community_id not in community_ids
            for node in self.nodes
        ):
            raise ValueError("every referenced community_id must exist in communities")

        return self


class UnderstandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    revision: ConsumptionRevision
    brain_context: list[BrainContext] = Field(default_factory=list)
    graph_context: UnderstandGraphContext
    completeness: Completeness
    warnings: list[str] = Field(default_factory=list)


ImpactResolutionFailure = Literal["not_found", "ambiguous", "not_in_graph"]


class ResolvedImpactRoot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selector: str = Field(min_length=1)
    graph_node_ids: list[str] = Field(min_length=1)
    symbol: SymbolRecord | None = None


class ImpactResolutionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selector: str = Field(min_length=1)
    reason: ImpactResolutionFailure
    candidates: list[SymbolRecord] = Field(default_factory=list)


class ImpactNode(GraphNode):
    depth: int = Field(ge=0)


class ImpactGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[ImpactNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    communities: list[GraphCommunity] = Field(default_factory=list)
    important_node_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "ImpactGraph":
        node_ids = {node.node_id for node in self.nodes}

        if any(
            edge.source_node_id not in node_ids
            or edge.target_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("every graph edge endpoint must exist in nodes")

        if any(node_id not in node_ids for node_id in self.important_node_ids):
            raise ValueError("every important_node_id must exist in nodes")

        community_ids = {community.community_id for community in self.communities}

        if any(
            node.community_id is not None
            and node.community_id not in community_ids
            for node in self.nodes
        ):
            raise ValueError("every referenced community_id must exist in communities")

        return self


class ImpactResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: ConsumptionRevision
    requested_symbols: list[str] = Field(min_length=1)
    resolved_roots: list[ResolvedImpactRoot] = Field(default_factory=list)
    resolution_issues: list[ImpactResolutionIssue] = Field(default_factory=list)
    affected_graph: ImpactGraph | None = None
    brain_enrichment: list[BrainContext] = Field(default_factory=list)
    completeness: Completeness
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "ImpactResult":
        if self.resolution_issues:
            if self.affected_graph is not None:
                raise ValueError("affected_graph must be absent when resolution fails")
            if self.brain_enrichment:
                raise ValueError(
                    "brain_enrichment must be empty when resolution fails"
                )
        elif self.affected_graph is None:
            raise ValueError("affected_graph is required after successful resolution")

        return self


__all__ = [
    "BrainContext",
    "Completeness",
    "ConsumptionRevision",
    "GraphCommunity",
    "GraphEdge",
    "GraphNode",
    "ImpactGraph",
    "ImpactNode",
    "ImpactResolutionFailure",
    "ImpactResolutionIssue",
    "ImpactResult",
    "ResolvedImpactRoot",
    "UnderstandGraphContext",
    "UnderstandResult",
]
