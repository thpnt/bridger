"""Filesystem publication for memory-harness Stage 0 and Stage 1 artifacts."""

import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from artifacts.writer import write_artifact
from memory.errors import FleetInitializationError, MemoryRunBindingError
from models.memory import (
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetTaskSpec,
    TargetTaskState,
)

_FLEET_SPEC_FILE = "fleet-spec.json"
_INITIALIZATION_DIRECTORY = "initialization"
_FLEET_STATE_FILE = "fleet-state.json"
_TARGETS_DIRECTORY = "targets"
_TARGET_SPEC_FILE = "target-task-spec.json"
_TARGET_STATE_FILE = "target-task-state.json"
_COMPLETION_STATE_FILE = "target-completion-state.json"


def persist_fleet_spec(spec: MemoryFleetSpec) -> None:
    """Atomically publish one immutable Stage 0 fleet specification."""
    runtime_root = Path(spec.runtime_root)
    require_path_segment(spec.fleet_run_id, "fleet_run_id")
    run_root = runtime_root / spec.fleet_run_id
    if run_root.exists():
        raise MemoryRunBindingError(f"fleet run already exists: {spec.fleet_run_id}")
    try:
        runtime_root.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{spec.fleet_run_id}-", dir=runtime_root)
        )
    except OSError as error:
        raise MemoryRunBindingError("could not prepare fleet runtime root") from error
    try:
        write_artifact(staging_root / _FLEET_SPEC_FILE, spec)
        persisted = MemoryFleetSpec.model_validate_json(
            (staging_root / _FLEET_SPEC_FILE).read_bytes()
        )
        if persisted != spec:
            raise MemoryRunBindingError("persisted fleet spec did not round-trip")
        if run_root.exists():
            raise MemoryRunBindingError(
                f"fleet run already exists: {spec.fleet_run_id}"
            )
        staging_root.replace(run_root)
        _fsync_directory(runtime_root)
    except BaseException:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def require_persisted_fleet_spec(fleet_spec: MemoryFleetSpec) -> None:
    """Require Stage 1 input to equal the exact persisted Stage 0 product."""
    spec_path = (
        Path(fleet_spec.runtime_root) / fleet_spec.fleet_run_id / _FLEET_SPEC_FILE
    )
    try:
        persisted = MemoryFleetSpec.model_validate_json(spec_path.read_bytes())
    except (OSError, ValidationError) as error:
        raise FleetInitializationError(
            "fleet spec is not a valid persisted Stage 0 binding"
        ) from error
    if persisted != fleet_spec:
        raise FleetInitializationError("persisted fleet spec does not match input")


def persist_initialization(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    task_specs: Sequence[TargetTaskSpec],
    task_states: Sequence[TargetTaskState],
    completion_states: Sequence[TargetCompletionState],
    workspaces: Sequence[Path],
) -> None:
    """Publish the complete Stage 1 state and workspaces as one logical commit."""
    run_root = Path(fleet_spec.runtime_root) / fleet_spec.fleet_run_id
    initialization_root = run_root / _INITIALIZATION_DIRECTORY
    if initialization_root.exists():
        raise FleetInitializationError("fleet is already initialized")

    output_root = Path(fleet_spec.output_root)
    if output_root.exists() and not output_root.is_dir():
        raise FleetInitializationError("output_root is not a directory")
    for workspace in workspaces:
        if workspace.exists() or workspace.is_symlink():
            raise FleetInitializationError(
                f"target workspace already exists: {workspace}"
            )

    try:
        staging_root = Path(tempfile.mkdtemp(prefix=".initialization-", dir=run_root))
    except OSError as error:
        raise FleetInitializationError("could not stage initialized fleet") from error

    created_workspaces: list[Path] = []
    output_root_created = False
    try:
        write_artifact(staging_root / _FLEET_STATE_FILE, fleet_state)
        for task_spec, task_state, completion_state in zip(
            task_specs,
            task_states,
            completion_states,
            strict=True,
        ):
            target_root = staging_root / _TARGETS_DIRECTORY / task_spec.target_id
            write_artifact(target_root / _TARGET_SPEC_FILE, task_spec)
            write_artifact(target_root / _TARGET_STATE_FILE, task_state)
            write_artifact(target_root / _COMPLETION_STATE_FILE, completion_state)

        if workspaces:
            output_root_created = not output_root.exists()
            output_root.mkdir(parents=True, exist_ok=True)
        for workspace in workspaces:
            workspace.mkdir()
            created_workspaces.append(workspace)
        if initialization_root.exists():
            raise FleetInitializationError("fleet is already initialized")
        staging_root.replace(initialization_root)
        _fsync_directory(run_root)
    except BaseException as error:
        shutil.rmtree(staging_root, ignore_errors=True)
        for workspace in reversed(created_workspaces):
            try:
                workspace.rmdir()
            except OSError:
                pass
        if output_root_created:
            try:
                output_root.rmdir()
            except OSError:
                pass
        if isinstance(error, FleetInitializationError):
            raise
        if isinstance(error, Exception):
            raise FleetInitializationError(
                "could not persist initialized fleet"
            ) from error
        raise


def require_path_segment(value: str, field_name: str) -> None:
    """Require a value to be safe as one filesystem path segment."""
    if Path(value).name != value or value in {"", ".", ".."}:
        raise ValueError(f"{field_name} must be a safe path segment")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "persist_fleet_spec",
    "persist_initialization",
    "require_path_segment",
    "require_persisted_fleet_spec",
]
