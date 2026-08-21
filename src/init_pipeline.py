"""Canonical orchestration for building one Bridger Repository Brain."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from extraction.service import extract_repository_facts
from graph.intelligence import build_graph_intelligence
from graph.lifecycle import create_graph_snapshot
from models.files import FileIndex
from models.graph import GraphBuildResult, GraphConstructionConfig
from models.repository import RepositoryContext
from models.symbols import SymbolIndex
from repository.service import prepare_repository


class InitMode(StrEnum):
    """Supported Repository Brain execution modes."""

    FULL = "full"
    DETERMINISTIC = "deterministic"
    TEST = "test"


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


def resolve_init_configuration(
    mode: InitMode,
    *,
    repository_root: Path | None = None,
    model_profile_name: str = "balanced",
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
    )


def build_repository_brain(
    configuration: InitRunConfiguration,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> RepositoryBrainBuildResult:
    """Run the documented Repository Brain pipeline for one repository."""
    _report_stage(on_stage, "Preparing repository")
    context, file_index = prepare_repository(configuration.repository_root)
    _report_stage(on_stage, "Extracting deterministic repository facts")
    symbol_index, _report, graphify_extraction = extract_repository_facts(
        context,
        file_index,
        cache_root=configuration.bridger_root / "cache",
    )
    graph_configuration = GraphConstructionConfig()
    _report_stage(on_stage, "Building deterministic graph intelligence")
    graph, diagnostics, derived_state = build_graph_intelligence(
        context,
        file_index,
        graphify_extraction,
        graph_configuration,
    )
    _report_stage(on_stage, "Publishing deterministic graph snapshot")
    graph_build = create_graph_snapshot(
        context,
        file_index,
        graph,
        diagnostics,
        derived_state,
        graph_configuration,
        configuration.graph_root,
    )
    if not configuration.enable_model_stages:
        return RepositoryBrainBuildResult(
            mode=configuration.mode,
            graph_build=graph_build,
        )

    _report_stage(on_stage, "Generating enrichment and Repository Brain memory")
    publication_path = asyncio.run(
        _run_model_driven_pipeline(
            configuration,
            context,
            file_index,
            symbol_index,
            graph_build,
            on_stage,
        )
    )
    return RepositoryBrainBuildResult(
        mode=configuration.mode,
        graph_build=graph_build,
        publication_path=publication_path,
    )


async def _run_model_driven_pipeline(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    on_stage: Callable[[str], None] | None,
) -> Path:
    """Run Layer 5 through publication using the existing durable contracts."""
    # The complete composition is implemented in the harness module so the CLI
    # never becomes a second state authority.
    from repository_brain.harness import prepare_model_layers, run_memory_harness

    try:
        profile, enrichment = prepare_model_layers(configuration, graph_build)
        _report_stage(on_stage, "Running memory fleet validation and publication")
        return await run_memory_harness(
            configuration,
            context,
            file_index,
            symbol_index,
            graph_build,
            profile,
            enrichment,
        )
    except Exception as error:
        message = str(error) or type(error).__name__
        raise RepositoryBrainBuildError(message) from error


def _report_stage(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


__all__ = [
    "InitMode",
    "InitRunConfiguration",
    "RepositoryBrainBuildError",
    "RepositoryBrainBuildResult",
    "build_repository_brain",
    "resolve_init_configuration",
]
