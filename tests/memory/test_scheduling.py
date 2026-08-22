"""Stage 2 deterministic scheduling contract tests."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from bridger.contracts.memory.core import (
    ExecutionBudget,
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    SourceBinding,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.memory import FleetSchedulingError, schedule_runnable_targets

_SOURCE = SourceBinding(
    repository_id="repository-1",
    repository_revision="a" * 40,
    graph_snapshot_id="snapshot-1",
)
_BUDGET = ExecutionBudget(
    max_cycles=10,
    max_model_calls=10,
    max_tool_calls=10,
    max_repair_cycles=3,
)


def test_schedules_independent_targets_in_fleet_order_up_to_concurrency() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture", "testing", "operations"],
        max_concurrent_targets=2,
    )

    scheduled = schedule_runnable_targets(
        fleet_spec,
        fleet_state,
        list(reversed(specs)),
        list(reversed(states)),
    )

    assert scheduled == ["task-architecture", "task-testing"]
    assert _state(states, "architecture").phase is TargetPhase.SCHEDULED
    assert _state(states, "testing").phase is TargetPhase.SCHEDULED
    assert _state(states, "operations").phase is TargetPhase.INITIALIZED
    assert fleet_state.phase is FleetPhase.RUNNING
    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []


@pytest.mark.parametrize(
    "active_phase",
    [
        TargetPhase.SCHEDULED,
        TargetPhase.HYDRATING,
        TargetPhase.WORKING,
        TargetPhase.FINALIZING,
        TargetPhase.VALIDATING,
        TargetPhase.REVIEWING,
    ],
)
def test_exact_active_phases_consume_capacity(active_phase: TargetPhase) -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture", "testing"],
        max_concurrent_targets=1,
        fleet_phase=FleetPhase.RUNNING,
    )
    _set_phase(_state(states, "architecture"), active_phase)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert _state(states, "testing").phase is TargetPhase.INITIALIZED


@pytest.mark.parametrize(
    "non_slot_phase",
    [
        TargetPhase.ACCEPTED,
        TargetPhase.BLOCKED,
        TargetPhase.EXHAUSTED,
        TargetPhase.FAILED,
        TargetPhase.STOPPED,
    ],
)
def test_non_slot_phases_leave_capacity(non_slot_phase: TargetPhase) -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture", "testing"],
        max_concurrent_targets=1,
        fleet_phase=FleetPhase.RUNNING,
    )
    _set_phase(_state(states, "architecture"), non_slot_phase)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-testing"
    ]


def test_accepted_dependency_schedules_but_progressing_dependency_waits() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["repository", "testing", "operations"],
        dependencies={"testing": ["repository"]},
        max_concurrent_targets=2,
        fleet_phase=FleetPhase.RUNNING,
    )
    _set_phase(_state(states, "repository"), TargetPhase.WORKING)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-operations"
    ]
    assert _state(states, "testing").phase is TargetPhase.INITIALIZED

    _set_phase(_state(states, "repository"), TargetPhase.ACCEPTED)
    _set_phase(_state(states, "operations"), TargetPhase.ACCEPTED)
    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-testing"
    ]


@pytest.mark.parametrize(
    "dependency_phase",
    [
        TargetPhase.BLOCKED,
        TargetPhase.EXHAUSTED,
        TargetPhase.FAILED,
        TargetPhase.STOPPED,
    ],
)
def test_terminal_dependency_blocks_transitive_dependents_but_not_siblings(
    dependency_phase: TargetPhase,
) -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["a", "b", "c", "sibling"],
        dependencies={"b": ["a"], "c": ["b"]},
        max_concurrent_targets=1,
        fleet_phase=FleetPhase.RUNNING,
    )
    _set_phase(_state(states, "a"), dependency_phase)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-sibling"
    ]
    assert _state(states, "b").phase is TargetPhase.BLOCKED
    assert _state(states, "c").phase is TargetPhase.BLOCKED


def test_repair_readmission_uses_same_task_and_preserves_usage() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture"],
        fleet_phase=FleetPhase.RUNNING,
    )
    state = states[0]
    state.usage.cycles = 2
    state.usage.repair_cycles = 1
    state.open_finding_refs.append(
        FindingRef(finding_id="finding-1", origin=FindingOrigin.TARGET_REVIEW)
    )
    state.phase = TargetPhase.REPAIR

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-architecture"
    ]
    assert state.phase is TargetPhase.SCHEDULED
    assert state.usage.cycles == 2
    assert state.usage.repair_cycles == 1


@pytest.mark.parametrize(
    ("usage_field", "budget_field"),
    [
        ("cycles", "max_cycles"),
        ("model_calls", "max_model_calls"),
        ("tool_calls", "max_tool_calls"),
        ("input_tokens", "max_input_tokens"),
        ("output_tokens", "max_output_tokens"),
    ],
)
def test_target_hard_budget_limits_exhaust_target(
    usage_field: str,
    budget_field: str,
) -> None:
    budget = _BUDGET.model_copy(update={budget_field: 4})
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture"],
        target_budget=budget,
        fleet_phase=FleetPhase.RUNNING,
    )
    setattr(states[0].usage, usage_field, 4)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert states[0].phase is TargetPhase.EXHAUSTED
    assert fleet_state.phase is FleetPhase.EXHAUSTED


def test_cached_input_does_not_consume_cumulative_input_budget() -> None:
    budget = _BUDGET.model_copy(update={"max_input_tokens": 4})
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture"],
        target_budget=budget,
        fleet_phase=FleetPhase.RUNNING,
    )
    states[0].usage.input_tokens = 4
    states[0].usage.cached_input_tokens = 1

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-architecture"
    ]
    assert states[0].phase is TargetPhase.SCHEDULED


def test_unconfigured_token_budgets_do_not_restrict_admission() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(["architecture"])
    states[0].usage.input_tokens = 1_000_000
    states[0].usage.output_tokens = 1_000_000

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-architecture"
    ]


def test_repair_requires_target_and_fleet_repair_headroom() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["repair", "new"],
        max_concurrent_targets=2,
        fleet_phase=FleetPhase.RUNNING,
    )
    repair = _state(states, "repair")
    repair.open_finding_refs.append(
        FindingRef(finding_id="finding-1", origin=FindingOrigin.TARGET_REVIEW)
    )
    repair.phase = TargetPhase.REPAIR
    fleet_state.usage.repair_cycles = fleet_spec.fleet_budget.max_repair_cycles

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-new"
    ]
    assert repair.phase is TargetPhase.REPAIR

    _set_phase(_state(states, "new"), TargetPhase.ACCEPTED)
    repair.usage.repair_cycles = specs[0].budget.max_repair_cycles
    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert repair.phase is TargetPhase.EXHAUSTED


def test_fleet_cycle_headroom_caps_one_pass_without_charging_usage() -> None:
    fleet_budget = _BUDGET.model_copy(update={"max_cycles": 3})
    fleet_spec, fleet_state, specs, states = _fleet(
        ["a", "b", "c"],
        fleet_budget=fleet_budget,
        max_concurrent_targets=3,
        fleet_phase=FleetPhase.RUNNING,
    )
    fleet_state.usage.cycles = 2

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-a"
    ]
    assert fleet_state.usage.cycles == 2
    assert _state(states, "b").phase is TargetPhase.INITIALIZED


def test_scheduler_does_not_predict_unknown_per_cycle_consumption() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["a", "b"],
        max_concurrent_targets=2,
        fleet_phase=FleetPhase.RUNNING,
    )
    fleet_state.usage.model_calls = fleet_spec.fleet_budget.max_model_calls - 1
    fleet_state.usage.tool_calls = fleet_spec.fleet_budget.max_tool_calls - 1

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == [
        "task-a",
        "task-b",
    ]
    assert fleet_state.usage.model_calls == fleet_spec.fleet_budget.max_model_calls - 1
    assert fleet_state.usage.tool_calls == fleet_spec.fleet_budget.max_tool_calls - 1


def test_fleet_exhaustion_does_not_exhaust_targets_and_waits_for_active_work() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["active", "waiting"],
        fleet_phase=FleetPhase.RUNNING,
    )
    fleet_state.usage.cycles = fleet_spec.fleet_budget.max_cycles
    _set_phase(_state(states, "active"), TargetPhase.WORKING)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert fleet_state.phase is FleetPhase.RUNNING
    assert _state(states, "waiting").phase is TargetPhase.INITIALIZED

    _set_phase(_state(states, "active"), TargetPhase.ACCEPTED)
    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert fleet_state.phase is FleetPhase.EXHAUSTED
    assert _state(states, "waiting").phase is TargetPhase.INITIALIZED


def test_fleet_repair_exhaustion_is_preserved_through_dependency_waiting() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["repair", "dependent"],
        dependencies={"dependent": ["repair"]},
        fleet_phase=FleetPhase.RUNNING,
    )
    repair = _state(states, "repair")
    repair.open_finding_refs.append(
        FindingRef(finding_id="finding-1", origin=FindingOrigin.TARGET_REVIEW)
    )
    repair.phase = TargetPhase.REPAIR
    fleet_state.usage.repair_cycles = fleet_spec.fleet_budget.max_repair_cycles

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert repair.phase is TargetPhase.REPAIR
    assert _state(states, "dependent").phase is TargetPhase.INITIALIZED
    assert fleet_state.phase is FleetPhase.EXHAUSTED


@pytest.mark.parametrize(
    ("phases", "expected"),
    [
        ([TargetPhase.FAILED, TargetPhase.EXHAUSTED], FleetPhase.FAILED),
        ([TargetPhase.EXHAUSTED, TargetPhase.STOPPED], FleetPhase.EXHAUSTED),
        ([TargetPhase.STOPPED, TargetPhase.BLOCKED], FleetPhase.STOPPED),
        ([TargetPhase.BLOCKED, TargetPhase.BLOCKED], FleetPhase.BLOCKED),
    ],
)
def test_terminal_no_progress_uses_documented_precedence(
    phases: list[TargetPhase],
    expected: FleetPhase,
) -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["a", "b"],
        fleet_phase=FleetPhase.RUNNING,
    )
    for state, phase in zip(states, phases, strict=True):
        _set_phase(state, phase)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert fleet_state.phase is expected


def test_all_locally_accepted_targets_are_handed_off_without_fleet_acceptance() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture", "testing"],
        fleet_phase=FleetPhase.RUNNING,
    )
    for state in states:
        _set_phase(state, TargetPhase.ACCEPTED)

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert fleet_state.phase is FleetPhase.RUNNING


def test_non_scheduling_fleet_phase_returns_empty_without_target_mutation() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["architecture"],
        fleet_phase=FleetPhase.REPAIRING,
    )
    states[0].open_finding_refs.append(
        FindingRef(finding_id="finding-1", origin=FindingOrigin.FLEET_REVIEW)
    )
    states[0].phase = TargetPhase.REPAIR

    assert schedule_runnable_targets(fleet_spec, fleet_state, specs, states) == []
    assert states[0].phase is TargetPhase.REPAIR


def test_invalid_authoritative_state_is_rejected_before_mutation() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(["a", "b"])
    invalid_state = states[1].model_copy(update={"fleet_run_id": "other-fleet"})

    with pytest.raises(FleetSchedulingError, match="different fleet"):
        schedule_runnable_targets(
            fleet_spec,
            fleet_state,
            specs,
            [states[0], invalid_state],
        )
    assert states[0].phase is TargetPhase.INITIALIZED
    assert fleet_state.phase is FleetPhase.INITIALIZED


def test_dependency_cycle_surviving_initialization_is_rejected() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(["a", "b"])
    cyclic_specs = [
        specs[0].model_copy(update={"depends_on_target_task_ids": ["task-b"]}),
        specs[1].model_copy(update={"depends_on_target_task_ids": ["task-a"]}),
    ]

    with pytest.raises(FleetSchedulingError, match="cycle"):
        schedule_runnable_targets(fleet_spec, fleet_state, cyclic_specs, states)


def test_active_oversubscription_is_rejected() -> None:
    fleet_spec, fleet_state, specs, states = _fleet(
        ["a", "b"],
        max_concurrent_targets=1,
        fleet_phase=FleetPhase.RUNNING,
    )
    for state in states:
        state.phase = TargetPhase.WORKING

    with pytest.raises(FleetSchedulingError, match="exceeds"):
        schedule_runnable_targets(fleet_spec, fleet_state, specs, states)


def _fleet(
    target_ids: Sequence[str],
    *,
    dependencies: dict[str, list[str]] | None = None,
    fleet_budget: ExecutionBudget = _BUDGET,
    target_budget: ExecutionBudget = _BUDGET,
    max_concurrent_targets: int = 1,
    fleet_phase: FleetPhase = FleetPhase.INITIALIZED,
) -> tuple[
    MemoryFleetSpec,
    FleetRunState,
    list[TargetTaskSpec],
    list[TargetTaskState],
]:
    dependencies = dependencies or {}
    fleet_spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id="catalog",
        target_catalog_version="v1",
        target_ids=list(target_ids),
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=fleet_budget,
        default_target_budget=target_budget,
        max_concurrent_targets=max_concurrent_targets,
        runtime_root="/tmp/runtime",
        output_root="/tmp/output",
    )
    specs = [
        TargetTaskSpec(
            target_task_id=f"task-{target_id}",
            fleet_run_id=fleet_spec.fleet_run_id,
            target_id=target_id,
            target_contract_version="v1",
            source=_SOURCE,
            worker_profile_id="worker-v1",
            reviewer_profile_id="reviewer-v1",
            permission_profile_id="permissions-v1",
            budget=target_budget,
            target_workspace=f"/tmp/output/{target_id}",
            depends_on_target_task_ids=[
                f"task-{dependency}" for dependency in dependencies.get(target_id, [])
            ],
        )
        for target_id in target_ids
    ]
    states = [
        TargetTaskState(
            target_task_id=spec.target_task_id,
            fleet_run_id=fleet_spec.fleet_run_id,
        )
        for spec in specs
    ]
    fleet_state = FleetRunState(
        fleet_run_id=fleet_spec.fleet_run_id,
        phase=fleet_phase,
        target_task_ids=[spec.target_task_id for spec in specs],
    )
    return fleet_spec, fleet_state, specs, states


def _state(states: Sequence[TargetTaskState], target_id: str) -> TargetTaskState:
    return next(
        state for state in states if state.target_task_id == f"task-{target_id}"
    )


def _set_phase(state: TargetTaskState, phase: TargetPhase) -> None:
    if phase is TargetPhase.FINALIZING:
        state.pending_finalization_request_ref = "finalization-1"
    elif phase is TargetPhase.ACCEPTED:
        state.last_accepted_result_ref = "accepted-1"
    state.phase = phase
