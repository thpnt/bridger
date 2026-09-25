"""Canonical orchestration for building one Bridger Repository Brain."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.files import FileIndex
from bridger.contracts.graph import GraphBuildResult, GraphConstructionConfig
from bridger.contracts.memory.core import MemoryFleetSpec
from bridger.contracts.repository import RepositoryContext
from bridger.contracts.symbols import SymbolIndex
from bridger.extraction.service import extract_repository_facts
from bridger.graph.intelligence import build_graph_intelligence
from bridger.graph.lifecycle import (
    create_graph_snapshot,
    load_graph_snapshot,
    validate_graph_snapshot,
)
from bridger.llm.profiles import LLMProfile
from bridger.progress import InitProgressObserver, InitStage, notify_stage_started
from bridger.repository.service import prepare_repository
from bridger.repository_brain.index import ensure_brain_index
from bridger.repository_brain.loader import (
    RepositoryBrainLoadError,
    load_repository_brain,
)
from bridger.repository_brain.publication import (
    clear_current_repository_brain,
    mark_repository_brain_complete,
    resolve_current_repository_brain,
    set_current_repository_brain,
    supersede_existing_fleets,
)
from bridger.repository_brain.runtime_metrics import (
    build_runtime_metrics_report,
    persist_runtime_metrics_report,
)
from bridger.runtime_timing import RuntimeMetricsCollector, current_collector

_LEGACY_STAGE_LABELS = {
    InitStage.PREPARE_REPOSITORY: "Preparing repository",
    InitStage.EXTRACT_FACTS: "Extracting deterministic repository facts",
    InitStage.BUILD_GRAPH: "Building deterministic graph intelligence",
    InitStage.PUBLISH_GRAPH: "Publishing deterministic graph snapshot",
    InitStage.MODEL_ENRICHMENT: "Generating enrichment and Repository Brain memory",
    InitStage.INITIALIZE_MEMORY_FLEET: (
        "Running memory fleet validation and publication"
    ),
    InitStage.PUBLISH_REPOSITORY_BRAIN: "Publishing Repository Brain",
    InitStage.PREPARE_BRAIN_INDEX: "Preparing Repository Brain index",
}


class InitMode(StrEnum):
    """Supported Repository Brain execution modes."""

    FULL = "full"
    DETERMINISTIC = "deterministic"
    TEST = "test"


class ReasoningEffort(StrEnum):
    """Supported reasoning policy for memory-agent model calls."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class RepositoryBrainBuildError(RuntimeError):
    """Raised when a Repository Brain build cannot complete."""


@dataclass(frozen=True)
class InitRunConfiguration:
    """Resolved configuration shared by the public init entrypoint."""

    mode: InitMode
    repository_root: Path
    bridger_root: Path
    model_profile_name: str
    enable_model_stages: bool
    test_budgets: bool
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH
    fresh: bool = False
    openai_model: str | None = None

    @property
    def graph_root(self) -> Path:
        """Return the deterministic snapshot storage location."""
        return self.bridger_root / "graph"


@dataclass(frozen=True)
class RepositoryBrainBuildResult:
    """Public result of the canonical Repository Brain builder."""

    mode: InitMode
    graph_build: GraphBuildResult
    publication_path: Path | None = None
    token_usage_report_path: Path | None = None
    reused: bool = False
    runtime_metrics_report_path: Path | None = field(default=None, compare=False)


@dataclass(frozen=True)
class RepositoryBrainModelBuildResult:
    """Artifacts produced by the model-driven portion of init."""

    publication_path: Path
    token_usage_report_path: Path | None


def format_repository_brain_error(error: BaseException) -> str:
    """Format a build failure without hiding grouped or chained exceptions."""
    if not isinstance(error, BaseExceptionGroup):
        lines = _format_exception_chain(error, set())
        return "\n".join(lines) or type(error).__name__

    leaves = _flatten_exception_group(error, set())
    seen: set[int] = set()
    rendered: list[list[str]] = []
    for leaf in leaves:
        lines = _format_exception_chain(leaf, seen)
        if lines:
            rendered.append(lines)
    if error.__cause__ is not None:
        cause_lines = _format_exception_chain(error.__cause__, seen)
        if cause_lines:
            if rendered:
                _append_cause(rendered[0], cause_lines)
            else:
                rendered.append(cause_lines)

    if not rendered:
        return type(error).__name__
    if len(rendered) == 1:
        return "\n".join(rendered[0])

    lines = [f"Repository Brain build failed with {len(rendered)} errors:", ""]
    for index, failure_lines in enumerate(rendered, start=1):
        lines.append(f"{index}. {failure_lines[0]}")
        lines.extend(f"   {line}" for line in failure_lines[1:])
        if index != len(rendered):
            lines.append("")
    return "\n".join(lines)


def _flatten_exception_group(
    error: BaseException,
    seen_groups: set[int],
) -> list[BaseException]:
    if not isinstance(error, BaseExceptionGroup):
        return [error]
    error_id = id(error)
    if error_id in seen_groups:
        return []
    seen_groups.add(error_id)
    leaves: list[BaseException] = []
    for child in error.exceptions:
        leaves.extend(_flatten_exception_group(child, seen_groups))
    return leaves


def _format_exception_chain(
    error: BaseException,
    seen: set[int],
) -> list[str]:
    error_id = id(error)
    if error_id in seen:
        return []
    seen.add(error_id)
    lines = [_describe_exception(error)]
    cause = error.__cause__
    if cause is None:
        return lines

    if isinstance(cause, BaseExceptionGroup):
        causes = _flatten_exception_group(cause, seen)
        for nested_cause in causes:
            cause_lines = _format_exception_chain(nested_cause, seen)
            if cause_lines:
                _append_cause(lines, cause_lines)
        return lines

    cause_lines = _format_exception_chain(cause, seen)
    if cause_lines:
        _append_cause(lines, cause_lines)
    return lines


def _append_cause(lines: list[str], cause_lines: list[str]) -> None:
    lines.append(f"caused by: {cause_lines[0]}")
    lines.extend(f"           {line}" for line in cause_lines[1:])


def _describe_exception(error: BaseException) -> str:
    message = str(error)
    if message:
        return f"{type(error).__name__}: {message}"
    return type(error).__name__


def resolve_init_configuration(
    mode: InitMode,
    *,
    repository_root: Path | None = None,
    model_profile_name: str = "balanced",
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH,
    fresh: bool = False,
    openai_model: str | None = None,
) -> InitRunConfiguration:
    """Resolve all mode-specific behavior at the CLI/application boundary."""
    root = (repository_root or Path.cwd()).resolve()
    return InitRunConfiguration(
        mode=mode,
        repository_root=root,
        bridger_root=root / ".bridger",
        model_profile_name=model_profile_name,
        enable_model_stages=mode is not InitMode.DETERMINISTIC,
        test_budgets=mode is InitMode.TEST,
        reasoning_effort=reasoning_effort,
        fresh=fresh,
        openai_model=openai_model,
    )


def build_repository_brain(
    configuration: InitRunConfiguration,
    *,
    on_stage: Callable[[str], None] | None = None,
    progress: InitProgressObserver | None = None,
) -> RepositoryBrainBuildResult:
    """Run the documented Repository Brain pipeline for one repository."""
    metrics = RuntimeMetricsCollector()
    with metrics.activate():
        try:
            result = _build_repository_brain(
                configuration, on_stage=on_stage, progress=progress
            )
        except BaseException:
            metrics.failed_stage = metrics.failed_stage or "init"
            try:
                report = build_runtime_metrics_report(
                    metrics,
                    bridger_root=configuration.bridger_root,
                    mode=configuration.mode.value,
                    fresh=configuration.fresh,
                    model=metrics.model or configuration.openai_model,
                    reasoning_effort=configuration.reasoning_effort.value,
                    model_profile=configuration.model_profile_name,
                    status="failed",
                )
                persist_runtime_metrics_report(report, configuration.bridger_root)
            except Exception:
                pass
            raise
        try:
            report = build_runtime_metrics_report(
                metrics,
                bridger_root=configuration.bridger_root,
                mode=configuration.mode.value,
                fresh=configuration.fresh,
                model=metrics.model or configuration.openai_model,
                reasoning_effort=configuration.reasoning_effort.value,
                model_profile=configuration.model_profile_name,
                status="completed",
            )
            path = persist_runtime_metrics_report(report, configuration.bridger_root)
        except Exception:
            path = None
        return replace(result, runtime_metrics_report_path=path)


def _build_repository_brain(
    configuration: InitRunConfiguration,
    *,
    on_stage: Callable[[str], None] | None = None,
    progress: InitProgressObserver | None = None,
) -> RepositoryBrainBuildResult:
    metrics = current_collector()
    assert metrics is not None
    _report_stage(on_stage, progress, InitStage.PREPARE_REPOSITORY)
    with metrics.span("prepare_repository"):
        context, file_index = prepare_repository(configuration.repository_root)
    metrics.repository_id = getattr(context, "repository_id", None)
    metrics.revision = getattr(context, "revision", None)
    if configuration.fresh and configuration.enable_model_stages:
        try:
            _mark_selected_brain_complete(configuration.bridger_root)
            supersede_existing_fleets(configuration.bridger_root / "runtime")
            clear_current_repository_brain(configuration.bridger_root)
        except Exception as error:
            raise RepositoryBrainBuildError(
                format_repository_brain_error(error)
            ) from error
    if configuration.mode is InitMode.FULL and not configuration.fresh:
        try:
            reused = _reuse_current_repository_brain(
                configuration,
                context,
                file_index,
            )
        except Exception as error:
            message = format_repository_brain_error(error)
            raise RepositoryBrainBuildError(message) from error
        if reused is not None:
            metrics.reused = True
            _report_stage(on_stage, progress, InitStage.PREPARE_BRAIN_INDEX)
            try:
                with metrics.span("brain_index"):
                    if progress is None:
                        _ensure_repository_brain_index(
                            configuration,
                            reused.publication_path,
                        )
                    else:
                        _ensure_repository_brain_index(
                            configuration,
                            reused.publication_path,
                            progress=progress,
                        )
            except Exception as error:
                message = format_repository_brain_error(error)
                raise RepositoryBrainBuildError(message) from error
            _mark_publication_complete(reused.publication_path)
            return reused
    recovery_spec = None
    if configuration.enable_model_stages and not configuration.fresh:
        try:
            from bridger.repository_brain.harness import discover_resumable_fleet

            recovery_spec = discover_resumable_fleet(configuration, context)
            if recovery_spec is not None:
                metrics.resumed = True
                metrics.fleet_run_id = getattr(recovery_spec, "fleet_run_id", None)
        except Exception as error:
            message = format_repository_brain_error(error)
            raise RepositoryBrainBuildError(message) from error
    _report_stage(on_stage, progress, InitStage.EXTRACT_FACTS)
    with metrics.span("extract_facts"):
        symbol_index, _report, graphify_extraction = extract_repository_facts(
            context,
            file_index,
            cache_root=configuration.bridger_root / "cache",
        )
    if recovery_spec is None:
        graph_configuration = GraphConstructionConfig()
        _report_stage(on_stage, progress, InitStage.BUILD_GRAPH)
        with metrics.span("build_graph"):
            graph, diagnostics, derived_state = build_graph_intelligence(
                context,
                file_index,
                graphify_extraction,
                graph_configuration,
            )
        _report_stage(on_stage, progress, InitStage.PUBLISH_GRAPH)
        with metrics.span("publish_graph"):
            graph_build = create_graph_snapshot(
                context,
                file_index,
                symbol_index,
                graph,
                diagnostics,
                derived_state,
                graph_configuration,
                configuration.graph_root,
            )
    else:
        try:
            from bridger.repository_brain.harness import load_recovery_model_layers

            with metrics.span("model_enrichment"):
                graph_build, profile, enrichment = load_recovery_model_layers(
                    configuration,
                    context,
                    file_index,
                    recovery_spec,
                )
            metrics.model = getattr(profile, "model", None)
        except Exception as error:
            message = format_repository_brain_error(error)
            raise RepositoryBrainBuildError(message) from error
    if not configuration.enable_model_stages:
        return RepositoryBrainBuildResult(
            mode=configuration.mode,
            graph_build=graph_build,
        )

    _report_stage(on_stage, progress, InitStage.MODEL_ENRICHMENT)
    try:
        # Layer 5 owns a synchronous public API that runs its internal async
        # batching. Complete it before entering the memory fleet event loop.
        if recovery_spec is None:
            from bridger.repository_brain.harness import prepare_model_layers

            with metrics.span("model_enrichment"):
                profile, enrichment = prepare_model_layers(configuration, graph_build)
            metrics.model = getattr(profile, "model", None)
        with metrics.span("memory_fleet"):
            model_result: RepositoryBrainModelBuildResult | Path = asyncio.run(
                _run_model_driven_pipeline(
                    configuration,
                    context,
                    file_index,
                    symbol_index,
                    graph_build,
                    profile,
                    enrichment,
                    on_stage,
                    progress,
                    recovery_spec,
                )
            )
        if isinstance(model_result, Path):
            publication_path = model_result
            token_usage_report_path = None
        else:
            publication_path = model_result.publication_path
            token_usage_report_path = model_result.token_usage_report_path
        _report_stage(on_stage, progress, InitStage.PREPARE_BRAIN_INDEX)
        with metrics.span("brain_index"):
            if progress is None:
                _ensure_repository_brain_index(configuration, publication_path)
            else:
                _ensure_repository_brain_index(
                    configuration,
                    publication_path,
                    progress=progress,
                )
        with metrics.span("brain_publication"):
            set_current_repository_brain(
                configuration.bridger_root,
                publication_path,
            )
            _mark_publication_complete(publication_path)
    except Exception as error:
        message = format_repository_brain_error(error)
        raise RepositoryBrainBuildError(message) from error
    return RepositoryBrainBuildResult(
        mode=configuration.mode,
        graph_build=graph_build,
        publication_path=publication_path,
        token_usage_report_path=token_usage_report_path,
    )


def _mark_publication_complete(publication_path: Path | None) -> None:
    if publication_path is None:
        raise ValueError("Repository Brain publication path is unavailable")
    brain = load_repository_brain(publication_path)
    mark_repository_brain_complete(
        Path(brain.manifest.memory_runtime_root),
        brain.manifest.fleet_run_id,
        brain.publication_id,
    )


def _mark_selected_brain_complete(bridger_root: Path) -> None:
    current = bridger_root / "current"
    if not current.exists() or current.is_symlink():
        return
    try:
        publication_path = resolve_current_repository_brain(bridger_root)
    except ValueError:
        return
    if publication_path is not None:
        try:
            _mark_publication_complete(publication_path)
        except RepositoryBrainLoadError:
            return


def _ensure_repository_brain_index(
    configuration: InitRunConfiguration,
    publication_path: Path | None,
    *,
    progress: InitProgressObserver | None = None,
) -> Path:
    """Ensure the derived index for one exact Repository Brain publication."""
    if publication_path is None:
        raise ValueError("Repository Brain publication path is unavailable")
    brain = load_repository_brain(publication_path)
    return ensure_brain_index(
        brain,
        configuration.bridger_root / "cache",
        progress=progress,
    )


def _reuse_current_repository_brain(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
) -> RepositoryBrainBuildResult | None:
    """Return the compatible authoritative current Brain, if one exists."""
    publication_path = resolve_current_repository_brain(configuration.bridger_root)
    if publication_path is None:
        return None

    brain = load_repository_brain(publication_path)
    from bridger.repository_brain.harness import load_memory_target_catalog

    catalog = load_memory_target_catalog(configuration)
    if (
        brain.manifest.repository_id != context.repository_id
        or brain.manifest.repository_revision != context.revision
        or brain.manifest.memory_target_catalog_id != catalog.catalog_id
        or brain.manifest.memory_target_catalog_version != catalog.catalog_version
    ):
        return None
    metrics = current_collector()
    if metrics is not None:
        metrics.fleet_run_id = getattr(brain.manifest, "fleet_run_id", None)

    graph_build = load_graph_snapshot(
        configuration.graph_root,
        brain.manifest.graph_snapshot_id,
    )
    validate_graph_snapshot(
        graph_build.snapshot_root,
        expected_context=context,
        expected_file_index=file_index,
        expected_config=GraphConstructionConfig(),
    )
    return RepositoryBrainBuildResult(
        mode=configuration.mode,
        graph_build=graph_build,
        publication_path=publication_path,
        token_usage_report_path=None,
        reused=True,
    )


async def _run_model_driven_pipeline(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    profile: LLMProfile,
    enrichment: GraphEnrichmentOverlay,
    on_stage: Callable[[str], None] | None,
    progress: InitProgressObserver | None,
    recovery_spec: MemoryFleetSpec | None = None,
) -> RepositoryBrainModelBuildResult:
    """Run the asynchronous memory fleet through publication."""
    # The complete composition is implemented in the harness module so the CLI
    # never becomes a second state authority.
    from bridger.repository_brain.harness import run_memory_harness

    _report_stage(on_stage, progress, InitStage.INITIALIZE_MEMORY_FLEET)
    return await run_memory_harness(
        configuration,
        context,
        file_index,
        symbol_index,
        graph_build,
        profile,
        enrichment,
        progress=progress,
        recovery_spec=recovery_spec,
    )


def _report_stage(
    callback: Callable[[str], None] | None,
    progress: InitProgressObserver | None,
    stage: InitStage,
) -> None:
    if callback is not None:
        try:
            callback(_LEGACY_STAGE_LABELS[stage])
        except Exception:
            pass
    notify_stage_started(progress, stage)


__all__ = [
    "InitMode",
    "InitRunConfiguration",
    "ReasoningEffort",
    "RepositoryBrainBuildError",
    "RepositoryBrainBuildResult",
    "RepositoryBrainModelBuildResult",
    "build_repository_brain",
    "format_repository_brain_error",
    "resolve_init_configuration",
]
