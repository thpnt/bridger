from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


class GraphNodeKind(StrEnum):
    DIRECTORY = "directory"
    FILE = "file"
    SYMBOL = "symbol"
    MANIFEST_ENTRY = "manifest_entry"
    FRAMEWORK_PATTERN = "framework_pattern"


class GraphEdgeKind(StrEnum):
    CONTAINS = "contains"
    DECLARES_SYMBOL = "declares_symbol"
    IMPORTS = "imports"
    DECLARES_ENTRYPOINT = "declares_entrypoint"
    MATCHES_PATH_PATTERN = "matches_path_pattern"


class GraphNode(ArtifactModel):
    id: NonEmptyString
    kind: GraphNodeKind
    path: RepositoryPath | None = None
    symbol_id: NonEmptyString | None = None
    key: NonEmptyString | None = None

    @field_validator("path")
    @classmethod
    def validate_optional_path(cls, path: str | None) -> str | None:
        return validate_repository_path(path) if path is not None else None

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "GraphNode":
        if (
            self.kind
            in {
                GraphNodeKind.DIRECTORY,
                GraphNodeKind.FILE,
                GraphNodeKind.MANIFEST_ENTRY,
            }
            and self.path is None
        ):
            raise ValueError(f"{self.kind.value} nodes require path")
        if self.kind is GraphNodeKind.SYMBOL and self.symbol_id is None:
            raise ValueError("symbol nodes require symbol_id")
        if self.kind is GraphNodeKind.MANIFEST_ENTRY and self.key is None:
            raise ValueError("manifest_entry nodes require key")
        return self


class GraphEdge(ArtifactModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_id: NonEmptyString = Field(
        validation_alias=AliasChoices("from_id", "from"), serialization_alias="from"
    )
    to_id: NonEmptyString = Field(
        validation_alias=AliasChoices("to_id", "to"), serialization_alias="to"
    )
    kind: GraphEdgeKind
    import_text: NonEmptyString | None = None


class RepoGraphUnresolvedImport(ArtifactModel):
    from_path: RepositoryPath
    import_text: NonEmptyString
    reason: NonEmptyString

    _validate_from_path = field_validator("from_path")(validate_repository_path)


class RepoGraphArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    unresolved_imports: list[RepoGraphUnresolvedImport] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_and_sort_graph(self) -> "RepoGraphArtifact":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node ids must be unique")
        known_ids = set(node_ids)
        if any(
            edge.from_id not in known_ids or edge.to_id not in known_ids
            for edge in self.edges
        ):
            raise ValueError("graph edges must reference existing nodes")
        self.nodes.sort(key=lambda node: (node.kind.value, node.id))
        self.edges.sort(
            key=lambda edge: (
                edge.kind.value,
                edge.from_id,
                edge.to_id,
                edge.import_text or "",
            )
        )
        self.unresolved_imports.sort(
            key=lambda item: (item.from_path, item.import_text, item.reason)
        )
        return self
