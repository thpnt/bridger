from dataclasses import dataclass
from pathlib import Path

from rich.table import Table

from bridger.console import console
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.repo_discovery import RepoDiscoveryArtifact
from bridger.models.repo_graph import RepoGraphArtifact
from bridger.models.symbol_index import SymbolIndexArtifact
from bridger.paths import ProjectPaths


@dataclass(frozen=True)
class InitRunSummary:
    file_index: FileIndexArtifact
    repo_context: RepoContextArtifact
    symbol_index: SymbolIndexArtifact
    repo_graph: RepoGraphArtifact
    repo_discovery: RepoDiscoveryArtifact
    supported_file_count: int
    artifacts_dir: str
    artifact_paths: dict[str, str]
    next_step: str
    already_exists: bool

    @property
    def symbol_parse_error_count(self) -> int:
        return len(self.symbol_index.parse_errors)

    @property
    def unresolved_import_count(self) -> int:
        return len(self.repo_graph.unresolved_imports)

    @property
    def has_warnings(self) -> bool:
        return self.symbol_parse_error_count > 0 or self.unresolved_import_count > 0


def render_init_summary(summary: InitRunSummary, *, verbose: bool) -> None:
    if summary.has_warnings:
        console.print("[yellow]Bridger initialized with warnings[/yellow]")
    else:
        console.print("[green]Bridger initialized[/green]")

    console.print()
    console.print(_build_substrate_table(summary))

    if summary.has_warnings:
        console.print()
        console.print(_build_warning_table(summary))

    if verbose:
        console.print()
        console.print(_build_artifacts_table(summary))

    console.print()
    console.print(f"Artifacts written to {summary.artifacts_dir}")
    console.print(f"Next: {summary.next_step}")

    if summary.already_exists:
        console.print("Existing project files were preserved.")


def build_init_run_summary(
    *,
    paths: ProjectPaths,
    file_index: FileIndexArtifact,
    repo_context: RepoContextArtifact,
    symbol_index: SymbolIndexArtifact,
    repo_graph: RepoGraphArtifact,
    repo_discovery: RepoDiscoveryArtifact,
    supported_file_count: int,
    already_exists: bool,
) -> InitRunSummary:
    return InitRunSummary(
        file_index=file_index,
        repo_context=repo_context,
        symbol_index=symbol_index,
        repo_graph=repo_graph,
        repo_discovery=repo_discovery,
        supported_file_count=supported_file_count,
        artifacts_dir=_relative_dir(paths.root, paths.file_index_artifact.parent),
        artifact_paths={
            "file-index": _relative_path(paths.root, paths.file_index_artifact),
            "repo-context": _relative_path(paths.root, paths.repo_context_artifact),
            "symbol-index": _relative_path(paths.root, paths.symbol_index_artifact),
            "repo-graph": _relative_path(paths.root, paths.repo_graph_artifact),
            "graph-summary": _relative_path(paths.root, paths.graph_summary_artifact),
            "repo-discovery": _relative_path(paths.root, paths.repo_discovery_artifact),
        },
        next_step="agentic repository discovery is not implemented yet",
        already_exists=already_exists,
    )


def _build_substrate_table(summary: InitRunSummary) -> Table:
    table = _base_table(title="Deterministic substrate")
    table.add_row(
        "Files",
        _join_parts(
            [
                f"{_format_count(summary.file_index.stats.files_included)} indexed",
                f"{_format_count(summary.file_index.stats.files_skipped)} skipped",
            ]
        ),
    )
    table.add_row(
        "Context",
        _join_parts(
            [
                f"{_format_count(len(summary.repo_context.manifests))} manifests",
                f"{_format_count(len(summary.repo_context.config_files))} config",
                _optional_count(len(summary.repo_context.ci_files), "CI"),
                (
                    f"{_format_count(len(summary.repo_context.instruction_files))} "
                    "instructions"
                ),
                f"{_format_count(len(summary.repo_context.docs_files))} docs",
                _optional_count(len(summary.repo_context.parse_errors), "parse errors"),
            ]
        ),
    )
    table.add_row(
        "Symbols",
        _join_parts(
            [
                f"{_format_count(len(summary.symbol_index.symbols))} symbols",
                f"{_format_count(summary.supported_file_count)} files",
                _optional_count(summary.symbol_parse_error_count, "parse errors"),
            ]
        ),
    )
    table.add_row(
        "Graph",
        _join_parts(
            [
                f"{_format_count(len(summary.repo_graph.nodes))} nodes",
                f"{_format_count(len(summary.repo_graph.edges))} edges",
                _optional_count(summary.unresolved_import_count, "unresolved imports"),
            ]
        ),
    )
    table.add_row(
        "Bootstrap",
        _join_parts(
            [
                (
                    f"{_format_count(len(summary.repo_discovery.artifact_checksums))} "
                    "artifacts"
                ),
                (
                    f"{_format_count(len(summary.repo_discovery.available_tools))} "
                    "tools declared"
                ),
            ]
        ),
    )
    return table


def _build_warning_table(summary: InitRunSummary) -> Table:
    table = _base_table(title="Warnings")
    if summary.symbol_parse_error_count > 0:
        table.add_row(
            f"{_format_count(summary.symbol_parse_error_count)} "
            "files could not be parsed"
        )
    if summary.unresolved_import_count > 0:
        table.add_row(
            f"{_format_count(summary.unresolved_import_count)} "
            "local imports could not be resolved"
        )
    return table


def _build_artifacts_table(summary: InitRunSummary) -> Table:
    table = _base_table(title="Artifacts")
    table.add_column("Artifact", style="default", no_wrap=True)
    table.add_column("Path", style="default")
    for artifact_name, artifact_path in summary.artifact_paths.items():
        table.add_row(artifact_name, artifact_path)
    return table


def _base_table(*, title: str) -> Table:
    table = Table(
        title=title,
        box=None,
        show_header=False,
        pad_edge=False,
        expand=False,
    )
    return table


def _join_parts(parts: list[str | None]) -> str:
    return " · ".join(part for part in parts if part)


def _optional_count(count: int, label: str) -> str | None:
    if count <= 0:
        return None
    return f"{_format_count(count)} {label}"


def _format_count(value: int) -> str:
    return f"{value:,}"


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _relative_dir(root: Path, path: Path) -> str:
    return f"{_relative_path(root, path)}/"
