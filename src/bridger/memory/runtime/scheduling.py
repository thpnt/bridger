"""Stage 2 deterministic target scheduling."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError

from bridger.contracts.memory.core import (
    ExecutionBudget,
    ExecutionUsage,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
    budgeted_input_tokens,
)
from bridger.memory.errors import FleetSchedulingError
from bridger.memory.persistence.durability import FleetRuntimeStore

_SCHEDULABLE_TARGET_PHASES = {TargetPhase.INITIALIZED, TargetPhase.REPAIR}
_ACTIVE_TARGET_PHASES = {
    TargetPhase.SCHEDULED,
    TargetPhase.HYDRATING,
    TargetPhase.WORKING,
    TargetPhase.FINALIZING,
    TargetPhase.VALIDATING,
    TargetPhase.REVIEWING,
}
_FAILED_DEPENDENCY_PHASES = {
    TargetPhase.BLOCKED,
    TargetPhase.EXHAUSTED,
    TargetPhase.FAILED,
    TargetPhase.STOPPED,
}
_SCHEDULABLE_FLEET_PHASES = {FleetPhase.INITIALIZED, FleetPhase.RUNNING}


def schedule_runnable_targets(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    *,
    persistence: FleetRuntimeStore | None = None,
) -> list[str]:
    """Admit runnable targets and return newly scheduled task IDs in fleet order."""
    specs_by_task, states_by_task = _validate_inputs(
        fleet_spec,
        fleet_state,
        target_specs,
        target_states,
    )

    if fleet_state.phase not in _SCHEDULABLE_FLEET_PHASES:
        return []

    target_order = {
        target_id: index for index, target_id in enumerate(fleet_spec.target_ids)
    }
    ordered_specs = sorted(target_specs, key=lambda spec: target_order[spec.target_id])
    _apply_dependency_blocking(ordered_specs, states_by_task)
    _apply_target_exhaustion(ordered_specs, states_by_task)
    _apply_dependency_blocking(ordered_specs, states_by_task)

    active_count = sum(
        state.phase in _ACTIVE_TARGET_PHASES for state in states_by_task.values()
    )
    available_slots = fleet_spec.max_concurrent_targets - active_count
    if available_slots < 0:
        raise FleetSchedulingError("active target count exceeds max_concurrent_targets")

    remaining_fleet_cycles = fleet_spec.fleet_budget.max_cycles - (
        fleet_state.usage.cycles
    )
    remaining_fleet_repairs = fleet_spec.fleet_budget.max_repair_cycles - (
        fleet_state.usage.repair_cycles
    )
    scheduled: list[str] = []

    for spec in ordered_specs:
        if len(scheduled) >= available_slots or remaining_fleet_cycles <= 0:
            break
        state = states_by_task[spec.target_task_id]
        if state.phase not in _SCHEDULABLE_TARGET_PHASES:
            continue
        if not _dependencies_accepted(spec, states_by_task):
            continue
        is_repair = state.phase is TargetPhase.REPAIR
        if not _budget_allows(fleet_spec.fleet_budget, fleet_state.usage, is_repair):
            continue
        if is_repair and remaining_fleet_repairs <= 0:
            continue

        state.phase = TargetPhase.SCHEDULED
        scheduled.append(spec.target_task_id)
        remaining_fleet_cycles -= 1
        if is_repair:
            remaining_fleet_repairs -= 1

    if scheduled and fleet_state.phase is FleetPhase.INITIALIZED:
        fleet_state.phase = FleetPhase.RUNNING

    _apply_terminal_fleet_phase(
        fleet_spec,
        fleet_state,
        ordered_specs,
        specs_by_task,
        states_by_task,
    )
    if persistence is not None:
        persistence.persist_scheduling_snapshot(
            fleet_state,
            target_specs,
            target_states,
            scheduled,
        )
    return scheduled


def _validate_inputs(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
) -> tuple[dict[str, TargetTaskSpec], dict[str, TargetTaskState]]:
    try:
        MemoryFleetSpec.model_validate(fleet_spec.model_dump(mode="python"))
        FleetRunState.model_validate(fleet_state.model_dump(mode="python"))
        for target_spec in target_specs:
            TargetTaskSpec.model_validate(target_spec.model_dump(mode="python"))
        for target_state in target_states:
            TargetTaskState.model_validate(target_state.model_dump(mode="python"))
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        raise FleetSchedulingError("scheduling inputs are malformed") from error

    if fleet_spec.fleet_run_id != fleet_state.fleet_run_id:
        raise FleetSchedulingError("fleet spec and state identities do not match")

    specs_by_task = _index_unique_specs(target_specs)
    states_by_task = _index_unique_states(target_states)
    fleet_task_ids = set(fleet_state.target_task_ids)
    if set(specs_by_task) != fleet_task_ids or set(states_by_task) != fleet_task_ids:
        raise FleetSchedulingError(
            "fleet target_task_ids must exactly match target specs and states"
        )

    specs_by_target: dict[str, TargetTaskSpec] = {}
    for task_id in fleet_state.target_task_ids:
        spec = specs_by_task[task_id]
        state = states_by_task[task_id]
        if spec.fleet_run_id != fleet_spec.fleet_run_id:
            raise FleetSchedulingError("target spec belongs to a different fleet")
        if state.fleet_run_id != fleet_spec.fleet_run_id:
            raise FleetSchedulingError("target state belongs to a different fleet")
        if state.target_task_id != spec.target_task_id:
            raise FleetSchedulingError("target spec and state identities do not match")
        if spec.source != fleet_spec.source:
            raise FleetSchedulingError("target source does not match fleet source")
        if spec.target_id in specs_by_target:
            raise FleetSchedulingError("duplicate target identity")
        specs_by_target[spec.target_id] = spec

    if set(specs_by_target) != set(fleet_spec.target_ids):
        raise FleetSchedulingError(
            "fleet target_ids must exactly match instantiated target specs"
        )
    if any(
        dependency not in fleet_task_ids
        for spec in target_specs
        for dependency in spec.depends_on_target_task_ids
    ):
        raise FleetSchedulingError("target dependency is outside the fleet")
    _validate_dependency_graph(target_specs)

    active_count = sum(
        state.phase in _ACTIVE_TARGET_PHASES for state in states_by_task.values()
    )
    if active_count > fleet_spec.max_concurrent_targets:
        raise FleetSchedulingError("active target count exceeds max_concurrent_targets")
    if fleet_state.phase is FleetPhase.INITIALIZED and active_count:
        raise FleetSchedulingError("initialized fleet cannot contain active targets")
    if fleet_state.phase is FleetPhase.ACCEPTED and any(
        state.phase is not TargetPhase.ACCEPTED for state in states_by_task.values()
    ):
        raise FleetSchedulingError("accepted fleet requires all targets accepted")
    return specs_by_task, states_by_task


def _index_unique_specs(
    target_specs: Sequence[TargetTaskSpec],
) -> dict[str, TargetTaskSpec]:
    indexed = {spec.target_task_id: spec for spec in target_specs}
    if len(indexed) != len(target_specs):
        raise FleetSchedulingError("duplicate target task spec identity")
    return indexed


def _index_unique_states(
    target_states: Sequence[TargetTaskState],
) -> dict[str, TargetTaskState]:
    indexed = {state.target_task_id: state for state in target_states}
    if len(indexed) != len(target_states):
        raise FleetSchedulingError("duplicate target task state identity")
    return indexed


def _validate_dependency_graph(target_specs: Sequence[TargetTaskSpec]) -> None:
    dependencies = {
        spec.target_task_id: spec.depends_on_target_task_ids for spec in target_specs
    }
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise FleetSchedulingError("target dependency cycle detected")
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)


def _apply_dependency_blocking(
    ordered_specs: Sequence[TargetTaskSpec],
    states_by_task: dict[str, TargetTaskState],
) -> None:
    changed = True
    while changed:
        changed = False
        for spec in ordered_specs:
            state = states_by_task[spec.target_task_id]
            if state.phase not in _SCHEDULABLE_TARGET_PHASES:
                continue
            dependency_phases = (
                states_by_task[dependency].phase
                for dependency in spec.depends_on_target_task_ids
            )
            if any(phase in _FAILED_DEPENDENCY_PHASES for phase in dependency_phases):
                state.phase = TargetPhase.BLOCKED
                changed = True


def _apply_target_exhaustion(
    ordered_specs: Sequence[TargetTaskSpec],
    states_by_task: dict[str, TargetTaskState],
) -> None:
    for spec in ordered_specs:
        state = states_by_task[spec.target_task_id]
        if state.phase in _SCHEDULABLE_TARGET_PHASES and not _budget_allows(
            spec.budget,
            state.usage,
            state.phase is TargetPhase.REPAIR,
        ):
            state.phase = TargetPhase.EXHAUSTED


def _budget_allows(
    budget: ExecutionBudget,
    usage: ExecutionUsage,
    is_repair: bool,
) -> bool:
    if usage.cycles >= budget.max_cycles:
        return False
    if usage.model_calls >= budget.max_model_calls:
        return False
    if usage.tool_calls >= budget.max_tool_calls:
        return False
    if budget.max_input_tokens is not None and (
        budgeted_input_tokens(usage) >= budget.max_input_tokens
    ):
        return False
    if budget.max_output_tokens is not None and (
        usage.output_tokens >= budget.max_output_tokens
    ):
        return False
    return not is_repair or usage.repair_cycles < budget.max_repair_cycles


def _dependencies_accepted(
    target_spec: TargetTaskSpec,
    states_by_task: dict[str, TargetTaskState],
) -> bool:
    return all(
        states_by_task[dependency].phase is TargetPhase.ACCEPTED
        for dependency in target_spec.depends_on_target_task_ids
    )


def _apply_terminal_fleet_phase(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    ordered_specs: Sequence[TargetTaskSpec],
    specs_by_task: dict[str, TargetTaskSpec],
    states_by_task: dict[str, TargetTaskState],
) -> None:
    if fleet_state.phase is not FleetPhase.RUNNING:
        return
    phases = [states_by_task[spec.target_task_id].phase for spec in ordered_specs]
    if all(phase is TargetPhase.ACCEPTED for phase in phases):
        return
    if any(phase in _ACTIVE_TARGET_PHASES for phase in phases):
        return
    if any(
        _can_still_reach_accepted(
            spec.target_task_id,
            fleet_spec,
            fleet_state,
            specs_by_task,
            states_by_task,
            set(),
        )
        for spec in ordered_specs
        if states_by_task[spec.target_task_id].phase is not TargetPhase.ACCEPTED
    ):
        return

    if TargetPhase.FAILED in phases:
        fleet_state.phase = FleetPhase.FAILED
    elif TargetPhase.EXHAUSTED in phases or _fleet_budget_exhausted_for_remaining(
        fleet_spec,
        fleet_state,
        ordered_specs,
        states_by_task,
    ):
        fleet_state.phase = FleetPhase.EXHAUSTED
    elif TargetPhase.STOPPED in phases:
        fleet_state.phase = FleetPhase.STOPPED
    else:
        fleet_state.phase = FleetPhase.BLOCKED


def _can_still_reach_accepted(
    task_id: str,
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    specs_by_task: dict[str, TargetTaskSpec],
    states_by_task: dict[str, TargetTaskState],
    visiting: set[str],
) -> bool:
    state = states_by_task[task_id]
    if state.phase is TargetPhase.ACCEPTED or state.phase in _ACTIVE_TARGET_PHASES:
        return True
    if state.phase not in _SCHEDULABLE_TARGET_PHASES:
        return False
    if not _budget_allows(
        fleet_spec.fleet_budget,
        fleet_state.usage,
        state.phase is TargetPhase.REPAIR,
    ):
        return False
    if task_id in visiting:
        raise FleetSchedulingError("target dependency cycle detected")
    visiting.add(task_id)
    can_progress = all(
        _can_still_reach_accepted(
            dependency,
            fleet_spec,
            fleet_state,
            specs_by_task,
            states_by_task,
            visiting,
        )
        for dependency in specs_by_task[task_id].depends_on_target_task_ids
    )
    visiting.remove(task_id)
    return can_progress


def _fleet_budget_exhausted_for_remaining(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    ordered_specs: Sequence[TargetTaskSpec],
    states_by_task: dict[str, TargetTaskState],
) -> bool:
    remaining = [
        states_by_task[spec.target_task_id]
        for spec in ordered_specs
        if states_by_task[spec.target_task_id].phase in _SCHEDULABLE_TARGET_PHASES
    ]
    return any(
        not _budget_allows(
            fleet_spec.fleet_budget,
            fleet_state.usage,
            state.phase is TargetPhase.REPAIR,
        )
        for state in remaining
    )


__all__ = ["schedule_runnable_targets"]
