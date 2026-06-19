from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bridger.artifacts import write_artifact
from bridger.deterministic.repo_discovery import (
    RepoDiscoveryBuildError,
    build_repo_discovery_for_project,
)
from bridger.deterministic.repo_discovery.builder import AVAILABLE_TOOLS
from bridger.deterministic.repo_discovery.checksums import (
    artifact_checksums,
    sha256_file,
)
from bridger.deterministic.repo_discovery.compact_context import (
    extract_compact_context,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
    SkippedFile,
    SkipReason,
)
from bridger.models.graph_summary import (
    DeclaredEntrypointSummary,
    GraphSummaryArtifact,
    GraphSummaryCounts,
)
from bridger.models.repo_context import (
    CiFile,
    CiKind,
    ConfigFile,
    ConfigKind,
    DocsFile,
    DocsKind,
    InstructionFile,
    InstructionKind,
    ManifestFile,
    ManifestKind,
    RepoContextArtifact,
)
from bridger.models.repo_discovery import (
    RepoDiscoveryArtifact,
    RepoDiscoveryArtifacts,
    RepoDiscoveryBudgets,
    RepoDiscoveryCompactContext,
    RepoDiscoveryRepo,
)
from bridger.models.repo_graph import RepoGraphArtifact
from bridger.models.symbol_index import SymbolIndexArtifact

GENERATED_AT = datetime(2026, 6, 19, tzinfo=UTC)
REQUIRED_ARTIFACT_NAMES = [
    "file-index.json",
    "repo-context.json",
    "symbol-index.json",
    "repo-graph.json",
    "graph-summary.json",
]
REQUIRED_TOOLS = {
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
}


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
        ci_files=[
            CiFile(
                path=".github/workflows/test.yml",
                kind=CiKind.GITHUB_ACTIONS_WORKFLOW,
            )
        ],
        instruction_files=[
            InstructionFile(path="AGENTS.md", kind=InstructionKind.AGENT_INSTRUCTIONS)
        ],
        docs_files=[DocsFile(path="README.md", kind=DocsKind.README)],
        parse_errors=[],
    )


def make_graph_summary() -> GraphSummaryArtifact:
    return GraphSummaryArtifact(
        generated_at=GENERATED_AT,
        counts=GraphSummaryCounts(file_nodes=1, symbol_nodes=2, import_edges=3),
        declared_entrypoints=[
            DeclaredEntrypointSummary(
                path="app.py", source="pyproject.toml:project.scripts.app"
            )
        ],
    )


def write_prior_artifacts(root: Path) -> dict[str, Path]:
    artifact_dir = root / ".bridger" / "artifacts"
    artifacts = {
        "file-index.json": make_file_index(),
        "repo-context.json": make_repo_context(),
        "symbol-index.json": SymbolIndexArtifact(
            generated_at=GENERATED_AT, symbols=[], parse_errors=[]
        ),
        "repo-graph.json": RepoGraphArtifact(generated_at=GENERATED_AT),
        "graph-summary.json": make_graph_summary(),
    }
    paths: dict[str, Path] = {}
    for name, artifact in artifacts.items():
        path = artifact_dir / name
        write_artifact(path, artifact)
        paths[name] = path
    return paths


def make_discovery_artifact() -> RepoDiscoveryArtifact:
    return RepoDiscoveryArtifact(
        generated_at=GENERATED_AT,
        repo=RepoDiscoveryRepo(root_name="repo", revision="unknown"),
        artifacts=RepoDiscoveryArtifacts(
            file_index=".bridger/artifacts/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
            repo_graph=".bridger/artifacts/repo-graph.json",
            graph_summary=".bridger/artifacts/graph-summary.json",
        ),
        artifact_checksums={name: "0" * 64 for name in REQUIRED_ARTIFACT_NAMES},
        compact_context=RepoDiscoveryCompactContext(
            file_count=0,
            skipped_file_count=0,
            manifest_files=[],
            config_files=[],
            instruction_files=[],
            docs_files=[],
            ci_files=[],
            declared_entrypoints=[],
            graph_counts=GraphSummaryCounts(),
        ),
        available_tools=[],
        budgets=RepoDiscoveryBudgets(),
    )


def test_valid_minimal_artifact_passes_validation() -> None:
    artifact = make_discovery_artifact()

    assert artifact.schema_version == 1


def test_absolute_artifact_paths_are_rejected() -> None:
    with pytest.raises(ValidationError, match="stay within the repository"):
        RepoDiscoveryArtifacts(
            file_index="/file-index.json",
            repo_context=".bridger/artifacts/repo-context.json",
            symbol_index=".bridger/artifacts/symbol-index.json",
            repo_graph=".bridger/artifacts/repo-graph.json",
            graph_summary=".bridger/artifacts/graph-summary.json",
        )


def test_required_fields_are_enforced() -> None:
    payload = make_discovery_artifact().model_dump()
    del payload["repo"]

    with pytest.raises(ValidationError, match="repo"):
        RepoDiscoveryArtifact.model_validate(payload)


def test_sha256_is_stable_and_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_bytes(b"first")
    first = sha256_file(path)

    assert first == sha256_file(path)

    path.write_bytes(b"second")

    assert sha256_file(path) != first


def test_checksums_represent_all_prior_artifacts(tmp_path: Path) -> None:
    paths = write_prior_artifacts(tmp_path)

    checksums = artifact_checksums(paths)

    assert set(checksums) == set(REQUIRED_ARTIFACT_NAMES)
    assert all(len(checksum) == 64 for checksum in checksums.values())


def test_compact_context_extracts_required_facts() -> None:
    context = extract_compact_context(
        make_file_index(), make_repo_context(), make_graph_summary()
    )

    assert context.file_count == 1
    assert context.skipped_file_count == 1
    assert context.manifest_files == ["pyproject.toml"]
    assert context.config_files == ["ruff.toml"]
    assert context.instruction_files == ["AGENTS.md"]
    assert context.docs_files == ["README.md"]
    assert context.ci_files == [".github/workflows/test.yml"]
    assert context.declared_entrypoints[0].path == "app.py"
    assert context.graph_counts.import_edges == 3


def test_discovery_contract_contains_only_factual_bootstrap_fields(
    tmp_path: Path,
) -> None:
    write_prior_artifacts(tmp_path)

    artifact = build_repo_discovery_for_project(tmp_path, generated_at=GENERATED_AT)
    payload = artifact.model_dump(mode="json")

    assert set(payload["artifacts"].values()) == {
        f".bridger/artifacts/{name}" for name in REQUIRED_ARTIFACT_NAMES
    }
    assert set(artifact.available_tools) == REQUIRED_TOOLS
    assert artifact.available_tools == AVAILABLE_TOOLS
    assert artifact.budgets == RepoDiscoveryBudgets()
    forbidden_fields = {
        "suggested_first_actions",
        "initial_hypotheses",
        "code_areas",
        "architecture_summary",
        "semantic_warnings",
        "business_domain_conclusions",
    }
    assert forbidden_fields.isdisjoint(payload)
    assert forbidden_fields.isdisjoint(payload["compact_context"])


@pytest.mark.parametrize("missing_name", REQUIRED_ARTIFACT_NAMES)
def test_missing_prior_artifact_fails_clearly(
    tmp_path: Path, missing_name: str
) -> None:
    paths = write_prior_artifacts(tmp_path)
    paths[missing_name].unlink()

    with pytest.raises(RepoDiscoveryBuildError, match=missing_name):
        build_repo_discovery_for_project(tmp_path)
    assert not (tmp_path / ".bridger" / "artifacts" / "repo-discovery.json").exists()


def test_invalid_prior_artifact_fails_clearly(tmp_path: Path) -> None:
    paths = write_prior_artifacts(tmp_path)
    paths["repo-context.json"].write_text("{}")

    with pytest.raises(RepoDiscoveryBuildError, match="repo-context.json"):
        build_repo_discovery_for_project(tmp_path)
    assert not (tmp_path / ".bridger" / "artifacts" / "repo-discovery.json").exists()


def test_non_git_repo_uses_unknown_revision(tmp_path: Path) -> None:
    write_prior_artifacts(tmp_path)

    artifact = build_repo_discovery_for_project(tmp_path)

    assert artifact.repo.revision == "unknown"
