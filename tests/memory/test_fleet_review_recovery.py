"""Focused Stage 12 fleet-review recovery tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel
from test_fleet_review_acceptance import (
    _client,
    _pass_result,
    _run_review,
    _validated_fleet,
)
from test_fleet_validation import FleetFixture, _recover

import bridger.memory.evaluation.fleet_review as fleet_review_module
from bridger.contracts.memory.core import (
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    TargetPhase,
    TargetTaskState,
)
from bridger.contracts.memory.fleet_review import (
    FleetReviewFindingDraft,
    FleetReviewModelResult,
    FleetReviewVerdict,
)
from bridger.contracts.memory.fleet_validation import FleetValidationFinding
from bridger.contracts.memory.review import ReviewVerdict
from bridger.llm.testing.dummy import DummyLLMClient
from bridger.memory import (
    FleetExecutionCoordinator,
    PersistenceRecoveryError,
    RecoveredFleet,
    accept_fleet,
    resolve_fleet_review_verdict,
    schedule_runnable_targets,
)


def test_recovery_with_no_committed_fleet_review_keeps_reviewing_and_can_run(
    tmp_path: Path,
) -> None:
    fixture = _validated_fleet(tmp_path)
    recovered = _recover(fixture)
    try:
        assert recovered.fleet_state.phase is FleetPhase.REVIEWING
        assert recovered.fleet_state.open_finding_refs == []
        assert all(
            state.phase is TargetPhase.ACCEPTED
            for state in recovered.target_states.values()
        )
        _adopt_recovered(fixture, recovered)
        client = _client(_pass_result())

        verdict = _run_review(fixture, client)

        assert verdict.verdict is ReviewVerdict.PASS
        assert len(client.requests) == 1
        assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    finally:
        recovered.close()


def test_recovery_reuses_committed_pass_and_accepts_without_model_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    original = _run_review(fixture, _client(_pass_result()))
    usage = fixture.fleet_state.usage.model_copy(deep=True)
    recovered = _recover(fixture)
    try:
        assert recovered.fleet_state.phase is FleetPhase.REVIEWING
        assert (
            resolve_fleet_review_verdict(
                recovered.store,
                original.fleet_validation_report_ref,
            )
            == original
        )
        _adopt_recovered(fixture, recovered)
        _forbid_fleet_model_reservation(monkeypatch)

        def forbidden_context_build(*_: object, **__: object) -> None:
            raise AssertionError("recovery rebuilt the fleet-review input")

        monkeypatch.setattr(
            fleet_review_module,
            "_load_accepted_artifacts",
            forbidden_context_build,
        )
        client = DummyLLMClient([])

        reused = _run_review(fixture, client)

        assert reused == original
        assert client.requests == []
        assert fixture.fleet_state.usage == usage
        accepted = accept_fleet(recovered.store, recovered.fleet_state)
        assert recovered.fleet_state.phase is FleetPhase.ACCEPTED
        assert accepted.fleet_review_verdict_ref == original.fleet_review_id
    finally:
        recovered.close()


def test_recovery_clears_stale_pass_projection_and_preserves_other_origins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    original = _run_review(fixture, _client(_pass_result()))
    store = fixture.targets[0].store
    target_ids = [target.target_spec.target_task_id for target in fixture.targets]
    accepted_refs = [
        target.target_state.last_accepted_result_ref for target in fixture.targets
    ]
    unrelated = _unrelated_fleet_validation_finding(fixture, target_ids[:1])
    unrelated_ref = FindingRef(
        finding_id=unrelated.finding_id,
        origin=FindingOrigin.FLEET_VALIDATION,
    )
    stale_fleet_ref = FindingRef(
        finding_id="stale-fleet-review-finding",
        origin=FindingOrigin.FLEET_REVIEW,
    )
    stale_target_ref = FindingRef(
        finding_id="stale-target-review-finding",
        origin=FindingOrigin.FLEET_REVIEW,
    )
    fleet_state = FleetRunState.model_validate_json(
        store.paths.fleet_state.read_bytes()
    ).model_copy(
        deep=True,
        update={"open_finding_refs": [unrelated_ref, stale_fleet_ref]},
    )
    target_states = [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target.target_spec).read_bytes()
        )
        for target in fixture.targets
    ]
    target_states[0] = target_states[0].model_copy(
        deep=True,
        update={"open_finding_refs": [unrelated_ref, stale_target_ref]},
    )
    target_states[1] = target_states[1].model_copy(
        deep=True,
        update={"open_finding_refs": [stale_target_ref]},
    )
    _persist_recovery_projection(
        fixture,
        fleet_state,
        target_states,
        {
            store.paths.fleet_validation_finding(unrelated.finding_id): (
                _model_bytes(unrelated)
            )
        },
    )

    recovered = _recover(fixture)
    try:
        assert recovered.fleet_state.phase is FleetPhase.REVIEWING
        assert recovered.fleet_state.open_finding_refs == [unrelated_ref]
        assert recovered.target_states[target_ids[0]].open_finding_refs == [
            unrelated_ref
        ]
        assert recovered.target_states[target_ids[1]].open_finding_refs == []
        assert [
            recovered.target_states[task_id].last_accepted_result_ref
            for task_id in target_ids
        ] == accepted_refs
        assert (
            resolve_fleet_review_verdict(
                recovered.store,
                original.fleet_validation_report_ref,
            )
            == original
        )
        _adopt_recovered(fixture, recovered)
        _forbid_fleet_model_reservation(monkeypatch)

        def forbidden_context_build(*_: object, **__: object) -> None:
            raise AssertionError("recovery rebuilt the fleet-review input")

        monkeypatch.setattr(
            fleet_review_module,
            "_load_accepted_artifacts",
            forbidden_context_build,
        )
        client = DummyLLMClient([])
        assert _run_review(fixture, client) == original
        assert client.requests == []

        events_before = recovered.store.recover_event_tail()
        assert (
            sum(
                event.event_type == "fleet_review_projection_reconciled"
                for event in events_before
            )
            == 1
        )
        _adopt_recovered(fixture, recovered)
        recovered.close()
        recovered = _recover(fixture)
        events_after = recovered.store.recover_event_tail()
        assert events_after == events_before
        assert (
            resolve_fleet_review_verdict(
                recovered.store,
                original.fleet_validation_report_ref,
            )
            == original
        )
    finally:
        recovered.close()


def test_recovery_routes_reviewing_committed_needs_work_without_model_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    original = _commit_unrouted_needs_work(fixture, monkeypatch)
    before_usage = fixture.fleet_state.usage.model_copy(deep=True)
    _forbid_fleet_model_reservation(monkeypatch)

    recovered = _recover(fixture)
    try:
        affected_id = fixture.targets[0].target_spec.target_task_id
        unaffected_id = fixture.targets[1].target_spec.target_task_id
        assert recovered.fleet_state.phase is FleetPhase.RUNNING
        assert recovered.target_states[affected_id].phase is TargetPhase.REPAIR
        assert recovered.target_states[unaffected_id].phase is TargetPhase.ACCEPTED
        assert recovered.target_states[affected_id].open_finding_refs == (
            original.finding_refs
        )
        assert recovered.fleet_state.open_finding_refs == original.finding_refs
        assert recovered.fleet_state.usage == before_usage
        assert (
            resolve_fleet_review_verdict(
                recovered.store,
                original.fleet_validation_report_ref,
            )
            == original
        )
        events = recovered.store.recover_event_tail()
        assert (
            sum(event.event_type == "fleet_review_repair_routed" for event in events)
            == 1
        )
        _adopt_recovered(fixture, recovered)
        assert schedule_runnable_targets(
            fixture.spec,
            recovered.fleet_state,
            [target.target_spec for target in fixture.targets],
            [
                recovered.target_states[target_id]
                for target_id in recovered.fleet_state.target_task_ids
            ],
            persistence=recovered.store,
        ) == [affected_id]
    finally:
        recovered.close()


def test_recovery_rebuilds_partial_needs_work_projection_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    original = _commit_unrouted_needs_work(fixture, monkeypatch)
    store = fixture.targets[0].store
    target_ids = [target.target_spec.target_task_id for target in fixture.targets]
    unrelated = _unrelated_fleet_validation_finding(fixture, target_ids[:1])
    unrelated_ref = FindingRef(
        finding_id=unrelated.finding_id,
        origin=FindingOrigin.FLEET_VALIDATION,
    )
    stale_ref = FindingRef(
        finding_id="stale-needs-work-projection",
        origin=FindingOrigin.FLEET_REVIEW,
    )
    fleet_state = FleetRunState.model_validate_json(
        store.paths.fleet_state.read_bytes()
    ).model_copy(
        deep=True,
        update={"open_finding_refs": [unrelated_ref, stale_ref]},
    )
    target_states = [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target.target_spec).read_bytes()
        )
        for target in fixture.targets
    ]
    target_states[0] = target_states[0].model_copy(
        deep=True,
        update={
            "phase": TargetPhase.REPAIR,
            "open_finding_refs": [unrelated_ref, stale_ref],
        },
    )
    target_states[1] = target_states[1].model_copy(
        deep=True,
        update={"open_finding_refs": [stale_ref]},
    )
    _persist_recovery_projection(
        fixture,
        fleet_state,
        target_states,
        {
            store.paths.fleet_validation_finding(unrelated.finding_id): (
                _model_bytes(unrelated)
            )
        },
    )

    recovered = _recover(fixture)
    try:
        affected = recovered.target_states[target_ids[0]]
        unaffected = recovered.target_states[target_ids[1]]
        assert recovered.fleet_state.phase is FleetPhase.RUNNING
        assert affected.phase is TargetPhase.REPAIR
        assert unaffected.phase is TargetPhase.ACCEPTED
        assert [
            reference
            for reference in recovered.fleet_state.open_finding_refs
            if reference.origin is FindingOrigin.FLEET_REVIEW
        ] == original.finding_refs
        assert [
            reference
            for reference in affected.open_finding_refs
            if reference.origin is FindingOrigin.FLEET_REVIEW
        ] == original.finding_refs
        assert unrelated_ref in recovered.fleet_state.open_finding_refs
        assert unrelated_ref in affected.open_finding_refs
        assert not any(
            reference.finding_id == stale_ref.finding_id
            for state in [recovered.fleet_state, affected, unaffected]
            for reference in state.open_finding_refs
        )
        events_before = recovered.store.recover_event_tail()
        _adopt_recovered(fixture, recovered)
        recovered.close()
        recovered = _recover(fixture)
        assert recovered.store.recover_event_tail() == events_before
        assert (
            sum(
                event.event_type == "fleet_review_repair_routed"
                for event in events_before
            )
            == 1
        )
        assert recovered.target_states[target_ids[0]].phase is TargetPhase.REPAIR
        assert recovered.target_states[target_ids[1]].phase is TargetPhase.ACCEPTED
    finally:
        recovered.close()


@pytest.mark.parametrize("corrupt", ["verdict", "finding"])
def test_recovery_rejects_corrupt_committed_fleet_review_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: str,
) -> None:
    fixture = _validated_fleet(tmp_path)
    verdict = _commit_unrouted_needs_work(fixture, monkeypatch)
    store = fixture.targets[0].store
    path = (
        store.paths.fleet_review_verdict(verdict.fleet_review_id)
        if corrupt == "verdict"
        else store.paths.fleet_review_finding(verdict.finding_refs[0].finding_id)
    )
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(PersistenceRecoveryError):
        _recover(fixture)


def _commit_unrouted_needs_work(
    fixture: FleetFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> FleetReviewVerdict:
    affected = fixture.targets[0]
    result = FleetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="The accepted fleet needs a deterministic repair.",
        findings=[
            FleetReviewFindingDraft(
                criterion_id="cross-target-duplication",
                affected_target_task_ids=[affected.target_spec.target_task_id],
                affected_artifact_paths=["architecture/runtime.md"],
                message="The detailed state is duplicated.",
                required_outcome="Keep one canonical detail source.",
            )
        ],
    )

    def interrupt_routing(*_: object, **__: object) -> None:
        raise OSError("simulated crash before Stage 12 routing")

    monkeypatch.setattr(
        fleet_review_module,
        "_route_failed_review",
        interrupt_routing,
    )
    with pytest.raises(OSError, match="simulated crash"):
        _run_review(fixture, _client(result))
    monkeypatch.undo()

    store = affected.store
    verdict_root = store.paths.run_root / "fleet-review-verdicts"
    verdict = FleetReviewVerdict.model_validate_json(
        next(verdict_root.glob("*.json")).read_bytes()
    )
    fleet_state = FleetRunState.model_validate_json(
        store.paths.fleet_state.read_bytes()
    ).model_copy(update={"phase": FleetPhase.REVIEWING})
    target_states = [
        TargetTaskState.model_validate_json(
            store.paths.target_state(target.target_spec).read_bytes()
        )
        for target in fixture.targets
    ]
    _persist_recovery_projection(fixture, fleet_state, target_states)
    return verdict


def _persist_recovery_projection(
    fixture: FleetFixture,
    fleet_state: FleetRunState,
    target_states: list[TargetTaskState],
    extra_writes: dict[Path, bytes] | None = None,
) -> None:
    store = fixture.targets[0].store
    before = FleetRunState.model_validate_json(store.paths.fleet_state.read_bytes())
    writes = {
        store.paths.fleet_state: _model_bytes(fleet_state),
        **(extra_writes or {}),
    }
    for target, state in zip(fixture.targets, target_states, strict=True):
        writes[store.paths.target_state(target.target_spec)] = _model_bytes(state)
    store.commit_operation(
        operation_id=f"test-stage12-recovery-{uuid4().hex}",
        writes=writes,
        event_type="phase_transition",
        payload={
            "from_phase": before.phase.value,
            "to_phase": fleet_state.phase.value,
        },
    )
    fixture.fleet_state = fleet_state
    for target, state in zip(fixture.targets, target_states, strict=True):
        target.target_state = state


def _unrelated_fleet_validation_finding(
    fixture: FleetFixture,
    affected_target_task_ids: list[str],
) -> FleetValidationFinding:
    return FleetValidationFinding(
        finding_id=f"unrelated-validation-{uuid4().hex}",
        fleet_validation_report_id="older-validation-report",
        fleet_run_id=fixture.spec.fleet_run_id,
        rule_id="legacy-rule",
        affected_target_task_ids=affected_target_task_ids,
        subject_kind="legacy-projection",
        message="A separate finding origin must remain untouched.",
    )


def _model_bytes(model: BaseModel) -> bytes:
    return model.model_dump_json().encode("utf-8") + b"\n"


def _adopt_recovered(fixture: FleetFixture, recovered: RecoveredFleet) -> None:
    # The recovered fleet owns a new locked store and freshly loaded state models.
    fixture.fleet_state = recovered.fleet_state
    for target in fixture.targets:
        target.store = recovered.store
        target.target_state = recovered.target_states[target.target_spec.target_task_id]


def _forbid_fleet_model_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden_reservation(*_: object, **__: object) -> None:
        raise AssertionError("recovery repeated Stage 12 model work")

    monkeypatch.setattr(
        FleetExecutionCoordinator,
        "reserve_fleet_model_call",
        forbidden_reservation,
    )
