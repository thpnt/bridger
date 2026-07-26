import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from bridger.deterministic.file_index.ignore import (
    file_skip_reason,
    is_explicitly_excluded,
    is_gitignored,
    load_gitignore,
)
from bridger.deterministic.file_index.metadata import (
    collect_file_metadata,
)
from bridger.models.file_index import (
    ContentType,
    FileIndexArtifact,
    FileIndexDiagnostic,
    FileIndexStats,
    IndexedFile,
    ReadPolicy,
    SkippedFile,
    SkipReason,
)

MAX_INDEXED_FILE_BYTES = 1_000_000


def _repository_entries(repo_root: Path) -> list[Path]:
    entries: list[Path] = []
    pending = [repo_root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for child in children:
            entries.append(child)
            if child.is_dir() and not child.is_symlink():
                pending.append(child)
    return entries


def _relative_path(repo_root: Path, path: Path) -> PurePosixPath:
    return PurePosixPath(path.relative_to(repo_root).as_posix())


def _skipped(path: PurePosixPath, reason: SkipReason) -> SkippedFile:
    return SkippedFile(path=path.as_posix(), skip_reason=reason)


def _git_paths(
    repo_root: Path, revision: str
) -> tuple[
    str | None,
    list[PurePosixPath],
    int,
    list[FileIndexDiagnostic],
]:
    diagnostics: list[FileIndexDiagnostic] = []
    try:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
        )
        if resolved.returncode != 0 or not resolved.stdout.strip():
            raise OSError("revision could not be resolved")
        resolved_revision = resolved.stdout.strip()
        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", resolved_revision],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if tracked.returncode != 0:
            raise OSError("tracked file listing failed")
        paths = [
            PurePosixPath(value.decode("utf-8"))
            for value in tracked.stdout.split(b"\0")
            if value
        ]
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        untracked_count = (
            len([value for value in untracked.stdout.split(b"\0") if value])
            if untracked.returncode == 0
            else 0
        )
        return resolved_revision, sorted(paths), untracked_count, diagnostics
    except (OSError, UnicodeDecodeError):
        diagnostics.append(
            FileIndexDiagnostic(
                code="git_revision_unavailable",
                message=(
                    f"Could not inventory Git revision {revision!r}; used the "
                    "non-Git filesystem fallback."
                ),
            )
        )
        return None, [], 0, diagnostics


def _fallback_paths(repo_root: Path) -> list[PurePosixPath]:
    paths: list[PurePosixPath] = []
    for path in _repository_entries(repo_root):
        if path.is_dir():
            continue
        paths.append(_relative_path(repo_root, path))
    return sorted(paths)


def _metadata_only(
    path: PurePosixPath,
    *,
    reason: SkipReason,
    size_bytes: int = 0,
    is_symlink: bool = False,
) -> IndexedFile:
    return IndexedFile(
        path=path.as_posix(),
        extension=Path(path.name).suffix,
        size_bytes=size_bytes,
        line_count=0,
        sha256=None,
        is_binary=False,
        is_symlink=is_symlink,
        detected_encoding="unknown",
        content_type=(ContentType.SYMLINK if is_symlink else ContentType.UNKNOWN),
        read_policy=ReadPolicy.METADATA_ONLY,
        read_policy_reason=reason,
    )


def build_file_index_for_project(
    repo_root: Path,
    *,
    max_file_bytes: int = MAX_INDEXED_FILE_BYTES,
    revision: str = "HEAD",
    generated_at: datetime | None = None,
) -> FileIndexArtifact:
    root = repo_root.resolve()
    gitignore = load_gitignore(root)
    included_files: list[IndexedFile] = []
    skipped_files: list[SkippedFile] = []
    diagnostics: list[FileIndexDiagnostic] = []

    resolved_revision, tracked_paths, untracked_count, git_diagnostics = _git_paths(
        root, revision
    )
    diagnostics.extend(git_diagnostics)
    if resolved_revision is None:
        tracked_paths = _fallback_paths(root)
    if gitignore is None and (root / ".gitignore").is_file():
        diagnostics.append(
            FileIndexDiagnostic(
                code="gitignore_unreadable",
                message="The root .gitignore could not be read as UTF-8.",
            )
        )

    for relative_path in tracked_paths:
        path = root / Path(*relative_path.parts)
        ignored_reason = file_skip_reason(relative_path)

        if is_explicitly_excluded(relative_path):
            skipped_files.append(_skipped(relative_path, SkipReason.BRIDGER_DIRECTORY))
            continue

        if path.is_symlink():
            try:
                size_bytes = path.lstat().st_size
            except OSError:
                size_bytes = 0
            included_files.append(
                _metadata_only(
                    relative_path,
                    reason=SkipReason.SYMLINK_UNSUPPORTED,
                    size_bytes=size_bytes,
                    is_symlink=True,
                )
            )
            continue

        if not path.is_file():
            included_files.append(
                _metadata_only(relative_path, reason=SkipReason.READ_ERROR)
            )
            continue

        try:
            metadata = collect_file_metadata(path, relative_path)
            policy_reason = ignored_reason
            if policy_reason is None and is_gitignored(gitignore, relative_path):
                policy_reason = SkipReason.GITIGNORED
            if policy_reason is None and metadata.size_bytes > max_file_bytes:
                policy_reason = SkipReason.LARGE_FILE
            if policy_reason is None and metadata.is_binary:
                policy_reason = SkipReason.BINARY_FILE
            if policy_reason is None and metadata.content_type is ContentType.UNKNOWN:
                policy_reason = SkipReason.UNSUPPORTED_ENCODING

            if policy_reason is None:
                included_files.append(metadata)
            else:
                included_files.append(
                    metadata.model_copy(
                        update={
                            "read_policy": ReadPolicy.METADATA_ONLY,
                            "read_policy_reason": policy_reason,
                        }
                    )
                )
        except OSError:
            included_files.append(
                _metadata_only(relative_path, reason=SkipReason.READ_ERROR)
            )

    included_files.sort(key=lambda file: file.path)
    skipped_files.sort(key=lambda file: file.path)
    diagnostics.extend(
        FileIndexDiagnostic(
            code="untracked_files_excluded",
            message="Untracked files are excluded from the V0 inventory.",
        )
        for _ in range(1 if untracked_count else 0)
    )
    if skipped_files:
        diagnostics.append(
            FileIndexDiagnostic(
                code="inventory_membership_exclusions",
                message="Tracked paths under .bridger/** are excluded explicitly.",
            )
        )
    return FileIndexArtifact(
        generated_at=generated_at or datetime.now(UTC),
        repo_root_name=root.name,
        revision=resolved_revision or "unknown",
        files=included_files,
        skipped_files=skipped_files,
        stats=FileIndexStats(
            files_seen=len(included_files) + len(skipped_files),
            files_included=len(included_files),
            files_skipped=len(skipped_files),
            total_included_bytes=sum(file.size_bytes for file in included_files),
            files_tracked=len(tracked_paths),
            files_readable=sum(
                file.read_policy is ReadPolicy.READABLE for file in included_files
            ),
            files_metadata_only=sum(
                file.read_policy is ReadPolicy.METADATA_ONLY
                for file in included_files
            ),
            files_excluded=len(skipped_files),
            untracked_files_excluded=untracked_count,
        ),
        diagnostics=sorted(
            diagnostics, key=lambda item: (item.code, item.path or "", item.message)
        ),
    )
