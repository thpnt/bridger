"""Layer 2 application orchestration."""

from pathlib import Path
from typing import Any

from extraction.graphify import (
    adapt_file_index_to_graphify,
    run_graphify_extraction,
)
from extraction.symbol_index import build_symbol_index
from models.extraction import ExtractionFailure, ExtractionReport
from models.files import FileIndex
from models.repository import RepositoryContext
from models.symbols import SymbolIndex


def extract_repository_facts(
    context: RepositoryContext,
    file_index: FileIndex,
    *,
    cache_root: Path | None = None,
    parallel: bool = True,
    max_workers: int | None = None,
) -> tuple[SymbolIndex, ExtractionReport, dict[str, Any]]:
    """Extract deterministic facts and retain Graphify data for Layer 3."""
    selected_paths = adapt_file_index_to_graphify(context, file_index)
    graphify_result = run_graphify_extraction(
        selected_paths,
        context.root_path,
        cache_root=cache_root,
        parallel=parallel,
        max_workers=max_workers,
    )
    symbol_index = build_symbol_index(
        context,
        file_index,
        graphify_result.get("symbols", []),
    )
    failures = [
        ExtractionFailure(
            path=_relative_failure_path(error.get("path"), context.root_path),
            error=str(error.get("error") or "unknown extraction failure"),
        )
        for error in graphify_result.get("file_errors", [])
    ]
    failures.sort(key=lambda failure: failure.path)
    report = ExtractionReport(
        repository_id=context.repository_id,
        revision=context.revision,
        attempted_files=len(selected_paths),
        successful_files=len(selected_paths) - len(failures),
        failed_files=failures,
        produced_symbols=len(symbol_index.symbols),
    )
    return symbol_index, report, graphify_result


def _relative_failure_path(value: object, root_path: Path) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Graphify file error is missing its path")
    path = Path(value)
    if not path.is_absolute():
        path = root_path / path
    try:
        return path.resolve().relative_to(root_path.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(
            f"Graphify file error escapes the repository: {value}"
        ) from error
