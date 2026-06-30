from bridger.artifacts import write_artifact
from bridger.cli_output import build_init_run_summary, render_init_summary
from bridger.console import console
from bridger.deterministic.file_index import build_file_index_for_project
from bridger.deterministic.graph_summary import build_graph_summary_for_project
from bridger.deterministic.repo_context import build_repo_context_for_project
from bridger.deterministic.repo_discovery import build_repo_discovery_for_project
from bridger.deterministic.repo_graph import build_repo_graph_for_project
from bridger.deterministic.symbols import (
    build_extractor_registry,
    build_symbol_index_for_project,
    extractor_for_path,
)
from bridger.paths import ProjectPaths
from bridger.project import initialize_project


def run(fresh: bool, verbose: bool) -> None:
    paths = ProjectPaths.from_cwd()
    already_exists, _ = initialize_project(paths, fresh)
    file_index = build_file_index_for_project(paths.root)
    write_artifact(paths.file_index_artifact, file_index)
    repo_context = build_repo_context_for_project(paths.root)
    write_artifact(paths.repo_context_artifact, repo_context)
    symbol_index = build_symbol_index_for_project(paths.root)
    write_artifact(paths.symbol_index_artifact, symbol_index)
    repo_graph = build_repo_graph_for_project(paths.root)
    write_artifact(paths.repo_graph_artifact, repo_graph)
    graph_summary = build_graph_summary_for_project(paths.root)
    write_artifact(paths.graph_summary_artifact, graph_summary)
    repo_discovery = build_repo_discovery_for_project(paths.root)
    write_artifact(paths.repo_discovery_artifact, repo_discovery)
    extractor_registry = build_extractor_registry()
    supported_files = sum(
        extractor_for_path(file.path, extractor_registry) is not None
        for file in file_index.files
    )

    summary = build_init_run_summary(
        paths=paths,
        file_index=file_index,
        repo_context=repo_context,
        symbol_index=symbol_index,
        repo_graph=repo_graph,
        repo_discovery=repo_discovery,
        supported_file_count=supported_files,
        already_exists=already_exists,
    )
    render_init_summary(summary, verbose=verbose)

    if fresh:
        console.print("Fresh mode is currently a placeholder.")
