from pathlib import Path

from bridger.artifacts import write_artifact
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.repo_context import build_repo_context_for_project
from bridger.models.file_index import FileIndexArtifact, SkipReason
from bridger.models.repo_context import ManifestKind


def write_file(root: Path, path: str, content: str = "") -> None:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)


def write_file_index(root: Path) -> None:
    artifact = build_file_index_for_project(root)
    write_artifact(root / ".bridger/artifacts/file-index.json", artifact)


def test_builder_detects_files_from_supported_ecosystems(tmp_path: Path) -> None:
    files = {
        "pyproject.toml": "[project]\nname = 'example'\n",
        "package.json": "{}",
        "composer.json": "{}",
        "go.mod": "module example.com/service\n",
        "tsconfig.json": "{}",
        "next.config.ts": "export default {}",
        "vite.config.ts": "export default {}",
        "phpunit.xml": "<phpunit />",
        "cmd/api/main.go": "package main",
        "README.md": "# Example",
        "AGENTS.md": "# Instructions",
        ".github/workflows/test.yml": "name: test",
    }
    for path, content in files.items():
        write_file(tmp_path, path, content)
    write_file_index(tmp_path)

    artifact = build_repo_context_for_project(tmp_path)

    detected_paths = {
        entry.path
        for entries in (
            artifact.manifests,
            artifact.config_files,
            artifact.ci_files,
            artifact.instruction_files,
            artifact.docs_files,
        )
        for entry in entries
    }
    assert detected_paths == set(files)
    assert [manifest.path for manifest in artifact.manifests] == sorted(
        manifest.path for manifest in artifact.manifests
    )


def test_builder_records_invalid_manifests_without_stopping(tmp_path: Path) -> None:
    write_file(tmp_path, "package.json", "{invalid")
    write_file(tmp_path, "pyproject.toml", "[invalid")
    write_file(tmp_path, "go.mod", 'module "unterminated')
    write_file_index(tmp_path)

    artifact = build_repo_context_for_project(tmp_path)

    assert [manifest.path for manifest in artifact.manifests] == [
        "go.mod",
        "package.json",
        "pyproject.toml",
    ]
    assert [(error.path, error.error) for error in artifact.parse_errors] == [
        ("go.mod", "invalid_go_mod"),
        ("package.json", "invalid_json"),
        ("pyproject.toml", "invalid_toml"),
    ]


def test_builder_does_not_rescan_for_files_absent_from_index(tmp_path: Path) -> None:
    write_file(tmp_path, "README.md", "# Indexed")
    write_file_index(tmp_path)
    write_file(tmp_path, "package.json", "{}")
    write_file(tmp_path, "tsconfig.json", "{}")

    artifact = build_repo_context_for_project(tmp_path)

    assert artifact.manifests == []
    assert artifact.config_files == []
    assert [docs.path for docs in artifact.docs_files] == ["README.md"]


def test_builder_never_includes_or_reads_skipped_files(tmp_path: Path) -> None:
    write_file(tmp_path, ".env", "SECRET=value")
    write_file(tmp_path, "secret/package.json", "value\0binary")
    write_file_index(tmp_path)

    file_index_path = tmp_path / ".bridger/artifacts/file-index.json"
    file_index = build_file_index_for_project(tmp_path)
    assert {file.skip_reason for file in file_index.skipped_files} >= {
        SkipReason.SENSITIVE_FILE,
        SkipReason.BINARY_FILE,
    }

    artifact = build_repo_context_for_project(tmp_path)

    assert artifact.manifests == []
    assert artifact.config_files == []
    assert artifact.parse_errors == []
    assert file_index_path.is_file()


def test_builder_reads_manifest_content_only_for_indexed_paths(tmp_path: Path) -> None:
    write_file(tmp_path, "package.json", '{"name": "indexed"}')
    write_file_index(tmp_path)
    write_file(tmp_path, "composer.json", '{"name": "not-indexed"}')

    artifact = build_repo_context_for_project(tmp_path)

    assert [(manifest.path, manifest.kind) for manifest in artifact.manifests] == [
        ("package.json", ManifestKind.NODE_PACKAGE_JSON)
    ]
    assert artifact.manifests[0].parsed == {"name": "indexed"}


def test_builder_deduplicates_repeated_file_index_paths(tmp_path: Path) -> None:
    write_file(tmp_path, "package.json", "{}")
    write_file_index(tmp_path)
    file_index_path = tmp_path / ".bridger/artifacts/file-index.json"
    file_index = FileIndexArtifact.model_validate_json(file_index_path.read_bytes())
    duplicate_index = file_index.model_copy(
        update={"files": [file_index.files[0], file_index.files[0]]}
    )
    write_artifact(file_index_path, duplicate_index)

    artifact = build_repo_context_for_project(tmp_path)

    assert [manifest.path for manifest in artifact.manifests] == ["package.json"]
