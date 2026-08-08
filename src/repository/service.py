"""Thin application entry points for resolving and indexing Git repositories."""

from pathlib import Path

from models.files import FileIndex, IntakeConfiguration
from models.repository import RepositoryContext
from repository.errors import RepositoryError
from repository.file_index import build_file_index
from repository.git import normalize_repository_path, resolve_commit, run_git


def prepare_repository(
    root_path: str | Path,
    *,
    revision: str | None = None,
    scope_path: str = ".",
    configuration: IntakeConfiguration | None = None,
) -> tuple[RepositoryContext, FileIndex]:
    """Resolve a Git checkout and build its complete, revision-bound FileIndex."""
    context = resolve_repository(root_path, revision=revision, scope_path=scope_path)
    return context, build_file_index(context, configuration or IntakeConfiguration())


def resolve_repository(
    root_path: str | Path,
    *,
    revision: str | None = None,
    scope_path: str = ".",
) -> RepositoryContext:
    """Validate a Git checkout and resolve its exact source-state identity."""
    requested_path = Path(root_path).expanduser().resolve()
    try:
        is_work_tree = run_git(requested_path, "rev-parse", "--is-inside-work-tree")
    except RepositoryError as error:
        raise RepositoryError(f"not a Git repository: {requested_path}") from error
    if is_work_tree.decode("ascii").strip() != "true":
        raise RepositoryError(f"not a Git work tree: {requested_path}")

    repository_root = Path(
        run_git(requested_path, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    resolved_revision = resolve_commit(repository_root, revision)
    normalized_scope = normalize_repository_path(scope_path, allow_root=True)
    _validate_scope(repository_root, resolved_revision, normalized_scope)

    branch = _optional_git_output(
        repository_root,
        "symbolic-ref",
        "--quiet",
        "--short",
        "HEAD",
    )
    remote_url = _optional_git_output(
        repository_root,
        "config",
        "--get",
        "remote.origin.url",
    )
    repository_id = remote_url or repository_root.as_uri()
    return RepositoryContext(
        repository_id=repository_id,
        root_path=repository_root,
        revision=resolved_revision,
        branch=branch,
        scope_path=normalized_scope,
    )


def _validate_scope(root_path: Path, revision: str, scope_path: str) -> None:
    if scope_path == ".":
        run_git(root_path, "cat-file", "-e", f"{revision}^{{tree}}")
        return
    try:
        run_git(root_path, "cat-file", "-e", f"{revision}:{scope_path}")
    except RepositoryError as error:
        raise RepositoryError(
            f"scope path does not exist at revision {revision}: {scope_path}"
        ) from error


def _optional_git_output(root_path: Path, *arguments: str) -> str | None:
    try:
        output = run_git(root_path, *arguments).decode("utf-8").strip()
    except RepositoryError:
        return None
    return output or None
