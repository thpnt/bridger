"""Transient projection and Rich rendering tests for init progress."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from bridger.cli_progress import RichInitProgressPresenter, TargetProgressView
from bridger.contracts.memory.core import (
    CompletionItemState,
    CompletionStatus,
    ExecutionBudget,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    SourceBinding,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.persistence import TaskEvent
from bridger.init_pipeline import InitMode, ReasoningEffort

_SOURCE = SourceBinding(
    repository_id="repository-1",
    repository_revision="a" * 40,
    graph_snapshot_id="snapshot-1",
)
_BUDGET = ExecutionBudget(
    max_cycles=10,
    max_model_calls=10,
    max_tool_calls=10,
    max_repair_cycles=10,
    max_input_tokens=10_000,
    max_output_tokens=10_000,
)


def test_initial_snapshot_creates_one_row_per_activated_target() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(target_ids=["architecture", "operations"])
    _initialize(presenter, snapshot)

    assert presenter.fleet is not None
    assert [target.target_id for target in presenter.fleet.targets.values()] == [
        "architecture",
        "operations",
    ]
    presenter.close()


@pytest.mark.parametrize(
    "status",
    [
        CompletionStatus.COVERED,
        CompletionStatus.NOT_APPLICABLE,
        CompletionStatus.UNKNOWN,
    ],
)
def test_terminal_completion_statuses_count_as_resolved(
    status: CompletionStatus,
) -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(statuses=[status])
    _initialize(presenter, snapshot)

    target = _target(presenter)

    assert target.resolved == 1
    assert target.total == 1
    presenter.close()


def test_uninvestigated_does_not_count_as_resolved() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(statuses=[CompletionStatus.UNINVESTIGATED])
    _initialize(presenter, snapshot)

    assert _target(presenter).resolved == 0
    presenter.close()


def test_completion_projection_replaces_status_by_obligation_id() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(statuses=[CompletionStatus.UNINVESTIGATED])
    _initialize(presenter, snapshot)

    covered = _event(
        1,
        "completion_updated",
        {"obligation_id": "obligation-1", "status": "covered"},
    )
    presenter.runtime_event(covered)
    presenter.runtime_event(covered)
    assert _target(presenter).resolved == 1

    presenter.runtime_event(
        _event(
            2,
            "completion_updated",
            {"obligation_id": "obligation-1", "status": "unknown"},
        )
    )
    assert _target(presenter).resolved == 1
    presenter.close()


def test_full_resolution_does_not_imply_target_acceptance() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(
        statuses=[CompletionStatus.COVERED] * 11,
        target_phase=TargetPhase.REVIEWING,
    )
    _initialize(presenter, snapshot)

    target = _target(presenter)

    assert target.resolved == target.total == 11
    assert target.percentage == 100
    assert target.accepted is False

    presenter.runtime_event(
        _event(
            1,
            "target_accepted",
            {"from_phase": "reviewing", "to_phase": "accepted"},
        )
    )
    assert target.accepted is True
    presenter.close()


def test_zero_obligation_target_is_resolved_but_not_accepted() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(statuses=[])
    _initialize(presenter, snapshot)

    target = _target(presenter)

    assert target.resolved == target.total == 0
    assert target.percentage == 100
    assert target.accepted is False
    presenter.close()


def test_fleet_phase_events_update_the_projection() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot()
    _initialize(presenter, snapshot)

    presenter.runtime_event(
        _event(
            1,
            "fleet_validation_started",
            {"from_phase": "running", "to_phase": "validating"},
            target_task_id=None,
        )
    )

    assert presenter.fleet is not None
    assert presenter.fleet.phase is FleetPhase.VALIDATING
    presenter.close()


@pytest.mark.parametrize(
    "event_type",
    ["fleet_repair_routed", "fleet_review_repair_routed"],
)
def test_fleet_repair_events_move_exactly_affected_targets(
    event_type: str,
) -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot(
        target_ids=["architecture", "operations"],
        target_phase=TargetPhase.ACCEPTED,
        fleet_phase=FleetPhase.REPAIRING,
    )
    _initialize(presenter, snapshot)
    architecture_task = snapshot[1][0].target_task_id
    operations_task = snapshot[1][1].target_task_id

    presenter.runtime_event(
        _event(
            1,
            event_type,
            {
                "affected_target_task_ids": [architecture_task],
                "from_phase": "repairing",
                "to_phase": "running",
            },
            target_task_id=None,
        )
    )

    assert presenter.fleet is not None
    assert presenter.fleet.targets[architecture_task].phase is TargetPhase.REPAIR
    assert presenter.fleet.targets[operations_task].phase is TargetPhase.ACCEPTED
    assert presenter.fleet.phase is FleetPhase.RUNNING
    presenter.close()


def test_unknown_and_malformed_events_are_ignored() -> None:
    presenter, _ = _presenter()
    snapshot = _snapshot()
    _initialize(presenter, snapshot)

    presenter.runtime_event(_event(1, "future_event", {"to_phase": 7}))
    presenter.runtime_event(
        _event(2, "completion_updated", {"obligation_id": "obligation-1"})
    )
    presenter.runtime_event(
        _event(
            3,
            "fleet_repair_routed",
            {"affected_target_task_ids": "not-a-list", "to_phase": "invalid"},
            target_task_id=None,
        )
    )

    assert _target(presenter).resolved == 0
    presenter.close()


def test_interactive_rendering_keeps_progress_and_lifecycle_distinct() -> None:
    presenter, buffer = _presenter(interactive=True)
    snapshot = _snapshot(
        statuses=[CompletionStatus.COVERED] * 7 + [CompletionStatus.UNINVESTIGATED] * 4,
        target_phase=TargetPhase.WORKING,
    )
    _initialize(presenter, snapshot)
    presenter.close()

    output = buffer.getvalue()
    assert "architecture" in output
    assert "7/11" in output
    assert "64%" in output
    assert "working" in output


def test_interactive_rendering_shows_reviewing_then_accepted() -> None:
    snapshot = _snapshot(
        statuses=[CompletionStatus.COVERED] * 11,
        target_phase=TargetPhase.REVIEWING,
    )
    reviewing_presenter, reviewing_buffer = _presenter(interactive=True)
    _initialize(reviewing_presenter, snapshot)
    reviewing_presenter.close()

    presenter, buffer = _presenter(interactive=True)
    _initialize(presenter, snapshot)
    presenter.runtime_event(
        _event(
            1,
            "target_accepted",
            {"from_phase": "reviewing", "to_phase": "accepted"},
        )
    )
    presenter.close()

    output = buffer.getvalue()
    assert "11/11" in output
    assert "reviewing" in reviewing_buffer.getvalue()
    assert "accepted" in output


def test_noninteractive_rendering_is_append_only_without_ansi() -> None:
    presenter, buffer = _presenter()
    snapshot = _snapshot(
        statuses=[CompletionStatus.UNINVESTIGATED] * 11,
        target_phase=TargetPhase.WORKING,
    )
    _initialize(presenter, snapshot)
    presenter.runtime_event(
        _event(
            1,
            "completion_updated",
            {"obligation_id": "obligation-1", "status": "covered"},
        )
    )
    presenter.runtime_event(
        _event(
            2,
            "phase_transition",
            {"from_phase": "working", "to_phase": "reviewing"},
        )
    )
    presenter.close()

    output = buffer.getvalue()
    assert "[fleet] 1 targets initialized" in output
    assert "[target] architecture 1/11 9% working" in output
    assert "[target] architecture 1/11 9% reviewing" in output
    assert "\x1b" not in output


def test_fleet_failure_renders_a_terminal_failure_marker() -> None:
    presenter, buffer = _presenter()
    snapshot = _snapshot(target_phase=TargetPhase.WORKING)
    _initialize(presenter, snapshot)

    presenter.failed(RuntimeError("provider unavailable"))
    presenter.close()

    output = buffer.getvalue()
    assert "[fleet] execution failed" in output
    assert "Repository Brain build failed: provider unavailable" in output


def test_interactive_rendering_preserves_target_ids_at_80_columns() -> None:
    presenter, buffer = _presenter(interactive=True, width=80)
    snapshot = _snapshot(target_ids=["interfaces-and-integrations"])
    _initialize(presenter, snapshot)
    presenter.close()

    assert "interfaces-and-integrations" in buffer.getvalue()


def _presenter(
    *, interactive: bool = False, width: int = 120
) -> tuple[RichInitProgressPresenter, StringIO]:
    buffer = StringIO()
    presenter = RichInitProgressPresenter(
        console=Console(
            file=buffer,
            force_terminal=interactive,
            color_system="standard" if interactive else None,
            width=width,
        ),
        mode=InitMode.FULL,
        reasoning=ReasoningEffort.XHIGH,
    )
    presenter.start()
    return presenter, buffer


def _snapshot(
    *,
    statuses: list[CompletionStatus] | None = None,
    target_ids: list[str] | None = None,
    target_phase: TargetPhase = TargetPhase.INITIALIZED,
    fleet_phase: FleetPhase = FleetPhase.INITIALIZED,
) -> tuple[
    MemoryFleetSpec,
    list[TargetTaskSpec],
    list[TargetTaskState],
    list[TargetCompletionState],
    FleetRunState,
]:
    ids = target_ids or ["architecture"]
    obligation_statuses = (
        statuses if statuses is not None else [CompletionStatus.UNINVESTIGATED]
    )
    spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id="catalog-1",
        target_catalog_version="1",
        target_ids=ids,
        runtime_profile_id="runtime-1",
        default_worker_profile_id="worker-1",
        default_reviewer_profile_id="reviewer-1",
        default_permission_profile_id="permissions-1",
        fleet_budget=_BUDGET,
        default_target_budget=_BUDGET,
        runtime_root="/tmp/runtime",
        output_root="/tmp/output",
    )
    target_specs: list[TargetTaskSpec] = []
    target_states: list[TargetTaskState] = []
    completion_states: list[TargetCompletionState] = []
    for target_id in ids:
        task_id = f"task-{target_id}"
        target_specs.append(
            TargetTaskSpec(
                target_task_id=task_id,
                fleet_run_id=spec.fleet_run_id,
                target_id=target_id,
                target_contract_version="1",
                source=_SOURCE,
                worker_profile_id="worker-1",
                reviewer_profile_id="reviewer-1",
                permission_profile_id="permissions-1",
                budget=_BUDGET,
                target_workspace=str(Path("/tmp/output") / target_id),
            )
        )
        target_states.append(
            TargetTaskState(
                target_task_id=task_id,
                fleet_run_id=spec.fleet_run_id,
                phase=target_phase,
                last_accepted_result_ref=(
                    f"accepted-{target_id}"
                    if target_phase is TargetPhase.ACCEPTED
                    else None
                ),
            )
        )
        completion_states.append(
            TargetCompletionState(
                target_task_id=task_id,
                items=[
                    CompletionItemState(
                        obligation_id=f"obligation-{index}",
                        status=status,
                        resolution_note=(
                            f"Resolved obligation {index}."
                            if status is not CompletionStatus.UNINVESTIGATED
                            else None
                        ),
                    )
                    for index, status in enumerate(obligation_statuses, start=1)
                ],
            )
        )
    fleet_state = FleetRunState(
        fleet_run_id=spec.fleet_run_id,
        phase=fleet_phase,
        target_task_ids=[item.target_task_id for item in target_specs],
        accepted_result_ref=(
            "accepted-fleet" if fleet_phase is FleetPhase.ACCEPTED else None
        ),
    )
    return spec, target_specs, target_states, completion_states, fleet_state


def _initialize(
    presenter: RichInitProgressPresenter,
    snapshot: tuple[
        MemoryFleetSpec,
        list[TargetTaskSpec],
        list[TargetTaskState],
        list[TargetCompletionState],
        FleetRunState,
    ],
) -> None:
    presenter.fleet_initialized(*snapshot)


def _target(presenter: RichInitProgressPresenter) -> TargetProgressView:
    assert presenter.fleet is not None
    return next(iter(presenter.fleet.targets.values()))


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    target_task_id: str | None = "task-architecture",
) -> TaskEvent:
    return TaskEvent(
        event_id=f"event-{sequence}",
        fleet_run_id="fleet-1",
        target_task_id=target_task_id,
        sequence=sequence,
        event_type=event_type,
        timestamp="2026-08-23T00:00:00+00:00",
        payload=payload,
    )
