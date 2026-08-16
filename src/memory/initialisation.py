"""Stage 1 deterministic fleet and target initialization."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from memory.errors import FleetInitializationError, InvalidTargetArtifacts
from memory.persistence import (
    persist_initialization,
    require_path_segment,
    require_persisted_fleet_spec,
)
from memory.targets import _resolve_catalog_definitions
from models.memory import (
    CompletionItemState,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    SourceBinding,
    TargetCompletionState,
    TargetDefinition,
    TargetTaskSpec,
    TargetTaskState,
)

_SUPPORTED_SCHEMA_VERSION = 1


def initialize_fleet(
    fleet_spec: MemoryFleetSpec,
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
) -> tuple[
    FleetRunState,
    list[TargetTaskSpec],
    list[TargetTaskState],
    list[TargetCompletionState],
]:
    """Materialize and persist the complete initial fleet as one logical commit."""
    try:
        validated_spec = MemoryFleetSpec.model_validate(
            fleet_spec.model_dump(mode="python")
        )
        validated_catalog, definitions_by_target = _resolve_catalog_definitions(
            catalog,
            definitions,
            require_exact=False,
            required_target_ids=set(validated_spec.target_ids),
        )
        _validate_fleet_catalog(validated_spec, validated_catalog)
        _require_bound_fleet_spec(validated_spec)

        target_task_ids = {
            target_id: _target_task_id(validated_spec.fleet_run_id, target_id)
            for target_id in validated_spec.target_ids
        }
        if len(target_task_ids.values()) != len(set(target_task_ids.values())):
            raise FleetInitializationError("target task identity collision")
        _validate_dependencies(definitions_by_target, validated_spec.target_ids)

        task_specs: list[TargetTaskSpec] = []
        task_states: list[TargetTaskState] = []
        completion_states: list[TargetCompletionState] = []
        output_root = Path(validated_spec.output_root).resolve()
        workspaces: list[Path] = []

        for target_id in validated_spec.target_ids:
            require_path_segment(target_id, "target_id")
            definition = definitions_by_target[target_id]
            target_task_id = target_task_ids[target_id]
            workspace = (output_root / target_id).resolve()
            _require_within(workspace, output_root)
            workspaces.append(workspace)
            task_specs.append(
                TargetTaskSpec(
                    target_task_id=target_task_id,
                    fleet_run_id=validated_spec.fleet_run_id,
                    target_id=target_id,
                    target_contract_version=definition.target_contract_version,
                    source=SourceBinding.model_validate(
                        validated_spec.source.model_dump(mode="python")
                    ),
                    worker_profile_id=validated_spec.default_worker_profile_id,
                    reviewer_profile_id=validated_spec.default_reviewer_profile_id,
                    permission_profile_id=validated_spec.default_permission_profile_id,
                    budget=validated_spec.default_target_budget,
                    target_workspace=str(workspace),
                    depends_on_target_task_ids=[
                        target_task_ids[dependency]
                        for dependency in definition.depends_on
                    ],
                )
            )
            task_states.append(
                TargetTaskState(
                    target_task_id=target_task_id,
                    fleet_run_id=validated_spec.fleet_run_id,
                )
            )
            completion_states.append(
                TargetCompletionState(
                    target_task_id=target_task_id,
                    items=[
                        CompletionItemState(obligation_id=obligation.obligation_id)
                        for obligation in definition.completion_obligations
                    ],
                )
            )

        if len(workspaces) != len(set(workspaces)):
            raise FleetInitializationError("target workspace collision")
        fleet_state = FleetRunState(
            fleet_run_id=validated_spec.fleet_run_id,
            target_task_ids=[spec.target_task_id for spec in task_specs],
        )
        _validate_initialization_bundle(
            validated_spec,
            definitions_by_target,
            fleet_state,
            task_specs,
            task_states,
            completion_states,
        )
        persist_initialization(
            validated_spec,
            fleet_state,
            task_specs,
            task_states,
            completion_states,
            workspaces,
        )
        return fleet_state, task_specs, task_states, completion_states
    except FleetInitializationError:
        raise
    except InvalidTargetArtifacts as error:
        raise FleetInitializationError(str(error)) from error
    except (OSError, TypeError, ValidationError, ValueError) as error:
        raise FleetInitializationError("fleet initialization is invalid") from error


def _validate_fleet_catalog(
    fleet_spec: MemoryFleetSpec,
    catalog: MemoryTargetCatalog,
) -> None:
    if (
        fleet_spec.target_catalog_id,
        fleet_spec.target_catalog_version,
    ) != (catalog.catalog_id, catalog.catalog_version):
        raise FleetInitializationError("fleet spec does not match target catalog")
    active_targets = set(fleet_spec.target_ids)
    catalog_order = [
        entry.target_id
        for entry in catalog.targets
        if entry.target_id in active_targets
    ]
    if catalog_order != fleet_spec.target_ids:
        raise FleetInitializationError(
            "fleet target_ids do not preserve deterministic catalog order"
        )


def _require_bound_fleet_spec(fleet_spec: MemoryFleetSpec) -> None:
    runtime_root = Path(fleet_spec.runtime_root)
    output_root = Path(fleet_spec.output_root)
    if not runtime_root.is_absolute() or not output_root.is_absolute():
        raise FleetInitializationError("fleet roots must be absolute")
    if runtime_root == output_root:
        raise FleetInitializationError("runtime_root and output_root must be distinct")
    if fleet_spec.schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise FleetInitializationError("unsupported fleet spec schema version")
    require_path_segment(fleet_spec.fleet_run_id, "fleet_run_id")
    require_persisted_fleet_spec(fleet_spec)


def _target_task_id(fleet_run_id: str, target_id: str) -> str:
    identity = f"bridger-memory-target:{fleet_run_id}:{target_id}"
    return uuid.uuid5(uuid.NAMESPACE_URL, identity).hex


def _validate_dependencies(
    definitions_by_target: Mapping[str, TargetDefinition],
    target_ids: Sequence[str],
) -> None:
    active_targets = set(target_ids)
    for target_id in target_ids:
        for dependency in definitions_by_target[target_id].depends_on:
            if dependency == target_id:
                raise FleetInitializationError("a target cannot depend on itself")
            if dependency not in active_targets:
                raise FleetInitializationError(
                    f"target dependency is inactive or invalid: {dependency}"
                )

    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(target_id: str) -> None:
        if target_id in visited:
            return
        if target_id in visiting:
            raise FleetInitializationError("target dependency cycle detected")
        visiting.add(target_id)
        for dependency in definitions_by_target[target_id].depends_on:
            visit(dependency)
        visiting.remove(target_id)
        visited.add(target_id)

    for target_id in target_ids:
        visit(target_id)


def _validate_initialization_bundle(
    fleet_spec: MemoryFleetSpec,
    definitions_by_target: Mapping[str, TargetDefinition],
    fleet_state: FleetRunState,
    task_specs: Sequence[TargetTaskSpec],
    task_states: Sequence[TargetTaskState],
    completion_states: Sequence[TargetCompletionState],
) -> None:
    if fleet_state != FleetRunState(
        fleet_run_id=fleet_spec.fleet_run_id,
        target_task_ids=[spec.target_task_id for spec in task_specs],
    ):
        raise FleetInitializationError("fleet state does not have initial defaults")
    if not (
        len(task_specs)
        == len(task_states)
        == len(completion_states)
        == len(fleet_spec.target_ids)
    ):
        raise FleetInitializationError("initialized target object counts differ")

    for target_id, task_spec, task_state, completion_state in zip(
        fleet_spec.target_ids,
        task_specs,
        task_states,
        completion_states,
        strict=True,
    ):
        definition = definitions_by_target[target_id]
        if task_spec.target_id != target_id:
            raise FleetInitializationError("task target identity does not match")
        if task_spec.source != fleet_spec.source:
            raise FleetInitializationError("task source does not match fleet source")
        if task_spec.target_contract_version != definition.target_contract_version:
            raise FleetInitializationError(
                "task target contract version does not match"
            )
        if task_state != TargetTaskState(
            target_task_id=task_spec.target_task_id,
            fleet_run_id=fleet_spec.fleet_run_id,
        ):
            raise FleetInitializationError(
                "target state does not have initial defaults"
            )
        expected_completion = TargetCompletionState(
            target_task_id=task_spec.target_task_id,
            items=[
                CompletionItemState(obligation_id=obligation.obligation_id)
                for obligation in definition.completion_obligations
            ],
        )
        if completion_state != expected_completion:
            raise FleetInitializationError(
                "completion state does not exactly match target obligations"
            )


def _require_within(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise FleetInitializationError(
            "target workspace must remain inside output_root"
        ) from error


__all__ = ["initialize_fleet"]
