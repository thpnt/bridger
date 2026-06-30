from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from bridger.models.file_index import (
    ArtifactModel,
    RepositoryPath,
    validate_repository_path,
)
from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    GraphSummaryCounts,
)

Checksum = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

REQUIRED_ARTIFACT_CHECKSUM_KEYS = {
    "file-index.json",
    "repo-context.json",
    "symbol-index.json",
    "repo-graph.json",
    "graph-summary.json",
}


class RepoDiscoveryRepo(ArtifactModel):
    root_name: str
    revision: str


class RepoDiscoveryArtifacts(ArtifactModel):
    file_index: RepositoryPath
    repo_context: RepositoryPath
    symbol_index: RepositoryPath
    repo_graph: RepositoryPath
    graph_summary: RepositoryPath

    _validate_paths = field_validator(
        "file_index",
        "repo_context",
        "symbol_index",
        "repo_graph",
        "graph_summary",
    )(validate_repository_path)


class RepoDiscoveryCompactContext(ArtifactModel):
    file_count: Annotated[int, Field(ge=0)]
    skipped_file_count: Annotated[int, Field(ge=0)]
    manifest_files: list[RepositoryPath]
    config_files: list[RepositoryPath]
    instruction_files: list[RepositoryPath]
    docs_files: list[RepositoryPath]
    ci_files: list[RepositoryPath]
    declared_entrypoints: list[DeclaredEntrypointSummary]
    graph_counts: GraphSummaryCounts

    _validate_paths = field_validator(
        "manifest_files",
        "config_files",
        "instruction_files",
        "docs_files",
        "ci_files",
    )(lambda paths: [validate_repository_path(path) for path in paths])

    @model_validator(mode="after")
    def sort_paths(self) -> "RepoDiscoveryCompactContext":
        self.manifest_files.sort()
        self.config_files.sort()
        self.instruction_files.sort()
        self.docs_files.sort()
        self.ci_files.sort()
        return self


class RepoDiscoveryBudgets(ArtifactModel):
    max_files_read: Annotated[int, Field(gt=0)] = 80
    max_excerpts: Annotated[int, Field(gt=0)] = 200
    max_grep_results: Annotated[int, Field(gt=0)] = 100
    max_symbol_results: Annotated[int, Field(gt=0)] = 100
    max_graph_neighbors: Annotated[int, Field(gt=0)] = 50
    max_file_excerpt_lines: Annotated[int, Field(gt=0)] = 200


class RepoDiscoveryArtifact(ArtifactModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    repo: RepoDiscoveryRepo
    artifacts: RepoDiscoveryArtifacts
    artifact_checksums: dict[str, Checksum]
    compact_context: RepoDiscoveryCompactContext
    available_tools: list[str]
    budgets: RepoDiscoveryBudgets

    @field_validator("artifact_checksums")
    @classmethod
    def validate_artifact_checksums(
        cls, checksums: dict[str, Checksum]
    ) -> dict[str, Checksum]:
        if set(checksums) != REQUIRED_ARTIFACT_CHECKSUM_KEYS:
            raise ValueError("checksums must represent all required prior artifacts")
        return checksums
