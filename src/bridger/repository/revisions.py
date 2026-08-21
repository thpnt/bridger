"""Revision-to-revision Git file change classification."""

import os

from bridger.contracts.files import FileChangeSet
from bridger.contracts.repository import RepositoryContext
from bridger.repository.git import resolve_commit, run_git


def compare_revisions(
    context: RepositoryContext,
    base_revision: str,
    target_revision: str,
) -> FileChangeSet:
    """Return sorted added, modified, and deleted paths without rename detection."""
    base_commit = resolve_commit(context.root_path, base_revision)
    target_commit = resolve_commit(context.root_path, target_revision)
    output = run_git(
        context.root_path,
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        base_commit,
        target_commit,
        "--",
        context.scope_path,
    )
    added_paths: list[str] = []
    modified_paths: list[str] = []
    deleted_paths: list[str] = []
    fields = [field for field in output.split(b"\0") if field]
    for status, raw_path in zip(fields[::2], fields[1::2], strict=True):
        path = os.fsdecode(raw_path)
        if status == b"A":
            added_paths.append(path)
        elif status == b"D":
            deleted_paths.append(path)
        else:
            modified_paths.append(path)
    return FileChangeSet(
        base_revision=base_commit,
        target_revision=target_commit,
        added_paths=sorted(added_paths),
        modified_paths=sorted(modified_paths),
        deleted_paths=sorted(deleted_paths),
    )
