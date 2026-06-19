from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from bridger.deterministic.repo_discovery.checksums import artifact_checksums
from bridger.deterministic.repo_discovery.compact_context import extract_compact_context
from bridger.deterministic.repo_discovery.git import get_git_revision
from bridger.models.file_index import FileIndexArtifact
from bridger.models.graph_summary import GraphSummaryArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.repo_discovery import (
    RepoDiscoveryArtifact,
    RepoDiscoveryArtifacts,
    RepoDiscoveryBudgets,
    RepoDiscoveryRepo,
)
from bridger.models.repo_graph import RepoGraphArtifact
from bridger.models.symbol_index import SymbolIndexArtifact

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)

ARTIFACT_PATHS = RepoDiscoveryArtifacts(
    file_index=".bridger/artifacts/file-index.json",
    repo_context=".bridger/artifacts/repo-context.json",
    symbol_index=".bridger/artifacts/symbol-index.json",
    repo_graph=".bridger/artifacts/repo-graph.json",
    graph_summary=".bridger/artifacts/graph-summary.json",
)

AVAILABLE_TOOLS = [
    "inspect_repo_discovery",
    "list_files",
    "list_tree",
    "search_paths",
    "grep_contents",
    "read_file_excerpt",
    "inspect_manifest",
    "list_config_files",
    "list_docs_files",
    "list_instruction_files",
    "list_ci_files",
    "search_symbols",
    "list_symbols",
    "get_symbol",
    "read_symbol_excerpt",
    "get_file_overview",
    "get_graph_neighbors",
    "get_reverse_imports",
    "list_file_imports",
    "list_declared_entrypoints",
    "inspect_graph_summary",
    "validate_paths",
]


class RepoDiscoveryBuildError(RuntimeError):
    pass


def build_repo_discovery(
    file_index: FileIndexArtifact,
    repo_context: RepoContextArtifact,
    graph_summary: GraphSummaryArtifact,
    artifact_checksum_values: dict[str, str],
    *,
    root_name: str,
    revision: str,
    generated_at: datetime | None = None,
) -> RepoDiscoveryArtifact:
    return RepoDiscoveryArtifact(
        generated_at=generated_at or datetime.now(UTC),
        repo=RepoDiscoveryRepo(root_name=root_name, revision=revision),
        artifacts=ARTIFACT_PATHS,
        artifact_checksums=artifact_checksum_values,
        compact_context=extract_compact_context(
            file_index, repo_context, graph_summary
        ),
        available_tools=AVAILABLE_TOOLS,
        budgets=RepoDiscoveryBudgets(),
    )


def build_repo_discovery_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> RepoDiscoveryArtifact:
    root = repo_root.resolve()
    artifact_files = {
        "file-index.json": root / ARTIFACT_PATHS.file_index,
        "repo-context.json": root / ARTIFACT_PATHS.repo_context,
        "symbol-index.json": root / ARTIFACT_PATHS.symbol_index,
        "repo-graph.json": root / ARTIFACT_PATHS.repo_graph,
        "graph-summary.json": root / ARTIFACT_PATHS.graph_summary,
    }

    file_index = _load_artifact(artifact_files["file-index.json"], FileIndexArtifact)
    repo_context = _load_artifact(
        artifact_files["repo-context.json"], RepoContextArtifact
    )
    _load_artifact(artifact_files["symbol-index.json"], SymbolIndexArtifact)
    _load_artifact(artifact_files["repo-graph.json"], RepoGraphArtifact)
    graph_summary = _load_artifact(
        artifact_files["graph-summary.json"], GraphSummaryArtifact
    )

    try:
        checksums = artifact_checksums(artifact_files)
    except OSError as error:
        raise RepoDiscoveryBuildError(
            f"Could not checksum required artifact: {error}"
        ) from error

    return build_repo_discovery(
        file_index,
        repo_context,
        graph_summary,
        checksums,
        root_name=root.name,
        revision=get_git_revision(root),
        generated_at=generated_at,
    )


def _load_artifact(path: Path, model: type[ArtifactT]) -> ArtifactT:
    if not path.is_file():
        raise RepoDiscoveryBuildError(f"Required artifact is missing: {path.name}")
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise RepoDiscoveryBuildError(
            f"Required artifact is invalid: {path.name}: {error}"
        ) from error
