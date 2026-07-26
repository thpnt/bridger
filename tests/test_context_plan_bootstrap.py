from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bridger.artifacts import write_artifact
from bridger.deterministic.context_plan_bootstrap import (
    ContextPlanBootstrapBuildError,
    build_context_plan_bootstrap_for_project,
)
from bridger.deterministic.context_plan_bootstrap.builder import AVAILABLE_TOOLS
from bridger.deterministic.context_plan_bootstrap.checksums import (
    artifact_checksums,
    sha256_file,
)
from bridger.deterministic.context_plan_bootstrap.compact_context import (
    extract_compact_context,
)
from bridger.models.context_plan_bootstrap import (
    ContextPlanBootstrapArtifact,
    ContextPlanBootstrapArtifacts,
    ContextPlanBootstrapBudgets,
    ContextPlanBootstrapRepo,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)
from bridger.models.repo_context import (
    ConfigFile,
    ConfigKind,
    ManifestFile,
    ManifestKind,
    RepoContextArtifact,
)
from bridger.models.symbol_index import SymbolIndexArtifact

GENERATED_AT = datetime(2026, 6, 19, tzinfo=UTC)
REQUIRED_ARTIFACT_NAMES = [
    "file-index.json",
    "repo-context.json",
    "symbol-index.json",
]


def make_file_index() -> FileIndexArtifact:
    return FileIndexArtifact(
        generated_at=GENERATED_AT,
        repo_root_name="repo",
        files=[
            IndexedFile(
                path="app.py",
                extension=".py",
                size_bytes=1,
                line_count=1,
                sha256="0" * 64,
                is_binary=False,
                is_symlink=False,
                detected_encoding="utf-8",
            )
        ],
        skipped_files=[SkippedFile(path=".env", skip_reason=SkipReason.SENSITIVE_FILE)],
        stats=FileIndexStats(
            files_seen=2,
            files_included=1,
            files_skipped=1,
            total_included_bytes=1,
        ),
    )


def make_repo_context() -> RepoContextArtifact:
    return RepoContextArtifact(
        generated_at=GENERATED_AT,
        manifests=[
            ManifestFile(
                path="pyproject.toml",
                kind=ManifestKind.PYTHON_PYPROJECT,
                parsed={},
            )
        ],
        config_files=[ConfigFile(path="ruff.toml", kind=ConfigKind.PYTHON_TOOL_CONFIG)],
        ci_files=[],
        instruction_files=[],
        docs_files=[],
        parse_errors=[],
    )


def write_prior_artifacts(root: Path) -> dict[str, Path]:
    artifact_dir = root / ".bridger" / "artifacts"
    artifacts = {
        "file-index.json": make_file_index(),
        "repo-context.json": make_repo_context(),
        "symbol-index.json": SymbolIndexArtifact(
            generated_at=GENERATED_AT, symbols=[], parse_errors=[]
        ),
    }
    paths: dict[str, Path] = {}
    for name, artifact in artifacts.items():
        path = artifact_dir / name
        write_artifact(path, artifact)
        paths[name] = path
    return paths


def make_bootstrap_artifact() -> ContextPlanBootstrapArtifact:
    return ContextPlanBootstrapArtifact(
        generated_at=GENERATED_AT,
        repo=ContextPlanBootstrapRepo(root_name="repo", revision="unknown"),
        artifacts=ContextPlanBootstrapArtifacts(
            file_index=".bridger/artifacts/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
        ),
        artifact_checksums={name: "0" * 64 for name in REQUIRED_ARTIFACT_NAMES},
        compact_context=extract_compact_context(make_file_index(), make_repo_context()),
        available_tools=AVAILABLE_TOOLS,
        budgets=ContextPlanBootstrapBudgets(),
    )


def test_valid_minimal_bootstrap_passes_validation() -> None:
    assert make_bootstrap_artifact().schema_version == 1


def test_absolute_artifact_paths_are_rejected() -> None:
    with pytest.raises(ValidationError, match="stay within the repository"):
        ContextPlanBootstrapArtifacts(
            file_index="/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
        )


def test_checksums_are_stable_and_cover_prior_artifacts(tmp_path: Path) -> None:
    paths = write_prior_artifacts(tmp_path)
    checksums = artifact_checksums(paths)

    assert set(checksums) == set(REQUIRED_ARTIFACT_NAMES)
    assert all(len(checksum) == 64 for checksum in checksums.values())
    first = sha256_file(paths["file-index.json"])
    assert first == sha256_file(paths["file-index.json"])


def test_compact_context_extracts_required_facts() -> None:
    context = extract_compact_context(make_file_index(), make_repo_context())

    assert context.file_count == 1
    assert context.skipped_file_count == 1
    assert context.manifest_files == ["pyproject.toml"]
    assert context.config_files == ["ruff.toml"]


def test_bootstrap_builder_references_three_prior_artifacts(tmp_path: Path) -> None:
    write_prior_artifacts(tmp_path)

    artifact = build_context_plan_bootstrap_for_project(
        tmp_path, generated_at=GENERATED_AT
    )

    assert set(artifact.artifact_checksums) == set(REQUIRED_ARTIFACT_NAMES)
    assert artifact.available_tools == AVAILABLE_TOOLS
    assert artifact.budgets == ContextPlanBootstrapBudgets()
    assert "repo-graph.json" not in artifact.model_dump_json()
    assert "graph-summary.json" not in artifact.model_dump_json()


@pytest.mark.parametrize("missing_name", REQUIRED_ARTIFACT_NAMES)
def test_missing_prior_artifact_fails_clearly(
    tmp_path: Path, missing_name: str
) -> None:
    paths = write_prior_artifacts(tmp_path)
    paths[missing_name].unlink()

    with pytest.raises(ContextPlanBootstrapBuildError, match=missing_name):
        build_context_plan_bootstrap_for_project(tmp_path)


def test_repo_discovery_artifact_is_not_created(tmp_path: Path) -> None:
    write_prior_artifacts(tmp_path)
    build_context_plan_bootstrap_for_project(tmp_path)

    assert not (tmp_path / ".bridger/artifacts/repo-discovery.json").exists()
