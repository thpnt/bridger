from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)

Count = Annotated[int, Field(ge=0)]


class GraphSummaryCounts(ArtifactModel):
    directory_nodes: Count = 0
    file_nodes: Count = 0
    symbol_nodes: Count = 0
    manifest_entry_nodes: Count = 0
    framework_pattern_nodes: Count = 0
    contains_edges: Count = 0
    declares_symbol_edges: Count = 0
    import_edges: Count = 0
    declares_entrypoint_edges: Count = 0
    matches_path_pattern_edges: Count = 0
    unresolved_imports: Count = 0


class FanInFile(ArtifactModel):
    path: RepositoryPath
    incoming_edges: Annotated[int, Field(ge=1)]

    _validate_path = field_validator("path")(validate_repository_path)


class FanOutFile(ArtifactModel):
    path: RepositoryPath
    outgoing_edges: Annotated[int, Field(ge=1)]

    _validate_path = field_validator("path")(validate_repository_path)


class DeclaredEntrypointSummary(ArtifactModel):
    path: RepositoryPath
    source: str

    _validate_path = field_validator("path")(validate_repository_path)


class UnresolvedImportSample(ArtifactModel):
    from_path: RepositoryPath
    import_text: str
    reason: str

    _validate_from_path = field_validator("from_path")(validate_repository_path)


class GraphSummaryArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    counts: GraphSummaryCounts
    top_fan_in_files: list[FanInFile] = Field(default_factory=list)
    top_fan_out_files: list[FanOutFile] = Field(default_factory=list)
    declared_entrypoints: list[DeclaredEntrypointSummary] = Field(default_factory=list)
    unresolved_imports_sample: list[UnresolvedImportSample] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def sort_output(self) -> "GraphSummaryArtifact":
        self.top_fan_in_files.sort(key=lambda item: (-item.incoming_edges, item.path))
        self.top_fan_out_files.sort(key=lambda item: (-item.outgoing_edges, item.path))
        self.declared_entrypoints.sort(key=lambda item: (item.path, item.source))
        self.unresolved_imports_sample.sort(
            key=lambda item: (item.from_path, item.import_text, item.reason)
        )
        return self
