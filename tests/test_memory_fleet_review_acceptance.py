"""Focused Stage 12 fleet reconciliation and Stage 13 acceptance tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from test_memory_fleet_validation import (
    FleetFixture,
    _accept_current_candidate,
    _accepted_fleet,
    _load_target_states,
    _recover,
)
from test_memory_review import _profile

import memory.fleet_review as fleet_review_module
from llm.models import LLMOperation, LLMResponse, LLMUsage
from llm.testing.dummy import DummyLLMClient
from memory import (
    ContextWindowManager,
    FleetAcceptanceError,
    FleetExecutionCoordinator,
    FleetReviewError,
    TargetWorkspace,
    accept_fleet,
    reconcile_fleet,
    resolve_accepted_memory_fleet_result,
    resolve_fleet_review_finding,
    schedule_runnable_targets,
    validate_fleet,
)
from models.fleet_acceptance import AcceptedMemoryFleetResult
from models.fleet_review import (
    FleetReviewFindingDraft,
    FleetReviewModelResult,
)
from models.memory import FindingOrigin, FleetPhase, FleetRunState, TargetPhase
from models.review import ReviewVerdict


def test_full_corpus_pass_charges_only_fleet_and_accepts_idempotently(
    tmp_path: Path,
) -> None:
    fixture = _validated_fleet(tmp_path)
    target_usage = [
        target.target_state.usage.model_copy(deep=True) for target in fixture.targets
    ]
    fleet_usage = fixture.fleet_state.usage.model_copy(deep=True)
    client = _client(_pass_result(), input_tokens=41, output_tokens=9)
    Path(fixture.targets[0].target_spec.target_workspace, "runtime.md").write_text(
        "ambient mutable workspace drift",
        encoding="utf-8",
    )

    verdict = _run_review(fixture, client)

    assert verdict.verdict is ReviewVerdict.PASS
    assert verdict.finding_refs == []
    assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    assert fixture.fleet_state.usage.model_calls == fleet_usage.model_calls + 1
    assert fixture.fleet_state.usage.input_tokens == fleet_usage.input_tokens + 41
    assert fixture.fleet_state.usage.output_tokens == fleet_usage.output_tokens + 9
    assert [target.target_state.usage for target in fixture.targets] == target_usage
    assert client.requests[0].operation is LLMOperation.MEMORY_AGENT_RECONCILIATION
    assert client.requests[0].tools == []
    request_content = client.requests[0].messages[1].content or ""
    assert "architecture/runtime.md" in request_content
    assert "data-and-state/persistence.md" in request_content
    assert "ambient mutable workspace drift" not in request_content
    review_usage = fixture.fleet_state.usage.model_copy(deep=True)
    assert _run_review(fixture, DummyLLMClient([])) == verdict
    assert fixture.fleet_state.usage == review_usage

    accepted_usage = fixture.fleet_state.usage.model_copy(deep=True)
    first = accept_fleet(fixture.targets[0].store, fixture.fleet_state)
    second = accept_fleet(fixture.targets[0].store, fixture.fleet_state)

    assert isinstance(first, AcceptedMemoryFleetResult)
    assert second == first
    assert first.accepted_target_result_refs == (
        verdict_subject_refs(fixture, verdict.fleet_validation_report_ref)
    )
    assert first.fleet_review_verdict_ref == verdict.fleet_review_id
    assert fixture.fleet_state.phase is FleetPhase.ACCEPTED
    assert fixture.fleet_state.accepted_result_ref == (
        first.accepted_memory_fleet_result_id
    )
    assert fixture.fleet_state.usage == accepted_usage
    assert (
        resolve_accepted_memory_fleet_result(
            fixture.targets[0].store,
            first.accepted_memory_fleet_result_id,
        )
        == first
    )
    with pytest.raises(ValidationError):
        first.target_catalog_version = "other"
    events = fixture.targets[0].store.recover_event_tail()
    assert sum(event.event_type == "fleet_review_completed" for event in events) == 1
    assert sum(event.event_type == "fleet_accepted" for event in events) == 1


def test_needs_work_reopens_only_affected_target_and_preserves_projection(
    tmp_path: Path,
) -> None:
    fixture = _validated_fleet(tmp_path)
    affected = fixture.targets[0]
    unaffected = fixture.targets[1]
    result = FleetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="Architecture duplicates the state authority.",
        findings=[
            FleetReviewFindingDraft(
                criterion_id="cross-target-duplication",
                affected_target_task_ids=[affected.target_spec.target_task_id],
                affected_artifact_paths=["architecture/runtime.md"],
                message="Architecture repeats the canonical persistence detail.",
                required_outcome=(
                    "Keep persistence detail in data-and-state and retain only "
                    "bounded runtime context in architecture."
                ),
            )
        ],
    )
    unaffected_result = unaffected.target_state.last_accepted_result_ref

    verdict = _run_review(fixture, _client(result))
    states = _load_target_states(fixture)
    finding = resolve_fleet_review_finding(
        affected.store,
        verdict.finding_refs[0].finding_id,
    )

    assert verdict.verdict is ReviewVerdict.NEEDS_WORK
    assert fixture.fleet_state.phase is FleetPhase.RUNNING
    assert states[0].phase is TargetPhase.REPAIR
    assert states[1].phase is TargetPhase.ACCEPTED
    assert states[1].last_accepted_result_ref == unaffected_result
    assert states[0].open_finding_refs == verdict.finding_refs
    assert fixture.fleet_state.open_finding_refs == verdict.finding_refs
    assert finding.affected_target_task_ids == [affected.target_spec.target_task_id]
    assert finding.affected_artifact_paths == ["architecture/runtime.md"]
    assert all(
        reference.origin is FindingOrigin.FLEET_REVIEW
        for reference in verdict.finding_refs
    )
    with pytest.raises(FleetAcceptanceError, match="REVIEWING"):
        accept_fleet(affected.store, fixture.fleet_state)


def test_reconciliation_rejects_unknown_repair_subject_as_provider_failure(
    tmp_path: Path,
) -> None:
    fixture = _validated_fleet(tmp_path)
    result = FleetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="A repair is needed.",
        findings=[
            FleetReviewFindingDraft(
                criterion_id="semantic-ownership",
                affected_target_task_ids=["unknown-task"],
                message="The output names a target outside the fleet.",
                required_outcome="Use an activated target.",
            )
        ],
    )

    with pytest.raises(FleetReviewError, match="persist fleet review verdict"):
        _run_review(fixture, _client(result))

    assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    assert fixture.fleet_state.open_finding_refs == []
    assert not (
        fixture.targets[0].store.paths.run_root / "fleet-review-verdicts"
    ).exists()


def test_local_reacceptance_keeps_fleet_review_finding_until_fresh_pass(
    tmp_path: Path,
) -> None:
    fixture = _validated_fleet(tmp_path)
    affected = fixture.targets[0]
    needs_work = FleetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="Architecture duplicates state ownership.",
        findings=[
            FleetReviewFindingDraft(
                criterion_id="semantic-ownership",
                affected_target_task_ids=[affected.target_spec.target_task_id],
                message="Architecture owns detailed persistence semantics.",
                required_outcome="Keep only runtime-relevant persistence context.",
            )
        ],
    )
    failed = _run_review(fixture, _client(needs_work))
    states = _load_target_states(fixture)
    for target, state in zip(fixture.targets, states, strict=True):
        target.target_state = state

    assert schedule_runnable_targets(
        fixture.spec,
        fixture.fleet_state,
        [target.target_spec for target in fixture.targets],
        [target.target_state for target in fixture.targets],
        persistence=affected.store,
    ) == [affected.target_spec.target_task_id]
    affected.target_state.phase = TargetPhase.WORKING
    affected.store.persist_target_state(
        affected.target_spec,
        affected.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": TargetPhase.SCHEDULED.value,
            "to_phase": TargetPhase.WORKING.value,
        },
    )
    TargetWorkspace(
        affected.target_spec,
        affected.target_state,
        affected.store,
    ).write_target_artifact(
        "runtime.md",
        "# Runtime\n\nRuntime structure with bounded state context.\n",
        expected_revision=1,
    )
    _accept_current_candidate(affected)

    assert failed.finding_refs[0] in affected.target_state.open_finding_refs
    validate_fleet(affected.store, fixture.fleet_state)
    assert failed.finding_refs[0] in fixture.fleet_state.open_finding_refs
    passed = _run_review(fixture, _client(_pass_result()))
    final_states = _load_target_states(fixture)

    assert passed.verdict is ReviewVerdict.PASS
    assert fixture.fleet_state.open_finding_refs == []
    assert all(
        reference.origin is not FindingOrigin.FLEET_REVIEW
        for state in final_states
        for reference in state.open_finding_refs
    )


def test_recovery_finishes_committed_fleet_review_repair_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    result = FleetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="Architecture must reduce duplicated state detail.",
        findings=[
            FleetReviewFindingDraft(
                criterion_id="cross-target-duplication",
                affected_target_task_ids=[
                    fixture.targets[0].target_spec.target_task_id
                ],
                message="The detailed state explanation is duplicated.",
                required_outcome="Retain one canonical detailed explanation.",
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
    persisted = FleetRunState.model_validate_json(
        fixture.targets[0].store.paths.fleet_state.read_bytes()
    )
    assert persisted.phase is FleetPhase.REPAIRING

    monkeypatch.undo()
    recovered = _recover(fixture)
    try:
        states = [
            recovered.target_states[target.target_spec.target_task_id]
            for target in fixture.targets
        ]
        assert recovered.fleet_state.phase is FleetPhase.RUNNING
        assert states[0].phase is TargetPhase.REPAIR
        assert states[1].phase is TargetPhase.ACCEPTED
        events = recovered.store.recover_event_tail()
        assert (
            sum(event.event_type == "fleet_review_repair_routed" for event in events)
            == 1
        )
    finally:
        recovered.close()


def test_acceptance_rejects_changed_or_corrupt_provenance(tmp_path: Path) -> None:
    fixture = _validated_fleet(tmp_path)
    _run_review(fixture, _client(_pass_result()))
    store = fixture.targets[0].store
    report_root = store.paths.run_root / "fleet-validation-reports"
    report_path = next(report_root.glob("*.json"))
    report_path.write_text("{}", encoding="utf-8")

    with pytest.raises(FleetAcceptanceError, match="coherent fleet acceptance"):
        accept_fleet(store, fixture.fleet_state)

    assert fixture.fleet_state.phase is FleetPhase.REVIEWING
    assert fixture.fleet_state.accepted_result_ref is None


def test_recovery_validates_terminal_accepted_result(tmp_path: Path) -> None:
    fixture = _validated_fleet(tmp_path)
    _run_review(fixture, _client(_pass_result()))
    accepted = accept_fleet(fixture.targets[0].store, fixture.fleet_state)

    recovered = _recover(fixture)
    try:
        assert recovered.fleet_state.phase is FleetPhase.ACCEPTED
        assert recovered.fleet_state.accepted_result_ref == (
            accepted.accepted_memory_fleet_result_id
        )
    finally:
        recovered.close()


def test_acceptance_transaction_recovers_forward_without_duplicate_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _validated_fleet(tmp_path)
    _run_review(fixture, _client(_pass_result()))
    store = fixture.targets[0].store
    original_apply = store._apply_intent

    def interrupt_acceptance(transaction_root: Path, intent: object) -> None:
        event = getattr(intent, "event")
        if getattr(event, "event_type") == "fleet_accepted":
            raise OSError("simulated acceptance crash")
        original_apply(transaction_root, intent)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "_apply_intent", interrupt_acceptance)
    with pytest.raises(FleetAcceptanceError, match="coherent fleet acceptance"):
        accept_fleet(store, fixture.fleet_state)
    assert fixture.fleet_state.phase is FleetPhase.REVIEWING

    monkeypatch.setattr(store, "_apply_intent", original_apply)
    store.recover_transactions()
    result = accept_fleet(store, fixture.fleet_state)

    assert fixture.fleet_state.phase is FleetPhase.ACCEPTED
    result_root = store.paths.run_root / "accepted-memory-fleet-results"
    assert len(list(result_root.glob("*.json"))) == 1
    assert (
        resolve_accepted_memory_fleet_result(
            store,
            result.accepted_memory_fleet_result_id,
        )
        == result
    )
    events = store.recover_event_tail()
    assert sum(event.event_type == "fleet_accepted" for event in events) == 1


def _validated_fleet(tmp_path: Path) -> FleetFixture:
    fixture = _accepted_fleet(
        tmp_path,
        {
            "architecture": ("runtime.md", "# Runtime\n\nRuntime structure.\n"),
            "data-and-state": (
                "persistence.md",
                "# Persistence\n\nState authority.\n",
            ),
        },
    )
    report = validate_fleet(fixture.targets[0].store, fixture.fleet_state)
    assert report.verdict.value == "pass"
    return fixture


def _run_review(
    fixture: FleetFixture,
    client: DummyLLMClient,
):
    profile = _profile()
    return asyncio.run(
        reconcile_fleet(
            fleet_spec=fixture.spec,
            fleet_state=fixture.fleet_state,
            catalog=fixture.catalog,
            target_definitions=[target.definition for target in fixture.targets],
            reviewer_profile=profile,
            reviewer_instructions=Path(
                "src/prompts/reviewer/reconciliation.md"
            ).read_text(encoding="utf-8"),
            reconciliation_rubric="Apply the locked fleet reconciliation criteria.",
            context_window_manager=ContextWindowManager(profile),
            llm_client=client,
            coordinator=FleetExecutionCoordinator(),
            persistence=fixture.targets[0].store,
        )
    )


def _client(
    result: FleetReviewModelResult,
    *,
    input_tokens: int = 20,
    output_tokens: int = 5,
) -> DummyLLMClient:
    response: LLMResponse[BaseModel] = LLMResponse(
        structured_output=result,
        usage=LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        provider="test-provider",
        model="review-model",
        response_id="response-1",
    )
    return DummyLLMClient([response])


def _pass_result() -> FleetReviewModelResult:
    return FleetReviewModelResult(
        outcome=ReviewVerdict.PASS,
        summary="The accepted memory corpus is coherent.",
    )


def verdict_subject_refs(fixture: FleetFixture, report_id: str) -> list[str]:
    from models.fleet_validation import FleetValidationReport

    report = FleetValidationReport.model_validate_json(
        fixture.targets[0].store.paths.fleet_validation_report(report_id).read_bytes()
    )
    return report.accepted_target_result_refs
