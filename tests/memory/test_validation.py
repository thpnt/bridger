"""Focused Stage 7 hard-validation lifecycle and persistence tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_persistence import (
    RuntimeFixture,
    _enter_working,
    _recover,
    _runtime,
)

import bridger.memory.evaluation.validation as validation_module
from bridger.contracts.memory.core import (
    CompletionStatus,
    FindingOrigin,
    FindingRef,
    TargetPhase,
    TargetTaskState,
)
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    EvidenceReference,
    FileEvidenceLocator,
    OpenQuestion,
)
from bridger.memory import (
    PersistenceRecoveryError,
    TargetWorkspace,
    handle_finalization_request,
    resolve_validation_report,
    validate_target_candidate,
)


class FakeNavigator:
    """Minimal deterministic source authority used by Stage 7 tests."""

    def __init__(
        self,
        fixture: RuntimeFixture,
        *,
        existing_paths: set[str] | None = None,
    ) -> None:
        source = fixture.target_spec.source
        self.source_identity = (
            source.repository_id,
            source.repository_revision,
            source.graph_snapshot_id,
            source.enrichment_overlay_id,
        )
        self.existing_paths = existing_paths or set()

    def get_file_overview(self, path: str) -> object:
        if path not in self.existing_paths:
            raise KeyError(path)
        return SimpleNamespace(
            file=SimpleNamespace(
                disposition=SimpleNamespace(read_mode="full"),
            )
        )

    def read_file_ranges(self, *_: object, **__: object) -> list[object]:
        raise KeyError("unknown range")

    def read_symbol_excerpt(self, *_: object, **__: object) -> object:
        raise KeyError("unknown symbol")

    def get_graph_entity(self, *_: object, **__: object) -> object:
        raise KeyError("unknown graph entity")


def test_validation_passes_exact_checkpoint_and_preserves_review_handoff(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    usage_before = fixture.target_state.usage.model_copy(deep=True)
    fleet_usage_before = fixture.fleet_state.usage.model_copy(deep=True)
    evidence = _add_file_evidence(fixture, "src/app.py")
    _resolve_completion(
        fixture,
        CompletionStatus.COVERED,
        evidence_refs=[evidence.evidence_id],
    )
    workspace = TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    )
    workspace.write_target_artifact("architecture.md", "# Exact candidate\n")
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {evidence.evidence_id: evidence},
        {},
    )
    Path(fixture.target_spec.target_workspace, "architecture.md").write_text(
        "ambient mutation after submission",
        encoding="utf-8",
    )

    report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture, existing_paths={"src/app.py"}),  # type: ignore[arg-type]
    )

    assert report.verdict is ValidationVerdict.PASS
    assert report.finalization_request_id == request.finalization_request_id
    assert report.candidate_checkpoint_ref == request.candidate_checkpoint_ref
    assert report.finding_refs == []
    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert (
        fixture.target_state.pending_finalization_request_ref
        == request.finalization_request_id
    )
    assert fixture.target_state.open_finding_refs == []
    assert fixture.target_state.usage == usage_before
    assert fixture.fleet_state.usage == fleet_usage_before


def test_validation_failures_persist_findings_and_route_to_repair(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    review_finding = FindingRef(
        finding_id="existing-review-finding",
        origin=FindingOrigin.TARGET_REVIEW,
    )
    fixture.target_state.open_finding_refs = [review_finding]
    evidence = _add_file_evidence(fixture, "missing.py")
    _resolve_completion(
        fixture,
        CompletionStatus.COVERED,
        evidence_refs=[evidence.evidence_id],
    )
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact("architecture.md", "   \n")
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
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )

    assert report.verdict is ValidationVerdict.FAIL
    assert fixture.target_state.phase is TargetPhase.REPAIR
    assert fixture.target_state.pending_finalization_request_ref is None
    assert fixture.target_state.open_finding_refs == [
        review_finding,
        *report.finding_refs,
    ]
    rule_ids = {
        validation_module.ValidationFinding.model_validate_json(
            fixture.store.paths.validation_finding(
                fixture.target_spec,
                reference.finding_id,
            ).read_bytes()
        ).rule_id
        for reference in report.finding_refs
    }
    assert rule_ids == {
        "artifact.non_empty_markdown_missing",
        "completion.covered_without_evidence",
        "evidence.unresolvable",
    }
    assert all(
        reference.origin is FindingOrigin.HARD_VALIDATION
        for reference in report.finding_refs
    )
    assert (
        resolve_validation_report(
            fixture.store,
            fixture.target_spec,
            request.finalization_request_id,
        )
        == report
    )


def test_uninvestigated_and_missing_artifact_are_candidate_failures(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )

    report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )

    rules = _report_rules(fixture, report)
    assert report.verdict is ValidationVerdict.FAIL
    assert rules == {"artifact.missing", "completion.uninvestigated"}
    assert request.candidate_checkpoint_ref == report.candidate_checkpoint_ref


def test_open_questions_are_structurally_valid_and_do_not_block_pass(
    tmp_path: Path,
) -> None:
    fixture = _passing_fixture(tmp_path)
    question = OpenQuestion(
        question_id="question-1",
        target_task_id=fixture.target_spec.target_task_id,
        text="Which deployment path is authoritative?",
    )
    after_state = fixture.target_state.model_copy(deep=True)
    after_state.open_question_refs = [question.question_id]
    fixture.store.commit_progress(
        fixture.target_spec,
        fixture.target_state,
        after_state,
        [question],
        [],
    )
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {question.question_id: question},
    )

    report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )

    assert report.verdict is ValidationVerdict.PASS
    assert report.candidate_checkpoint_ref == request.candidate_checkpoint_ref


def test_corrupt_evaluation_subject_is_not_a_worker_finding(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    fixture.store.paths.finalization_request(
        fixture.target_spec,
        request.finalization_request_id,
    ).write_text("{}", encoding="utf-8")

    with pytest.raises(PersistenceRecoveryError, match="subject integrity"):
        validate_target_candidate(
            fixture.store,
            fixture.target_spec,
            fixture.target_state,
            fixture.definition,
            FakeNavigator(fixture),  # type: ignore[arg-type]
        )

    assert fixture.target_state.phase is TargetPhase.FINALIZING
    assert fixture.target_state.open_finding_refs == []


def test_duplicate_invocation_reuses_the_committed_report(tmp_path: Path) -> None:
    fixture = _passing_fixture(tmp_path)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    navigator = FakeNavigator(fixture)
    first = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        navigator,  # type: ignore[arg-type]
    )
    second = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        navigator,  # type: ignore[arg-type]
        finalization_request_id=request.finalization_request_id,
    )

    assert second == first
    reports = (
        fixture.store.paths.target_root(fixture.target_spec) / "validation-reports"
    )
    assert len(list(reports.glob("*.json"))) == 1
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "validation_started" for event in events) == 1
    assert sum(event.event_type == "validation_completed" for event in events) == 1


def test_validating_recovery_reruns_the_same_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _passing_fixture(tmp_path)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    original = validation_module._run_candidate_gates

    def interrupt(*_: object) -> list[object]:
        raise OSError("simulated validation interruption")

    monkeypatch.setattr(validation_module, "_run_candidate_gates", interrupt)
    with pytest.raises(PersistenceRecoveryError, match="coherent outcome"):
        validate_target_candidate(
            fixture.store,
            fixture.target_spec,
            fixture.target_state,
            fixture.definition,
            FakeNavigator(fixture),  # type: ignore[arg-type]
        )
    assert fixture.target_state.phase is TargetPhase.VALIDATING
    assert (
        resolve_validation_report(
            fixture.store,
            fixture.target_spec,
            request.finalization_request_id,
        )
        is None
    )

    recovered = _recover(fixture)
    try:
        recovered_state = recovered.target_states[fixture.target_spec.target_task_id]
        assert recovered_state.phase is TargetPhase.VALIDATING
        monkeypatch.setattr(validation_module, "_run_candidate_gates", original)
        report = validate_target_candidate(
            recovered.store,
            fixture.target_spec,
            recovered_state,
            fixture.definition,
            FakeNavigator(fixture),  # type: ignore[arg-type]
        )

        assert report.verdict is ValidationVerdict.PASS
        assert report.candidate_checkpoint_ref == request.candidate_checkpoint_ref
        assert recovered_state.phase is TargetPhase.REVIEWING
    finally:
        recovered.close()


def test_multiple_finalization_rounds_keep_immutable_history(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    request_a = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    report_a = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )
    assert report_a.verdict is ValidationVerdict.FAIL

    fixture.target_state.phase = TargetPhase.SCHEDULED
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.REPAIR.value,
            "to_phase": TargetPhase.SCHEDULED.value,
        },
    )
    fixture.target_state.phase = TargetPhase.WORKING
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.SCHEDULED.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
    _resolve_completion(fixture, CompletionStatus.UNKNOWN)
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact("architecture.md", "# Repaired\n")
    request_b = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    report_b = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )

    assert report_b.verdict is ValidationVerdict.PASS
    assert request_a.finalization_request_id != request_b.finalization_request_id
    assert report_a.validation_report_id != report_b.validation_report_id
    assert (
        resolve_validation_report(
            fixture.store,
            fixture.target_spec,
            request_a.finalization_request_id,
        )
        == report_a
    )
    assert (
        resolve_validation_report(
            fixture.store,
            fixture.target_spec,
            request_b.finalization_request_id,
        )
        == report_b
    )
    assert not any(
        reference.origin is FindingOrigin.HARD_VALIDATION
        for reference in fixture.target_state.open_finding_refs
    )


def test_committed_validation_completion_recovers_forward_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _passing_fixture(tmp_path)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    original_apply = fixture.store._apply_intent

    def interrupt_completion(transaction_root: Path, intent: object) -> None:
        event = getattr(intent, "event")
        if getattr(event, "event_type") == "validation_completed":
            raise OSError("simulated validation completion crash")
        original_apply(transaction_root, intent)  # type: ignore[arg-type]

    monkeypatch.setattr(fixture.store, "_apply_intent", interrupt_completion)
    with pytest.raises(PersistenceRecoveryError, match="coherent outcome"):
        validate_target_candidate(
            fixture.store,
            fixture.target_spec,
            fixture.target_state,
            fixture.definition,
            FakeNavigator(fixture),  # type: ignore[arg-type]
        )
    assert fixture.target_state.phase is TargetPhase.VALIDATING

    monkeypatch.setattr(fixture.store, "_apply_intent", original_apply)
    fixture.store.recover_transactions()
    fixture.store.recover_transactions()
    persisted = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )
    report = resolve_validation_report(
        fixture.store,
        fixture.target_spec,
        request.finalization_request_id,
    )

    assert persisted.phase is TargetPhase.REVIEWING
    assert report is not None
    assert report.verdict is ValidationVerdict.PASS
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "validation_completed" for event in events) == 1


def _passing_fixture(tmp_path: Path) -> RuntimeFixture:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    _resolve_completion(fixture, CompletionStatus.UNKNOWN)
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact("architecture.md", "# Candidate\n")
    return fixture


def _resolve_completion(
    fixture: RuntimeFixture,
    status: CompletionStatus,
    *,
    evidence_refs: list[str] | None = None,
) -> None:
    item = fixture.completion_state.items[0]
    item.resolution_note = "Mechanically resolved for validation."
    item.evidence_refs = evidence_refs or []
    item.status = status
    fixture.store.persist_completion_state(
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        obligation_id=item.obligation_id,
    )


def _add_file_evidence(
    fixture: RuntimeFixture,
    path: str,
) -> EvidenceReference:
    evidence = EvidenceReference(
        evidence_id=f"evidence-{path.replace('/', '-')}",
        target_task_id=fixture.target_spec.target_task_id,
        source=fixture.target_spec.source,
        kind=EvidenceKind.FILE,
        locator=FileEvidenceLocator(path=path),
    )
    fixture.store.commit_evidence(
        fixture.target_spec,
        fixture.target_state,
        evidence,
    )
    return evidence


def _report_rules(
    fixture: RuntimeFixture,
    report: object,
) -> set[str]:
    validated = validation_module.TargetValidationReport.model_validate(report)
    return {
        validation_module.ValidationFinding.model_validate_json(
            fixture.store.paths.validation_finding(
                fixture.target_spec,
                reference.finding_id,
            ).read_bytes()
        ).rule_id
        for reference in validated.finding_refs
    }
