"""Focused Stage 10 target-acceptance and recovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from test_persistence import RuntimeFixture, _enter_working, _recover, _runtime
from test_review import _client, _pass_result, _ready_for_review, _run_review
from test_validation import (
    FakeNavigator,
    _add_file_evidence,
    _passing_fixture,
    _resolve_completion,
)

from bridger.artifacts.writer import write_artifact
from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import (
    CompletionStatus,
    FindingOrigin,
    FindingRef,
    TargetPhase,
    TargetTaskState,
)
from bridger.contracts.memory.fleet_validation import FleetValidationFinding
from bridger.contracts.memory.persistence import TargetFinalizationRequest
from bridger.contracts.memory.review import (
    ReviewFindingDraft,
    ReviewVerdict,
    TargetReviewModelResult,
)
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.contracts.memory.worker_cycle import EvidenceReference
from bridger.memory import (
    PersistenceRecoveryError,
    TargetAcceptanceError,
    TargetWorkspace,
    accept_target,
    handle_finalization_request,
    resolve_accepted_target_result,
    validate_checkpoint,
    validate_target_candidate,
)


def test_accepts_exact_passed_candidate_without_charging_usage(
    tmp_path: Path,
) -> None:
    fixture, request = _review_pass_fixture(tmp_path)
    checkpoint = validate_checkpoint(
        fixture.store,
        fixture.target_spec,
        request.candidate_checkpoint_ref,
    )
    target_usage = fixture.target_state.usage.model_copy(deep=True)
    fleet_usage = fixture.fleet_state.usage.model_copy(deep=True)

    result = accept_target(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
    )

    assert isinstance(result, AcceptedTargetResult)
    assert result.target_task_id == fixture.target_spec.target_task_id
    assert result.fleet_run_id == fixture.spec.fleet_run_id
    assert result.target_id == fixture.target_spec.target_id
    assert result.target_contract_version == fixture.target_spec.target_contract_version
    assert result.source == fixture.target_spec.source
    assert result.artifact_refs == checkpoint.task_state.artifact_refs
    assert result.completion_items == checkpoint.completion_state.items
    assert result.evidence_refs == checkpoint.task_state.evidence_refs
    assert result.finalization_request_ref == request.finalization_request_id
    assert fixture.target_state.phase is TargetPhase.ACCEPTED
    assert fixture.target_state.last_accepted_result_ref == (
        result.accepted_target_result_id
    )
    assert fixture.target_state.pending_finalization_request_ref is None
    assert fixture.target_state.usage == target_usage
    assert fixture.fleet_state.usage == fleet_usage
    assert (
        resolve_accepted_target_result(
            fixture.store,
            fixture.target_spec,
            result.accepted_target_result_id,
        )
        == result
    )
    with pytest.raises(ValidationError):
        result.target_id = "other"


def test_rejects_wrong_phase_or_missing_successful_review(tmp_path: Path) -> None:
    fixture, _ = _ready_for_review(tmp_path)

    with pytest.raises(TargetAcceptanceError, match="coherent target acceptance"):
        accept_target(fixture.store, fixture.target_spec, fixture.target_state)

    fixture.target_state.phase = TargetPhase.WORKING
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.REVIEWING.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
    with pytest.raises(TargetAcceptanceError, match="REVIEWING"):
        accept_target(fixture.store, fixture.target_spec, fixture.target_state)


def test_rejects_non_pass_validation_and_review_results(tmp_path: Path) -> None:
    validation_fixture = _runtime(tmp_path / "validation")
    _enter_working(validation_fixture)
    handle_finalization_request(
        validation_fixture.store,
        validation_fixture.target_spec,
        validation_fixture.target_state,
        validation_fixture.completion_state,
        {},
        {},
    )
    report = validate_target_candidate(
        validation_fixture.store,
        validation_fixture.target_spec,
        validation_fixture.target_state,
        validation_fixture.definition,
        FakeNavigator(validation_fixture),  # type: ignore[arg-type]
    )
    assert report.verdict is ValidationVerdict.FAIL
    with pytest.raises(TargetAcceptanceError, match="REVIEWING"):
        accept_target(
            validation_fixture.store,
            validation_fixture.target_spec,
            validation_fixture.target_state,
        )

    review_fixture, _ = _ready_for_review(tmp_path / "review")
    review_result = TargetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="The candidate still needs material work.",
        findings=[
            ReviewFindingDraft(
                criterion_id="coverage",
                message="Required coverage is missing.",
                required_outcome="Cover the required target concern.",
            )
        ],
    )
    verdict = _run_review(review_fixture, _client(review_result))
    assert verdict.verdict is ReviewVerdict.NEEDS_WORK
    with pytest.raises(TargetAcceptanceError, match="REVIEWING"):
        accept_target(
            review_fixture.store,
            review_fixture.target_spec,
            review_fixture.target_state,
        )


def test_rejects_candidate_drift_after_local_pass(tmp_path: Path) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)
    Path(fixture.target_spec.target_workspace, "architecture.md").write_text(
        "# Drifted after review\n",
        encoding="utf-8",
    )

    with pytest.raises(TargetAcceptanceError, match="coherent target acceptance"):
        accept_target(fixture.store, fixture.target_spec, fixture.target_state)

    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert fixture.target_state.last_accepted_result_ref is None


def test_duplicate_acceptance_reuses_one_result_and_event(tmp_path: Path) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)

    first = accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    second = accept_target(fixture.store, fixture.target_spec, fixture.target_state)

    assert second == first
    result_root = (
        fixture.store.paths.target_root(fixture.target_spec) / "accepted-target-results"
    )
    assert len(list(result_root.glob("*.json"))) == 1
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "target_accepted" for event in events) == 1


def test_committed_acceptance_recovers_forward_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)
    original_apply = fixture.store._apply_intent

    def interrupt_acceptance(transaction_root: Path, intent: object) -> None:
        event = getattr(intent, "event")
        if getattr(event, "event_type") == "target_accepted":
            raise OSError("simulated acceptance crash")
        original_apply(transaction_root, intent)  # type: ignore[arg-type]

    monkeypatch.setattr(fixture.store, "_apply_intent", interrupt_acceptance)
    with pytest.raises(TargetAcceptanceError, match="coherent target acceptance"):
        accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    assert fixture.target_state.phase is TargetPhase.REVIEWING

    monkeypatch.setattr(fixture.store, "_apply_intent", original_apply)
    fixture.store.recover_transactions()
    fixture.store.recover_transactions()
    result = accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    persisted = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )

    assert persisted.phase is TargetPhase.ACCEPTED
    assert persisted.last_accepted_result_ref == result.accepted_target_result_id
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "target_accepted" for event in events) == 1


def test_reopening_preserves_history_and_reacceptance_creates_new_result(
    tmp_path: Path,
) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)
    first = accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    first_path = fixture.store.paths.accepted_target_result(
        fixture.target_spec,
        first.accepted_target_result_id,
    )
    first_bytes = first_path.read_bytes()

    future_finding = FleetValidationFinding(
        finding_id="future-fleet-finding",
        fleet_validation_report_id="future-fleet-report",
        fleet_run_id=fixture.spec.fleet_run_id,
        rule_id="link.missing_destination",
        affected_target_task_ids=[fixture.target_spec.target_task_id],
        subject_kind="link",
        subject_ref="architecture/architecture.md -> missing.md",
        message="Repair the broken generated-memory link.",
    )
    write_artifact(
        fixture.store.paths.fleet_validation_finding(future_finding.finding_id),
        future_finding,
    )

    fixture.target_state.open_finding_refs = [
        FindingRef(
            finding_id="future-fleet-finding",
            origin=FindingOrigin.FLEET_VALIDATION,
        )
    ]
    fixture.fleet_state.open_finding_refs = list(fixture.target_state.open_finding_refs)
    write_artifact(fixture.store.paths.fleet_state, fixture.fleet_state)
    fixture.target_state.phase = TargetPhase.REPAIR
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.ACCEPTED.value,
            "to_phase": TargetPhase.REPAIR.value,
        },
    )
    assert fixture.target_state.last_accepted_result_ref == (
        first.accepted_target_result_id
    )

    recovered = _recover(fixture)
    try:
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.phase is TargetPhase.REPAIR
        assert state.last_accepted_result_ref == first.accepted_target_result_id
        assert (
            resolve_accepted_target_result(
                recovered.store,
                fixture.target_spec,
                first.accepted_target_result_id,
            )
            == first
        )
    finally:
        recovered.close()

    fixture.store = recovered.store
    fixture.target_state = state.model_copy(
        deep=True,
        update={
            "open_finding_refs": [],
            "phase": TargetPhase.WORKING,
        },
    )
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.REPAIR.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact(
        "architecture.md",
        "# Repaired candidate\n",
        expected_revision=1,
    )
    evidence_id = fixture.target_state.evidence_refs[0]
    evidence = EvidenceReference.model_validate_json(
        fixture.store.paths.evidence(
            fixture.target_spec,
            evidence_id,
        ).read_bytes()
    )
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {evidence_id: evidence},
        {},
    )
    report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(
            fixture,
            existing_paths={"src/app.py"},
        ),  # type: ignore[arg-type]
    )
    verdict = _run_review(fixture, _client(_pass_result()))
    second = accept_target(fixture.store, fixture.target_spec, fixture.target_state)

    assert report.verdict is ValidationVerdict.PASS
    assert verdict.verdict is ReviewVerdict.PASS
    assert second.accepted_target_result_id != first.accepted_target_result_id
    assert second.finalization_request_ref == request.finalization_request_id
    assert fixture.target_state.last_accepted_result_ref == (
        second.accepted_target_result_id
    )
    assert first_path.read_bytes() == first_bytes
    assert (
        resolve_accepted_target_result(
            fixture.store,
            fixture.target_spec,
            first.accepted_target_result_id,
        )
        == first
    )


def test_recovery_rejects_accepted_state_with_missing_result(tmp_path: Path) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)
    result = accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    fixture.store.paths.accepted_target_result(
        fixture.target_spec,
        result.accepted_target_result_id,
    ).unlink()

    with pytest.raises(PersistenceRecoveryError, match="accepted target result"):
        _recover(fixture)


def test_recovery_loads_valid_accepted_target_without_rerunning_work(
    tmp_path: Path,
) -> None:
    fixture, _ = _review_pass_fixture(tmp_path)
    expected = accept_target(fixture.store, fixture.target_spec, fixture.target_state)
    usage = fixture.target_state.usage.model_copy(deep=True)

    recovered = _recover(fixture)
    try:
        state = recovered.target_states[fixture.target_spec.target_task_id]
        assert state.phase is TargetPhase.ACCEPTED
        assert state.last_accepted_result_ref == expected.accepted_target_result_id
        assert state.usage == usage
        assert recovered.active_target_task_ids == ()
        assert (
            resolve_accepted_target_result(
                recovered.store,
                fixture.target_spec,
                expected.accepted_target_result_id,
            )
            == expected
        )
    finally:
        recovered.close()


def _review_pass_fixture(
    tmp_path: Path,
) -> tuple[RuntimeFixture, TargetFinalizationRequest]:
    fixture = _passing_fixture(tmp_path)
    evidence = _add_file_evidence(fixture, "src/app.py")
    _resolve_completion(
        fixture,
        CompletionStatus.COVERED,
        evidence_refs=[evidence.evidence_id],
    )
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {evidence.evidence_id: evidence},
        {},
    )
    report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(
            fixture,
            existing_paths={"src/app.py"},
        ),  # type: ignore[arg-type]
    )
    assert report.verdict is ValidationVerdict.PASS
    verdict = _run_review(fixture, _client(_pass_result()))
    assert verdict.verdict is ReviewVerdict.PASS
    return fixture, request
