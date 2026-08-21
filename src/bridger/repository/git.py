"""Small private helpers for revision-bound Git operations."""

import os
import subprocess
from pathlib import Path, PurePosixPath

from bridger.repository.errors import RepositoryError


def run_git(
    root_path: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> bytes:
    """Run one Git command against a checkout and return its raw stdout."""
    command = ["git", "-C", os.fspath(root_path), *arguments]
    completed = subprocess.run(
        command,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RepositoryError(message or f"Git command failed: {' '.join(arguments)}")
    return completed.stdout


def normalize_repository_path(value: str, *, allow_root: bool = False) -> str:
    """Normalize one repository-relative POSIX path without allowing escapes."""
    if not value or "\x00" in value:
        raise RepositoryError("repository path must not be empty or contain NUL")
    raw_path = PurePosixPath(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise RepositoryError("repository path must remain inside the repository")
    normalized = raw_path.as_posix()
    if normalized == ".":
        if allow_root:
            return normalized
        raise RepositoryError("file path must name a tracked file")
    return normalized


def resolve_commit(root_path: Path, revision: str | None) -> str:
    """Resolve a Git revision expression to its exact commit object identifier."""
    requested_revision = "HEAD" if revision is None else revision
    if not requested_revision:
        raise RepositoryError("revision must not be empty")
    output = run_git(
        root_path,
        "rev-parse",
        "--verify",
        f"{requested_revision}^{{commit}}",
    )
    return output.decode("ascii").strip()


def path_is_within_scope(path: str, scope_path: str) -> bool:
    """Return whether a normalized file path is inside a normalized scope path."""
    return scope_path == "." or path == scope_path or path.startswith(f"{scope_path}/")
