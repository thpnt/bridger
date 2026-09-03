"""Canonical orchestration for building one Bridger Repository Brain."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
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
from bridger.repository_brain.loader import load_repository_brain
from bridger.repository_brain.publication import resolve_current_repository_brain

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


@dataclass(frozen=True)
class RepositoryBrainModelBuildResult:
    """Artifacts produced by the model-driven portion of init."""

    publication_path: Path
    token_usage_report_path: Path


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
    )


def build_repository_brain(
    configuration: InitRunConfiguration,
    *,
    on_stage: Callable[[str], None] | None = None,
    progress: InitProgressObserver | None = None,
) -> RepositoryBrainBuildResult:
    """Run the documented Repository Brain pipeline for one repository."""
    _report_stage(on_stage, progress, InitStage.PREPARE_REPOSITORY)
    context, file_index = prepare_repository(configuration.repository_root)
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
            return reused
    recovery_spec = None
    if configuration.enable_model_stages and not configuration.fresh:
        try:
            from bridger.repository_brain.harness import discover_resumable_fleet

            recovery_spec = discover_resumable_fleet(configuration, context)
        except Exception as error:
            message = format_repository_brain_error(error)
            raise RepositoryBrainBuildError(message) from error
    _report_stage(on_stage, progress, InitStage.EXTRACT_FACTS)
    symbol_index, _report, graphify_extraction = extract_repository_facts(
        context,
        file_index,
        cache_root=configuration.bridger_root / "cache",
    )
    if recovery_spec is None:
        graph_configuration = GraphConstructionConfig()
        _report_stage(on_stage, progress, InitStage.BUILD_GRAPH)
        graph, diagnostics, derived_state = build_graph_intelligence(
            context,
            file_index,
            graphify_extraction,
            graph_configuration,
        )
        _report_stage(on_stage, progress, InitStage.PUBLISH_GRAPH)
        graph_build = create_graph_snapshot(
            context,
            file_index,
            graph,
            diagnostics,
            derived_state,
            graph_configuration,
            configuration.graph_root,
        )
    else:
        try:
            from bridger.repository_brain.harness import load_recovery_model_layers

            graph_build, profile, enrichment = load_recovery_model_layers(
                configuration,
                context,
                file_index,
                recovery_spec,
            )
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

            profile, enrichment = prepare_model_layers(configuration, graph_build)
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
    except Exception as error:
        message = format_repository_brain_error(error)
        raise RepositoryBrainBuildError(message) from error
    return RepositoryBrainBuildResult(
        mode=configuration.mode,
        graph_build=graph_build,
        publication_path=publication_path,
        token_usage_report_path=token_usage_report_path,
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
