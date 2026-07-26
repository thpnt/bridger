from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from bridger.deterministic.context_plan_bootstrap.checksums import artifact_checksums
from bridger.deterministic.context_plan_bootstrap.compact_context import (
    extract_compact_context,
)
from bridger.deterministic.context_plan_bootstrap.git import get_git_revision
from bridger.models.context_plan_bootstrap import (
    ContextPlanBootstrapArtifact,
    ContextPlanBootstrapArtifacts,
    ContextPlanBootstrapBudgets,
    ContextPlanBootstrapRepo,
)
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.symbol_index import SymbolIndexArtifact

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)

ARTIFACT_PATHS = ContextPlanBootstrapArtifacts(
    file_index=".bridger/artifacts/file-index.json",
    repo_context=".bridger/artifacts/repo-context.json",
    symbol_index=".bridger/artifacts/symbol-index.json",
)

AVAILABLE_TOOLS = [
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
    "validate_paths",
]


class ContextPlanBootstrapBuildError(RuntimeError):
    pass


def build_context_plan_bootstrap(
    file_index: FileIndexArtifact,
    repo_context: RepoContextArtifact,
    artifact_checksum_values: dict[str, str],
    *,
    root_name: str,
    revision: str,
    generated_at: datetime | None = None,
) -> ContextPlanBootstrapArtifact:
    return ContextPlanBootstrapArtifact(
        generated_at=generated_at or datetime.now(UTC),
        repo=ContextPlanBootstrapRepo(root_name=root_name, revision=revision),
        artifacts=ARTIFACT_PATHS,
        artifact_checksums=artifact_checksum_values,
        compact_context=extract_compact_context(file_index, repo_context),
        available_tools=AVAILABLE_TOOLS,
        budgets=ContextPlanBootstrapBudgets(),
    )


def build_context_plan_bootstrap_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> ContextPlanBootstrapArtifact:
    root = repo_root.resolve()
    artifact_files = {
        "file-index.json": root / ARTIFACT_PATHS.file_index,
        "repo-context.json": root / ARTIFACT_PATHS.repo_context,
        "symbol-index.json": root / ARTIFACT_PATHS.symbol_index,
    }

    file_index = _load_artifact(artifact_files["file-index.json"], FileIndexArtifact)
    repo_context = _load_artifact(
        artifact_files["repo-context.json"], RepoContextArtifact
    )
    _load_artifact(artifact_files["symbol-index.json"], SymbolIndexArtifact)

    try:
        checksums = artifact_checksums(artifact_files)
    except OSError as error:
        raise ContextPlanBootstrapBuildError(
            f"Could not checksum required artifact: {error}"
        ) from error

    return build_context_plan_bootstrap(
        file_index,
        repo_context,
        checksums,
        root_name=root.name,
        revision=get_git_revision(root),
        generated_at=generated_at,
    )


def _load_artifact(path: Path, model: type[ArtifactT]) -> ArtifactT:
    if not path.is_file():
        raise ContextPlanBootstrapBuildError(
            f"Required artifact is missing: {path.name}"
        )
    try:
        return model.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise ContextPlanBootstrapBuildError(
            f"Required artifact is invalid: {path.name}: {error}"
        ) from error
