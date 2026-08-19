"""Focused Stage 8 target-review lifecycle and recovery tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel
from test_memory_persistence import RuntimeFixture, _recover
from test_memory_validation import FakeNavigator, _passing_fixture

import memory.review as review_module
from llm.errors import LLMConnectionError
from llm.models import LLMOperation, LLMResponse, LLMUsage
from llm.testing.dummy import DummyLLMClient
from memory import (
    ContextWindowManager,
    FleetExecutionCoordinator,
    TargetReviewBudgetError,
    TargetReviewError,
    TargetWorkspace,
    handle_finalization_request,
    resolve_review_finding,
    resolve_review_verdict,
    review_target,
    validate_target_candidate,
)
from models.hydration import WorkerProfile
from models.memory import FindingOrigin, TargetPhase, TargetTaskState
from models.review import (
    ReviewerInstructions,
    ReviewFindingDraft,
    ReviewFindingSeverity,
    ReviewVerdict,
    TargetReviewModelResult,
)


def test_review_passes_exact_checkpoint_and_awaits_acceptance(tmp_path: Path) -> None:
    fixture, request = _ready_for_review(tmp_path)
    Path(fixture.target_spec.target_workspace, "architecture.md").write_text(
        "ambient mutation after validation",
        encoding="utf-8",
    )
    client = _client(_pass_result(), input_tokens=31, output_tokens=7)
    usage_before = fixture.target_state.usage.model_copy(deep=True)
    fleet_usage_before = fixture.fleet_state.usage.model_copy(deep=True)

    verdict = _run_review(fixture, client)

    assert verdict.verdict is ReviewVerdict.PASS
    assert verdict.finalization_request_id == request.finalization_request_id
    assert verdict.candidate_checkpoint_ref == request.candidate_checkpoint_ref
    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert (
        fixture.target_state.pending_finalization_request_ref
        == request.finalization_request_id
    )
    assert fixture.target_state.open_finding_refs == []
    assert fixture.target_state.usage.model_calls == usage_before.model_calls + 1
    assert fixture.target_state.usage.input_tokens == usage_before.input_tokens + 31
    assert fixture.target_state.usage.output_tokens == usage_before.output_tokens + 7
    assert fixture.fleet_state.usage.model_calls == fleet_usage_before.model_calls + 1
    assert client.requests[0].operation is LLMOperation.MEMORY_AGENT_REVIEW
    assert client.requests[0].tools == []
    assert "# Candidate" in (client.requests[0].messages[1].content or "")
    assert "ambient mutation after validation" not in (
        client.requests[0].messages[1].content or ""
    )


def test_needs_work_persists_runtime_findings_and_routes_to_repair(
    tmp_path: Path,
) -> None:
    fixture, request = _ready_for_review(tmp_path)
    result = TargetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="The architecture explanation is too shallow.",
        blocking_findings=[
            ReviewFindingDraft(
                rubric_dimension="Runtime composition",
                affected_scope="Main runtime flow",
                affected_artifact_id=fixture.target_state.artifact_refs[0].artifact_id,
                message="The central runtime path is only named.",
                repair_instruction="Explain the path from bootstrap to execution.",
            )
        ],
        non_blocking_findings=[
            ReviewFindingDraft(
                rubric_dimension="Terminology",
                message="One component name is inconsistent.",
                repair_instruction="Use one component name consistently.",
            )
        ],
        repair_priorities=["Explain the central runtime path."],
    )

    verdict = _run_review(fixture, _client(result))

    assert verdict.verdict is ReviewVerdict.NEEDS_WORK
    assert fixture.target_state.phase is TargetPhase.REPAIR
    assert fixture.target_state.pending_finalization_request_ref is None
    assert fixture.target_state.open_finding_refs == verdict.blocking_finding_refs
    assert all(
        reference.origin is FindingOrigin.TARGET_REVIEW
        for reference in fixture.target_state.open_finding_refs
    )
    blocking = resolve_review_finding(
        fixture.store,
        fixture.target_spec,
        verdict.blocking_finding_refs[0].finding_id,
    )
    non_blocking = resolve_review_finding(
        fixture.store,
        fixture.target_spec,
        verdict.non_blocking_finding_refs[0].finding_id,
    )
    assert blocking.severity is ReviewFindingSeverity.BLOCKING
    assert non_blocking.severity is ReviewFindingSeverity.NON_BLOCKING
    assert (
        resolve_review_verdict(
            fixture.store,
            fixture.target_spec,
            request.finalization_request_id,
        )
        == verdict
    )


def test_duplicate_review_reuses_one_authoritative_verdict(tmp_path: Path) -> None:
    fixture, request = _ready_for_review(tmp_path)
    client = _client(_pass_result())

    first = _run_review(fixture, client)
    second = _run_review(
        fixture,
        client,
        finalization_request_id=request.finalization_request_id,
    )

    assert second == first
    assert len(client.requests) == 1
    verdicts = fixture.store.paths.target_root(fixture.target_spec) / "review-verdicts"
    assert len(list(verdicts.glob("*.json"))) == 1
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "review_completed" for event in events) == 1


def test_transient_provider_failure_leaves_review_runnable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, request = _ready_for_review(tmp_path)
    error = LLMConnectionError("temporary outage", retryable=True)
    client = DummyLLMClient([error])

    async def one_attempt(
        operation: object,
        *,
        before_attempt: object,
        on_retry: object,
    ) -> object:
        del on_retry
        await before_attempt(1)  # type: ignore[operator]
        return await operation()  # type: ignore[operator]

    monkeypatch.setattr(review_module, "run_provider_with_retry", one_attempt)
    with pytest.raises(LLMConnectionError, match="temporary outage"):
        _run_review(fixture, client)

    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert (
        fixture.target_state.pending_finalization_request_ref
        == request.finalization_request_id
    )
    assert (
        resolve_review_verdict(
            fixture.store,
            fixture.target_spec,
            request.finalization_request_id,
        )
        is None
    )
    assert fixture.target_state.usage.model_calls == 1
    assert fixture.store.provider_reservations() == []


def test_crash_before_verdict_persistence_can_rerun_reviewer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, request = _ready_for_review(tmp_path)
    original_complete = review_module._complete_review

    def interrupt(*_: object) -> object:
        raise OSError("simulated crash before review commit")

    monkeypatch.setattr(review_module, "_complete_review", interrupt)
    with pytest.raises(OSError, match="before review commit"):
        _run_review(fixture, _client(_pass_result()))
    assert (
        resolve_review_verdict(
            fixture.store,
            fixture.target_spec,
            request.finalization_request_id,
        )
        is None
    )
    assert fixture.target_state.phase is TargetPhase.REVIEWING

    monkeypatch.setattr(review_module, "_complete_review", original_complete)
    verdict = _run_review(fixture, _client(_pass_result()))

    assert verdict.verdict is ReviewVerdict.PASS
    assert fixture.target_state.usage.model_calls == 2


def test_committed_review_recovers_forward_and_is_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, request = _ready_for_review(tmp_path)
    original_apply = fixture.store._apply_intent

    def interrupt_completion(transaction_root: Path, intent: object) -> None:
        event = getattr(intent, "event")
        if getattr(event, "event_type") == "review_completed":
            raise OSError("simulated review completion crash")
        original_apply(transaction_root, intent)  # type: ignore[arg-type]

    monkeypatch.setattr(fixture.store, "_apply_intent", interrupt_completion)
    with pytest.raises(TargetReviewError, match="persist target review"):
        _run_review(fixture, _client(_pass_result()))

    monkeypatch.setattr(fixture.store, "_apply_intent", original_apply)
    fixture.store.recover_transactions()
    fixture.store.recover_transactions()
    persisted = TargetTaskState.model_validate_json(
        fixture.store.paths.target_state(fixture.target_spec).read_bytes()
    )
    client = DummyLLMClient([])
    verdict = _run_review(
        fixture,
        client,
        finalization_request_id=request.finalization_request_id,
    )

    assert persisted.phase is TargetPhase.REVIEWING
    assert verdict.verdict is ReviewVerdict.PASS
    assert client.requests == []
    events = fixture.store.recover_event_tail()
    assert sum(event.event_type == "review_completed" for event in events) == 1


def test_recovery_after_pass_reuses_verdict_without_provider_state(
    tmp_path: Path,
) -> None:
    fixture, request = _ready_for_review(tmp_path)
    expected = _run_review(fixture, _client(_pass_result()))

    recovered = _recover(fixture)
    try:
        recovered_state = recovered.target_states[fixture.target_spec.target_task_id]
        client = DummyLLMClient([])
        actual = asyncio.run(
            review_target(
                fleet_spec=recovered.fleet_spec,
                fleet_state=recovered.fleet_state,
                target_spec=fixture.target_spec,
                target_state=recovered_state,
                catalog=fixture.catalog,
                target_definition=fixture.definition,
                reviewer_profile=_profile(),
                reviewer_instructions=_instructions(fixture),
                context_window_manager=ContextWindowManager(_profile()),
                llm_client=client,
                coordinator=FleetExecutionCoordinator(),
                persistence=recovered.store,
                finalization_request_id=request.finalization_request_id,
            )
        )

        assert actual == expected
        assert recovered_state.phase is TargetPhase.REVIEWING
        assert client.requests == []
    finally:
        recovered.close()


def test_multiple_review_rounds_preserve_history_and_replace_open_projection(
    tmp_path: Path,
) -> None:
    fixture, request_a = _ready_for_review(tmp_path)
    result_a = TargetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="The runtime flow is missing.",
        blocking_findings=[
            ReviewFindingDraft(
                rubric_dimension="Execution paths",
                message="The central execution path is missing.",
                repair_instruction="Add the execution path.",
            )
        ],
        repair_priorities=["Add the execution path."],
    )
    verdict_a = _run_review(fixture, _client(result_a))
    historical_finding = verdict_a.blocking_finding_refs[0]

    _reenter_working(fixture)
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact(
        "architecture.md",
        "# Repaired\n\nBootstrap calls the runtime coordinator.",
        expected_revision=1,
    )
    request_b = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )
    client_b = _client(_pass_result())
    verdict_b = _run_review(fixture, client_b)

    assert request_a.finalization_request_id != request_b.finalization_request_id
    assert verdict_a.review_verdict_id != verdict_b.review_verdict_id
    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert not any(
        reference.origin is FindingOrigin.TARGET_REVIEW
        for reference in fixture.target_state.open_finding_refs
    )
    assert (
        resolve_review_verdict(
            fixture.store,
            fixture.target_spec,
            request_a.finalization_request_id,
        )
        == verdict_a
    )
    assert (
        resolve_review_finding(
            fixture.store,
            fixture.target_spec,
            historical_finding.finding_id,
        ).message
        == "The central execution path is missing."
    )
    assert historical_finding.finding_id in (
        client_b.requests[0].messages[1].content or ""
    )
    assert fixture.target_state.usage.model_calls == 2
    assert fixture.fleet_state.usage.model_calls == 2


def test_target_and_fleet_budget_stops_preserve_review_contract(tmp_path: Path) -> None:
    target_fixture, target_request = _ready_for_review(tmp_path / "target")
    target_limit = target_fixture.target_spec.budget.max_model_calls
    target_fixture.target_state.usage.model_calls = target_limit
    target_fixture.fleet_state.usage.model_calls = target_limit

    with pytest.raises(TargetReviewBudgetError) as target_error:
        _run_review(target_fixture, DummyLLMClient([]))

    assert target_error.value.scope == "target"
    assert target_fixture.target_state.phase is TargetPhase.EXHAUSTED
    assert (
        target_fixture.target_state.pending_finalization_request_ref
        == target_request.finalization_request_id
    )

    fleet_fixture, fleet_request = _ready_for_review(tmp_path / "fleet")
    fleet_fixture.fleet_state.usage.model_calls = (
        fleet_fixture.spec.fleet_budget.max_model_calls
    )
    with pytest.raises(TargetReviewBudgetError) as fleet_error:
        _run_review(fleet_fixture, DummyLLMClient([]))

    assert fleet_error.value.scope == "fleet"
    assert fleet_fixture.target_state.phase is TargetPhase.REVIEWING
    assert (
        fleet_fixture.target_state.pending_finalization_request_ref
        == fleet_request.finalization_request_id
    )


def _ready_for_review(
    tmp_path: Path,
) -> tuple[RuntimeFixture, object]:
    fixture = _passing_fixture(tmp_path)
    request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        FakeNavigator(fixture),  # type: ignore[arg-type]
    )
    return fixture, request


def _run_review(
    fixture: RuntimeFixture,
    client: DummyLLMClient,
    *,
    finalization_request_id: str | None = None,
) -> object:
    profile = _profile()
    return asyncio.run(
        review_target(
            fleet_spec=fixture.spec,
            fleet_state=fixture.fleet_state,
            target_spec=fixture.target_spec,
            target_state=fixture.target_state,
            catalog=fixture.catalog,
            target_definition=fixture.definition,
            reviewer_profile=profile,
            reviewer_instructions=_instructions(fixture),
            context_window_manager=ContextWindowManager(profile),
            llm_client=client,
            coordinator=FleetExecutionCoordinator(),
            persistence=fixture.store,
            finalization_request_id=finalization_request_id,
        )
    )


def _profile() -> WorkerProfile:
    return WorkerProfile(
        profile_id="reviewer-v1",
        model="review-model",
        tokenizer_encoding="cl100k_base",
        model_context_window_tokens=64_000,
        reserved_response_tokens=1_024,
    )


def _instructions(fixture: RuntimeFixture) -> ReviewerInstructions:
    return ReviewerInstructions(
        reviewer_profile_id=fixture.target_spec.reviewer_profile_id,
        target_id=fixture.target_spec.target_id,
        target_contract_version=fixture.target_spec.target_contract_version,
        shared=Path("src/prompts/reviewer/system.md").read_text(encoding="utf-8"),
        target_specific=Path("src/prompts/reviewer/targets/architecture.md").read_text(
            encoding="utf-8"
        ),
    )


def _pass_result() -> TargetReviewModelResult:
    return TargetReviewModelResult(
        outcome=ReviewVerdict.PASS,
        summary="The candidate satisfies the artifact-level target contract.",
    )


def _client(
    result: TargetReviewModelResult,
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


def _reenter_working(fixture: RuntimeFixture) -> None:
    previous = fixture.target_state.phase
    fixture.target_state.phase = TargetPhase.SCHEDULED
    fixture.store.persist_target_state(
        fixture.target_spec,
        fixture.target_state,
        event_type="phase_transition",
        payload={
            "from_phase": previous.value,
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
