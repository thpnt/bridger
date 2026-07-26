from dataclasses import dataclass
from pathlib import Path

from rich.table import Table

from bridger.console import console
from bridger.models.context_plan import ContextPlanRun
from bridger.models.context_plan_bootstrap import ContextPlanBootstrapArtifact
from bridger.models.file_index import FileIndexArtifact
from bridger.models.repo_context import RepoContextArtifact
from bridger.models.symbol_index import SymbolIndexArtifact
from bridger.paths import ProjectPaths


@dataclass(frozen=True)
class InitRunSummary:
    file_index: FileIndexArtifact
    repo_context: RepoContextArtifact
    symbol_index: SymbolIndexArtifact
    context_plan_bootstrap: ContextPlanBootstrapArtifact
    supported_file_count: int
    artifacts_dir: str
    artifact_paths: dict[str, str]
    next_step: str
    already_exists: bool

    @property
    def symbol_parse_error_count(self) -> int:
        return sum(
            len(result.errors) for result in self.symbol_index.files if result.errors
        )

    @property
    def has_warnings(self) -> bool:
        return self.symbol_parse_error_count > 0


def render_init_summary(summary: InitRunSummary, *, verbose: bool) -> None:
    if summary.has_warnings:
        console.print("[yellow]Repository substrate ready with warnings[/yellow]")
    else:
        console.print("[green]Repository substrate ready[/green]")

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
    context_plan_bootstrap: ContextPlanBootstrapArtifact,
    supported_file_count: int,
    already_exists: bool,
) -> InitRunSummary:
    return InitRunSummary(
        file_index=file_index,
        repo_context=repo_context,
        symbol_index=symbol_index,
        context_plan_bootstrap=context_plan_bootstrap,
        supported_file_count=supported_file_count,
        artifacts_dir=_relative_dir(paths.root, paths.file_index_artifact.parent),
        artifact_paths={
            "file-index": _relative_path(paths.root, paths.file_index_artifact),
            "repo-context": _relative_path(paths.root, paths.repo_context_artifact),
            "symbol-index": _relative_path(paths.root, paths.symbol_index_artifact),
            "context-plan-bootstrap": _relative_path(
                paths.root, paths.context_plan_bootstrap_artifact
            ),
        },
        next_step="Context Plan generation",
        already_exists=already_exists,
    )


def render_context_plan_success(
    run: ContextPlanRun,
    *,
    context_plan_path: str,
    run_artifact_path: str,
    verbose: bool,
) -> None:
    console.print()
    console.print("[green]Context Plan generated[/green]")
    if any(attempt.succeeded for attempt in run.validation_attempts):
        console.print("[green]✓ Context Plan validated[/green]")
    if run.output is not None:
        console.print(f"[green]✓ Written to {context_plan_path}[/green]")
    console.print(_build_context_plan_table(run, context_plan_path, run_artifact_path))

    if verbose:
        console.print()
        console.print(_build_context_plan_details_table(run))

    console.print("Memory generation and AGENTS.md generation are not implemented yet.")


def render_context_plan_failure(
    message: str,
    *,
    run_artifact_path: str | None,
    next_step: str | None = None,
) -> None:
    console.print(f"[red]Context Plan generation failed:[/red] {message}")
    if run_artifact_path is not None:
        console.print(f"Run record: {run_artifact_path}")
    if next_step is not None:
        console.print(f"Next: {next_step}")


def _build_context_plan_table(
    run: ContextPlanRun,
    context_plan_path: str,
    run_artifact_path: str,
) -> Table:
    table = _base_table(title="Context Plan")
    table.add_row("Status", run.status.value)
    table.add_row("Run ID", run.run_id)
    table.add_row("Context Plan", context_plan_path)
    table.add_row("Run record", run_artifact_path)
    table.add_row("Model", _model_identifier(run))
    table.add_row("Tool calls", _format_count(run.tool_call_count))
    table.add_row("Evidence paths", _format_count(run.inspection.inspected_file_count))
    table.add_row("Usage", _format_count(run.token_usage) + " tokens")
    table.add_row("Duration", _format_duration(run))
    return table


def _build_context_plan_details_table(run: ContextPlanRun) -> Table:
    table = _base_table(title="Context Plan run details")
    table.add_row("Model turns", _format_count(run.model_turns))
    table.add_row("Input tokens", _format_count(run.input_tokens))
    table.add_row("Output tokens", _format_count(run.output_tokens))
    table.add_row("Cached input tokens", _format_count(run.cached_input_tokens))
    table.add_row("Reasoning tokens", _format_count(run.reasoning_tokens))
    table.add_row("Model latency", f"{run.model_latency_ms:,} ms")
    table.add_row("Searches", _format_count(len(run.inspection.search_records)))
    table.add_row(
        "Finalization requests",
        _format_count(len(run.finalization_requests)),
    )
    table.add_row(
        "Repair attempts",
        _format_count(max(len(run.validation_attempts) - 1, 0)),
    )
    return table


def _model_identifier(run: ContextPlanRun) -> str:
    values = [value for value in (run.model_profile, run.model_name) if value]
    return " / ".join(values) if values else "unknown"


def _format_duration(run: ContextPlanRun) -> str:
    completed_at = run.completed_at or run.updated_at
    seconds = max((completed_at - run.started_at).total_seconds(), 0)
    return f"{seconds:.1f}s"


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
        "Bootstrap",
        _join_parts(
            [
                _format_bootstrap_count(
                    len(summary.context_plan_bootstrap.artifact_checksums), "artifacts"
                ),
                _format_bootstrap_count(
                    len(summary.context_plan_bootstrap.available_tools),
                    "tools declared",
                ),
            ]
        ),
    )
    return table


def _format_bootstrap_count(count: int, label: str) -> str:
    return f"{_format_count(count)} {label}"


def _build_warning_table(summary: InitRunSummary) -> Table:
    table = _base_table(title="Warnings")
    if summary.symbol_parse_error_count > 0:
        table.add_row(
            f"{_format_count(summary.symbol_parse_error_count)} "
            "files could not be parsed"
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
