"""Private boundary between Bridger repository truth and Graphify."""

from pathlib import Path
from typing import Any

from graphify.extract import extract
from models.files import FileIndex
from models.repository import RepositoryContext


def adapt_file_index_to_graphify(
    context: RepositoryContext,
    file_index: FileIndex,
) -> list[Path]:
    """Return the deterministic explicit paths Graphify is allowed to process."""
    _validate_repository_identity(context, file_index)
    root_path = context.root_path.resolve()
    selected_paths: list[Path] = []
    for record in file_index.files:
        if not (
            record.disposition.processing_mode == "extract"
            and record.disposition.read_mode == "full"
        ):
            continue
        runtime_path = (root_path / record.path).resolve()
        try:
            runtime_path.relative_to(root_path)
        except ValueError as error:
            raise ValueError(
                f"FileIndex path resolves outside the repository: {record.path}"
            ) from error
        selected_paths.append(runtime_path)
    return selected_paths


def run_graphify_extraction(
    paths: list[Path],
    repository_root: Path,
    *,
    cache_root: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Run Graphify directly with Bridger-selected paths and no discovery step."""
    return extract(
        paths,
        cache_root=cache_root or repository_root,
        root=repository_root,
        parallel=parallel,
        max_workers=max_workers,
    )


def _validate_repository_identity(
    context: RepositoryContext,
    file_index: FileIndex,
) -> None:
    if context.repository_id != file_index.repository_id:
        raise ValueError("RepositoryContext and FileIndex repository_id differ")
    if context.revision != file_index.revision:
        raise ValueError("RepositoryContext and FileIndex revision differ")
    if context.scope_path != file_index.scope_path:
        raise ValueError("RepositoryContext and FileIndex scope_path differ")
