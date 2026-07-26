from datetime import UTC, datetime
from pathlib import Path

from bridger.deterministic.repo_context.detectors import detect_file_kind
from bridger.deterministic.repo_context.parsers import (
    ManifestParseFailure,
    parse_manifest,
)
from bridger.models.file_index import FileIndexArtifact, ReadPolicy
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
    ManifestParseError,
    RepoContextArtifact,
)


def _read_indexed_file(repo_root: Path, relative_path: str) -> bytes:
    path = repo_root / relative_path
    current_path = repo_root
    for part in Path(relative_path).parts:
        current_path /= part
        if current_path.is_symlink():
            raise OSError("indexed path is no longer a safe repository file")
    resolved_path = path.resolve(strict=True)
    if not resolved_path.is_relative_to(repo_root):
        raise OSError("indexed path is no longer a safe repository file")
    return resolved_path.read_bytes()


def build_repo_context_for_project(
    repo_root: Path,
    *,
    generated_at: datetime | None = None,
) -> RepoContextArtifact:
    root = repo_root.resolve()
    file_index_path = root / ".bridger" / "artifacts" / "file-index.json"
    file_index = FileIndexArtifact.model_validate_json(file_index_path.read_bytes())
    manifests: list[ManifestFile] = []
    config_files: list[ConfigFile] = []
    ci_files: list[CiFile] = []
    instruction_files: list[InstructionFile] = []
    docs_files: list[DocsFile] = []
    parse_errors: list[ManifestParseError] = []
    processed_paths: set[str] = set()

    for indexed_file in file_index.files:
        if indexed_file.path in processed_paths:
            continue
        processed_paths.add(indexed_file.path)
        if indexed_file.read_policy is not ReadPolicy.READABLE:
            continue
        kind = detect_file_kind(indexed_file.path)
        if isinstance(kind, ManifestKind):
            parsed = {}
            try:
                parsed = parse_manifest(
                    kind, _read_indexed_file(root, indexed_file.path)
                )
            except ManifestParseFailure as error:
                parse_errors.append(
                    ManifestParseError(path=indexed_file.path, error=error.error)
                )
            except OSError:
                parse_errors.append(
                    ManifestParseError(path=indexed_file.path, error="read_error")
                )
            manifests.append(
                ManifestFile(path=indexed_file.path, kind=kind, parsed=parsed)
            )
        elif isinstance(kind, ConfigKind):
            config_files.append(ConfigFile(path=indexed_file.path, kind=kind))
        elif isinstance(kind, CiKind):
            ci_files.append(CiFile(path=indexed_file.path, kind=kind))
        elif isinstance(kind, InstructionKind):
            instruction_files.append(InstructionFile(path=indexed_file.path, kind=kind))
        elif isinstance(kind, DocsKind):
            docs_files.append(DocsFile(path=indexed_file.path, kind=kind))

    return RepoContextArtifact(
        generated_at=generated_at or datetime.now(UTC),
        manifests=sorted(manifests, key=lambda file: file.path),
        config_files=sorted(config_files, key=lambda file: file.path),
        ci_files=sorted(ci_files, key=lambda file: file.path),
        instruction_files=sorted(instruction_files, key=lambda file: file.path),
        docs_files=sorted(docs_files, key=lambda file: file.path),
        parse_errors=sorted(parse_errors, key=lambda error: error.path),
    )
