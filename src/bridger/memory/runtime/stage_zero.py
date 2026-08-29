"""Stage 0 target activation and immutable memory-run binding."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

from pydantic import ValidationError

from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.files import FileIndex
from bridger.contracts.graph import GraphBuildResult
from bridger.contracts.memory.core import (
    ActivationMode,
    ExecutionBudget,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    SourceBinding,
    TargetDefinition,
)
from bridger.contracts.repository import RepositoryContext
from bridger.contracts.symbols import SymbolIndex
from bridger.memory.errors import (
    InvalidTargetArtifacts,
    MemoryRunBindingError,
    TargetActivationError,
)
from bridger.memory.persistence.store import persist_fleet_spec, require_path_segment
from bridger.memory.targets import _resolve_catalog_definitions

ActivationRule: TypeAlias = Callable[
    [RepositoryContext, FileIndex, SymbolIndex, GraphBuildResult],
    bool,
]


def resolve_target_activation(
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    repository_context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    *,
    activation_rules: Mapping[str, ActivationRule] | None = None,
) -> list[str]:
    """Resolve active targets in catalog order using deterministic rules only."""
    validated_catalog, definitions_by_target = _resolve_catalog_definitions(
        catalog,
        definitions,
        require_exact=False,
    )
    rules = activation_rules or {}
    active_target_ids: list[str] = []
    for entry in validated_catalog.targets:
        definition = definitions_by_target[entry.target_id]
        if definition.activation.mode is ActivationMode.ALWAYS:
            active_target_ids.append(entry.target_id)
            continue

        rule_id = definition.activation.rule_id
        if rule_id is None:
            raise TargetActivationError(
                f"conditional target has no activation rule: {entry.target_id}"
            )
        rule = rules.get(rule_id)
        if rule is None:
            raise TargetActivationError(f"unknown activation rule: {rule_id}")
        try:
            is_active = rule(
                repository_context,
                file_index,
                symbol_index,
                graph_build,
            )
        except Exception as error:
            raise TargetActivationError(f"activation rule failed: {rule_id}") from error
        if not isinstance(is_active, bool):
            raise TargetActivationError(
                f"activation rule did not return bool: {rule_id}"
            )
        if is_active:
            active_target_ids.append(entry.target_id)
    return active_target_ids


def bind_memory_run(
    repository_context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    *,
    runtime_profile_id: str,
    default_worker_profile_id: str,
    default_reviewer_profile_id: str,
    default_permission_profile_id: str,
    fleet_budget: ExecutionBudget,
    default_target_budget: ExecutionBudget,
    runtime_root: Path,
    output_root: Path,
    max_concurrent_targets: int = 1,
    enrichment_overlay: GraphEnrichmentOverlay | None = None,
    activation_rules: Mapping[str, ActivationRule] | None = None,
) -> MemoryFleetSpec:
    """Bind compatible upstream authorities into one persisted immutable run spec."""
    try:
        _validate_upstream_compatibility(
            repository_context,
            file_index,
            symbol_index,
            graph_build,
            enrichment_overlay,
        )
        normalized_runtime_root, normalized_output_root = _normalize_roots(
            runtime_root,
            output_root,
        )
        validated_fleet_budget = ExecutionBudget.model_validate(
            fleet_budget.model_dump(mode="python")
        )
        validated_target_budget = ExecutionBudget.model_validate(
            default_target_budget.model_dump(mode="python")
        )
        target_ids = resolve_target_activation(
            catalog,
            definitions,
            repository_context,
            file_index,
            symbol_index,
            graph_build,
            activation_rules=activation_rules,
        )
        for target_id in target_ids:
            require_path_segment(target_id, "target_id")
        spec = MemoryFleetSpec(
            schema_version=2,
            fleet_run_id=uuid.uuid4().hex,
            source=SourceBinding(
                repository_id=repository_context.repository_id,
                repository_revision=repository_context.revision,
                graph_snapshot_id=graph_build.manifest.snapshot_id,
                enrichment_overlay_id=(
                    enrichment_overlay.overlay_id
                    if enrichment_overlay is not None
                    else None
                ),
            ),
            target_catalog_id=catalog.catalog_id,
            target_catalog_version=catalog.catalog_version,
            target_ids=target_ids,
            runtime_profile_id=runtime_profile_id,
            default_worker_profile_id=default_worker_profile_id,
            default_reviewer_profile_id=default_reviewer_profile_id,
            default_permission_profile_id=default_permission_profile_id,
            fleet_budget=validated_fleet_budget,
            default_target_budget=validated_target_budget,
            max_concurrent_targets=max_concurrent_targets,
            runtime_root=str(normalized_runtime_root),
            output_root=str(normalized_output_root),
        )
        persist_fleet_spec(spec)
        return spec
    except MemoryRunBindingError:
        raise
    except (InvalidTargetArtifacts, TargetActivationError) as error:
        raise MemoryRunBindingError(str(error)) from error
    except (OSError, TypeError, ValidationError, ValueError) as error:
        raise MemoryRunBindingError("memory run binding is invalid") from error


def _validate_upstream_compatibility(
    repository_context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    enrichment_overlay: GraphEnrichmentOverlay | None,
) -> None:
    expected_identity = (
        repository_context.repository_id,
        repository_context.revision,
        repository_context.scope_path,
    )
    if (
        file_index.repository_id,
        file_index.revision,
        file_index.scope_path,
    ) != expected_identity:
        raise ValueError("FileIndex does not belong to RepositoryContext")
    if (
        symbol_index.repository_id,
        symbol_index.revision,
        symbol_index.scope_path,
    ) != expected_identity:
        raise ValueError("SymbolIndex does not belong to RepositoryContext")
    if (
        graph_build.manifest.repository_id,
        graph_build.manifest.revision,
        graph_build.manifest.scope_path,
    ) != expected_identity:
        raise ValueError("graph snapshot does not belong to RepositoryContext")
    if (
        enrichment_overlay is not None
        and enrichment_overlay.graph_snapshot_id != graph_build.manifest.snapshot_id
    ):
        raise ValueError("enrichment overlay belongs to a different graph snapshot")


def _normalize_roots(runtime_root: Path, output_root: Path) -> tuple[Path, Path]:
    runtime = Path(runtime_root).resolve()
    output = Path(output_root).resolve()
    if runtime == output:
        raise ValueError("runtime_root and output_root must be distinct")
    for path, field_name in ((runtime, "runtime_root"), (output, "output_root")):
        if path.exists() and not path.is_dir():
            raise ValueError(f"{field_name} must be a directory")
    return runtime, output


__all__ = ["ActivationRule", "bind_memory_run", "resolve_target_activation"]
