"""Construction of the canonical Git-tracked Layer 1 inventory."""

import os
from dataclasses import dataclass

from bridger.contracts.files import (
    FileIndex,
    FileRecord,
    IntakeConfiguration,
    summarize_files,
)
from bridger.contracts.repository import RepositoryContext
from bridger.repository.git import run_git
from bridger.repository.policy import classify_file, determine_disposition

FILE_INDEX_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class _TreeEntry:
    path: str
    object_id: str
    size_bytes: int
    mode: str


def build_file_index(
    context: RepositoryContext,
    configuration: IntakeConfiguration,
) -> FileIndex:
    """Build the complete, sorted inventory of Git-tracked files in context scope."""
    records: list[FileRecord] = []
    for entry in _list_tree_entries(context):
        run_git(context.root_path, "cat-file", "-e", f"{entry.object_id}^{{object}}")
        is_regular_file = entry.mode in {"100644", "100755"}
        content_type, language = classify_file(
            entry.path,
            is_regular_file=is_regular_file,
        )
        records.append(
            FileRecord(
                path=entry.path,
                git_object_id=entry.object_id,
                size_bytes=entry.size_bytes,
                content_type=content_type,
                language=language,
                disposition=determine_disposition(
                    path=entry.path,
                    size_bytes=entry.size_bytes,
                    content_type=content_type,
                    is_regular_file=is_regular_file,
                    configuration=configuration,
                ),
            )
        )

    files = sorted(records, key=lambda record: record.path)
    return FileIndex(
        schema_version=FILE_INDEX_SCHEMA_VERSION,
        repository_id=context.repository_id,
        revision=context.revision,
        scope_path=context.scope_path,
        files=files,
        summary=summarize_files(files),
    )


def _list_tree_entries(context: RepositoryContext) -> list[_TreeEntry]:
    output = run_git(
        context.root_path,
        "ls-tree",
        "-r",
        "-l",
        "-z",
        context.revision,
        "--",
        context.scope_path,
    )
    entries: list[_TreeEntry] = []
    for raw_entry in output.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", maxsplit=1)
        mode, _object_type, object_id, raw_size = metadata.split(maxsplit=3)
        size_bytes = int(raw_size) if raw_size != b"-" else 0
        entries.append(
            _TreeEntry(
                path=os.fsdecode(raw_path),
                object_id=object_id.decode("ascii"),
                size_bytes=size_bytes,
                mode=mode.decode("ascii"),
            )
        )
    return entries
