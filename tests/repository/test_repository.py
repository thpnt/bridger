"""Focused invariants for the Git-backed Layer 1 repository intake."""

import subprocess
from pathlib import Path

import pytest

from bridger.contracts.files import (
    BOUNDED_READ_MAX_BYTES,
    IntakeConfiguration,
    SourceReadRequest,
)
from bridger.repository.errors import RepositoryError, SourceReadDeniedError
from bridger.repository.file_index import build_file_index
from bridger.repository.reader import read_file
from bridger.repository.revisions import compare_revisions
from bridger.repository.service import prepare_repository, resolve_repository


def test_repository_resolution_and_inventory_are_git_truth(tmp_path: Path) -> None:
    repository = _initialize_repository(tmp_path)
    _write(repository, "src/zeta.py", "zeta = 1\n")
    _write(repository, "src/alpha.py", "alpha = 1\n")
    _write(repository, ".bridger/state.json", "{}\n")
    _write(repository, "notes.txt", "tracked documentation\n")
    revision = _commit(repository, "initial files")
    _write(repository, "untracked.py", "ignored = True\n")

    context, file_index = prepare_repository(repository)

    assert context.revision == revision
    assert [record.path for record in file_index.files] == [
        ".bridger/state.json",
        "notes.txt",
        "src/alpha.py",
        "src/zeta.py",
    ]
    assert file_index.summary.total_tracked == 4
    internal = next(
        record for record in file_index.files if record.path.startswith(".bridger/")
    )
    assert internal.disposition.processing_mode == "skip"
    assert internal.disposition.reason == "bridger_internal"

    scoped_context, scoped_index = prepare_repository(repository, scope_path="src")
    assert scoped_context.scope_path == "src"
    assert [record.path for record in scoped_index.files] == [
        "src/alpha.py",
        "src/zeta.py",
    ]


def test_invalid_repository_or_revision_fails(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError, match="not a Git repository"):
        resolve_repository(tmp_path)

    repository = _initialize_repository(tmp_path)
    _write(repository, "tracked.py", "value = 1\n")
    _commit(repository, "initial file")
    with pytest.raises(RepositoryError):
        resolve_repository(repository, revision="does-not-exist")


def test_reads_are_revision_bound_and_dispositions_cannot_be_bypassed(
    tmp_path: Path,
) -> None:
    repository = _initialize_repository(tmp_path)
    _write(repository, "source.py", "version = 'committed'\n")
    _write(repository, ".env", "TOKEN=secret\n")
    _write(repository, "large.py", "x = '" + "a" * (BOUNDED_READ_MAX_BYTES + 1) + "'\n")
    _commit(repository, "initial files")
    context = resolve_repository(repository)
    file_index = build_file_index(
        context,
        IntakeConfiguration(max_full_read_bytes=10),
    )
    _write(repository, "source.py", "version = 'dirty'\n")

    result = read_file(context, file_index, SourceReadRequest(path="source.py"))
    assert result.content == "version = 'committed'\n"
    assert result.revision == context.revision
    assert not result.truncated

    with pytest.raises(SourceReadDeniedError):
        read_file(context, file_index, SourceReadRequest(path=".env"))
    with pytest.raises(RepositoryError, match="absent from the FileIndex"):
        read_file(context, file_index, SourceReadRequest(path="untracked.py"))

    bounded = read_file(
        context,
        file_index,
        SourceReadRequest(path="large.py", max_bytes=BOUNDED_READ_MAX_BYTES + 1),
    )
    assert len(bounded.content.encode(bounded.encoding)) == BOUNDED_READ_MAX_BYTES
    assert bounded.truncated


def test_compare_revisions_reports_added_modified_and_deleted_paths(
    tmp_path: Path,
) -> None:
    repository = _initialize_repository(tmp_path)
    _write(repository, "keep.py", "version = 1\n")
    _write(repository, "removed.py", "removed = True\n")
    base_revision = _commit(repository, "initial files")
    _write(repository, "keep.py", "version = 2\n")
    (repository / "removed.py").unlink()
    _write(repository, "added.py", "added = True\n")
    target_revision = _commit(repository, "changed files")

    context = resolve_repository(repository)
    changes = compare_revisions(context, base_revision, target_revision)

    assert changes.base_revision == base_revision
    assert changes.target_revision == target_revision
    assert changes.added_paths == ["added.py"]
    assert changes.modified_paths == ["keep.py"]
    assert changes.deleted_paths == ["removed.py"]


def _initialize_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Layer One Test")
    return repository


def _write(repository: Path, relative_path: str, content: str) -> None:
    destination = repository / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", "-A")
    _git(repository, "commit", "-m", message)
    return _git(repository, "rev-parse", "HEAD").strip()


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
