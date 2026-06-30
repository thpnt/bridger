from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from bridger.deterministic.file_index.ignore import file_skip_reason
from bridger.deterministic.file_index.metadata import (
    collect_file_metadata,
    has_binary_marker,
)
from bridger.models.file_index import (
    FileIndexArtifact,
    FileIndexStats,
    IndexedFile,
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


def build_file_index_for_project(
    repo_root: Path,
    *,
    max_file_bytes: int = MAX_INDEXED_FILE_BYTES,
    generated_at: datetime | None = None,
) -> FileIndexArtifact:
    root = repo_root.resolve()
    included_files: list[IndexedFile] = []
    skipped_files: list[SkippedFile] = []

    for path in _repository_entries(root):
        relative_path = _relative_path(root, path)
        ignored_reason = file_skip_reason(relative_path)

        if path.is_symlink():
            skipped_files.append(
                _skipped(
                    relative_path, ignored_reason or SkipReason.SYMLINK_UNSUPPORTED
                )
            )
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            skipped_files.append(_skipped(relative_path, SkipReason.IGNORED_FILE))
            continue
        if ignored_reason is not None:
            skipped_files.append(_skipped(relative_path, ignored_reason))
            continue

        try:
            if path.stat().st_size > max_file_bytes:
                skipped_files.append(_skipped(relative_path, SkipReason.LARGE_FILE))
            elif has_binary_marker(path):
                skipped_files.append(_skipped(relative_path, SkipReason.BINARY_FILE))
            else:
                included_files.append(collect_file_metadata(path, relative_path))
        except OSError:
            skipped_files.append(_skipped(relative_path, SkipReason.READ_ERROR))

    included_files.sort(key=lambda file: file.path)
    skipped_files.sort(key=lambda file: file.path)
    return FileIndexArtifact(
        generated_at=generated_at or datetime.now(UTC),
        repo_root_name=root.name,
        files=included_files,
        skipped_files=skipped_files,
        stats=FileIndexStats(
            files_seen=len(included_files) + len(skipped_files),
            files_included=len(included_files),
            files_skipped=len(skipped_files),
            total_included_bytes=sum(file.size_bytes for file in included_files),
        ),
    )
