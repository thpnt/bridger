"""Focused Stage 9 repair-path integration tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import test_review as review_helpers
from test_persistence import RuntimeFixture, _enter_working, _recover, _runtime
from test_validation import FakeNavigator as ValidationNavigator
from test_worker_cycle import FakeNavigator as WorkerNavigator

from bridger.contracts.memory.core import CompletionStatus, FindingOrigin, TargetPhase
from bridger.contracts.memory.hydration import (
    GraphOverview,
    PermissionProfile,
    WorkerContext,
    WorkerContextMode,
    WorkerCycleFocusKind,
    WorkerInstructions,
    WorkerProfile,
)
from bridger.contracts.memory.review import (
    ReviewFindingDraft,
    ReviewVerdict,
    TargetReviewModelResult,
)
from bridger.contracts.memory.validation import ValidationVerdict
from bridger.llm.models import LLMResponse, LLMToolCall, LLMUsage
from bridger.llm.testing.dummy import DummyLLMClient
from bridger.memory import (
    ContextWindowManager,
    FleetExecutionCoordinator,
    PersistenceRecoveryError,
    TargetWorkspace,
    WorkerCycleOutcome,
    compile_worker_context,
    handle_finalization_request,
    resolve_finalization_request,
    run_worker_cycle,
    schedule_runnable_targets,
    validate_target_candidate,
)

_WORKER_TOOLS = ("write_target_artifact", "update_completion_item")
_GRAPH_OVERVIEW = GraphOverview(
    graph_snapshot_id="snapshot-1",
    graph_contract_version="bridger.graph.v1",
    build_mode="full",
    node_count=0,
    edge_count=0,
    hyperedge_count=0,
    community_count=0,
    central_nodes=(),
    central_nodes_truncated=False,
    surprising_connections=(),
    surprising_connections_truncated=False,
    suggested_questions=(),
    suggested_questions_truncated=False,
)


def test_persisted_yield_rehydrates_directly_to_the_next_focus(tmp_path: Path) -> None:
    fixture = _runtime(tmp_path)
    scheduled = schedule_runnable_targets(
        fixture.spec,
        fixture.fleet_state,
        [fixture.target_spec],
        [fixture.target_state],
        persistence=fixture.store,
    )
    assert scheduled == [fixture.target_spec.target_task_id]
    profile = _worker_profile()
    permissions = PermissionProfile(
        profile_id=fixture.target_spec.permission_profile_id,
        allowed_tool_ids=_WORKER_TOOLS,
    )
    instructions = WorkerInstructions(
        worker_profile_id=profile.profile_id,
        target_id=fixture.target_spec.target_id,
        target_contract_version=fixture.target_spec.target_contract_version,
        shared="Use controlled tools for every mutation.",
        target_specific="Resolve the current bounded objective.",
    )
    context = compile_worker_context(
        fleet_spec=fixture.spec,
        target_spec=fixture.target_spec,
        target_state=fixture.target_state,
        completion_state=fixture.completion_state,
        catalog=fixture.catalog,
        target_definition=fixture.definition,
        worker_profile=profile,
        permission_profile=permissions,
        worker_instructions=instructions,
        graph_overview=_GRAPH_OVERVIEW,
        persistence=fixture.store,
    )
    assert context.cycle_focus.kind is WorkerCycleFocusKind.OBLIGATION
    client = DummyLLMClient(
        [
            _response(
                _call(
                    "completion",
                    "update_completion_item",
                    {
                        "obligation_id": "describe-architecture",
                        "status": CompletionStatus.COVERED.value,
                        "resolution_note": "Bounded objective completed.",
                        "evidence_refs": [],
                    },
                )
            ),
            _response(_call("yield", "yield_cycle", {})),
        ]
    )

    outcome = asyncio.run(
        run_worker_cycle(
            fleet_spec=fixture.spec,
            fleet_state=fixture.fleet_state,
            target_spec=fixture.target_spec,
            target_state=fixture.target_state,
            completion_state=fixture.completion_state,
            target_definition=fixture.definition,
            context=context,
            worker_profile=profile,
            permission_profile=permissions,
            context_window_manager=ContextWindowManager(profile),
            llm_client=client,
            navigator=WorkerNavigator(),  # type: ignore[arg-type]
            evidence={},
            questions={},
            coordinator=FleetExecutionCoordinator(),
            persistence=fixture.store,
        )
    )

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    assert fixture.target_state.pending_finalization_request_ref is None
    rehydrated = compile_worker_context(
        fleet_spec=fixture.spec,
        target_spec=fixture.target_spec,
        target_state=fixture.target_state,
        completion_state=fixture.completion_state,
        catalog=fixture.catalog,
        target_definition=fixture.definition,
        worker_profile=profile,
        permission_profile=permissions,
        worker_instructions=instructions,
        graph_overview=_GRAPH_OVERVIEW,
        persistence=fixture.store,
    )

    assert rehydrated.cycle_focus.kind is (WorkerCycleFocusKind.FINALIZATION_READINESS)
    assert fixture.target_state.usage.cycles == 1
    assert fixture.target_state.usage.tool_calls == 1


def test_hard_validation_failure_reenters_the_normal_worker_pipeline(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    rejected_request = handle_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        {},
        {},
    )
    rejected_report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        ValidationNavigator(fixture),  # type: ignore[arg-type]
    )

    assert rejected_report.verdict is ValidationVerdict.FAIL
    assert fixture.target_state.phase is TargetPhase.REPAIR
    assert fixture.target_state.usage.repair_cycles == 0

    recovered = _recover(fixture)
    try:
        repaired_fixture = RuntimeFixture(
            spec=recovered.fleet_spec,
            fleet_state=recovered.fleet_state,
            target_spec=recovered.target_specs[fixture.target_spec.target_task_id],
            target_state=recovered.target_states[fixture.target_spec.target_task_id],
            completion_state=recovered.completion_states[
                fixture.target_spec.target_task_id
            ],
            catalog=fixture.catalog,
            definition=fixture.definition,
            store=recovered.store,
        )
        context = _run_repair_worker(
            repaired_fixture,
            [
                _call(
                    "write",
                    "write_target_artifact",
                    {"path": "architecture.md", "content": "# Repaired\n"},
                ),
                _call(
                    "completion",
                    "update_completion_item",
                    {
                        "obligation_id": "describe-architecture",
                        "status": CompletionStatus.UNKNOWN.value,
                        "resolution_note": "Repaired after hard validation.",
                        "evidence_refs": [],
                    },
                ),
            ],
        )
        repaired_request = resolve_finalization_request(
            repaired_fixture.store,
            repaired_fixture.target_spec,
            repaired_fixture.target_state,
        )

        assert context.mode is WorkerContextMode.REPAIR
        assert {finding.origin for finding in context.repair_findings} == {
            FindingOrigin.HARD_VALIDATION
        }
        assert repaired_fixture.target_state.usage.repair_cycles == 1
        assert repaired_fixture.fleet_state.usage.repair_cycles == 1
        assert repaired_request.finalization_request_id != (
            rejected_request.finalization_request_id
        )
        assert repaired_request.candidate_checkpoint_ref != (
            rejected_request.candidate_checkpoint_ref
        )
        assert repaired_fixture.target_state.phase is TargetPhase.FINALIZING

        repaired_report = validate_target_candidate(
            repaired_fixture.store,
            repaired_fixture.target_spec,
            repaired_fixture.target_state,
            repaired_fixture.definition,
            ValidationNavigator(repaired_fixture),  # type: ignore[arg-type]
        )

        assert repaired_report.verdict is ValidationVerdict.PASS
        assert repaired_fixture.target_state.phase is TargetPhase.REVIEWING
        assert repaired_fixture.target_state.open_finding_refs == []
        assert repaired_fixture.target_state.last_accepted_result_ref is None
        assert repaired_fixture.store.paths.checkpoint_root(
            repaired_fixture.target_spec,
            rejected_request.candidate_checkpoint_ref,
        ).is_dir()
    finally:
        recovered.close()


def test_review_failure_reenters_stage_7_before_reviewing_again(
    tmp_path: Path,
) -> None:
    fixture, rejected_request = review_helpers._ready_for_review(tmp_path)
    rejected_verdict = review_helpers._run_review(
        fixture,
        review_helpers._client(
            _needs_work_result(fixture.target_state.artifact_refs[0].artifact_id)
        ),
    )
    original_finding = rejected_verdict.finding_refs[0]

    context = _run_repair_worker(
        fixture,
        [
            _call(
                "write",
                "write_target_artifact",
                {
                    "path": "architecture.md",
                    "content": (
                        "# Repaired\n\nBootstrap calls the runtime coordinator.\n"
                    ),
                    "expected_revision": 1,
                },
            )
        ],
    )
    repaired_request = resolve_finalization_request(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
    )

    assert context.mode is WorkerContextMode.REPAIR
    assert [finding.finding_id for finding in context.repair_findings] == [
        original_finding.finding_id
    ]
    assert "central execution path" in context.repair_findings[0].content
    assert context.repair_findings[0].affected_artifact_refs == (
        fixture.target_state.artifact_refs[0].artifact_id,
    )
    assert context.repair_findings[0].affected_obligation_ids == (
        "describe-architecture",
    )
    assert repaired_request.finalization_request_id != (
        rejected_request.finalization_request_id
    )
    assert fixture.target_state.usage.repair_cycles == 1

    repaired_report = validate_target_candidate(
        fixture.store,
        fixture.target_spec,
        fixture.target_state,
        fixture.definition,
        ValidationNavigator(fixture),  # type: ignore[arg-type]
    )

    assert repaired_report.verdict is ValidationVerdict.PASS
    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert fixture.target_state.open_finding_refs == [original_finding]

    repaired_verdict = review_helpers._run_review(
        fixture,
        review_helpers._client(review_helpers._pass_result()),
    )

    assert repaired_verdict.verdict is ReviewVerdict.PASS
    assert fixture.target_state.phase is TargetPhase.REVIEWING
    assert fixture.target_state.open_finding_refs == []
    assert fixture.target_state.last_accepted_result_ref is None


def test_recovery_rejects_a_repair_state_with_a_missing_current_finding(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    handle_finalization_request(
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
        ValidationNavigator(fixture),  # type: ignore[arg-type]
    )
    finding_path = fixture.store.paths.validation_finding(
        fixture.target_spec,
        report.finding_refs[0].finding_id,
    )
    finding_path.unlink()

    with pytest.raises(PersistenceRecoveryError, match="validation finding"):
        _recover(fixture)


def test_recovery_does_not_substitute_a_different_pre_worker_candidate(
    tmp_path: Path,
) -> None:
    fixture = _runtime(tmp_path)
    _enter_working(fixture)
    TargetWorkspace(
        fixture.target_spec,
        fixture.target_state,
        fixture.store,
    ).write_target_artifact("architecture.md", "# Rejected candidate\n")
    handle_finalization_request(
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
        ValidationNavigator(fixture),  # type: ignore[arg-type]
    )
    assert report.verdict is ValidationVerdict.FAIL

    replacement = b"# Uncheckpointed replacement\n"
    Path(fixture.target_spec.target_workspace, "architecture.md").write_bytes(
        replacement
    )
    with pytest.raises(PersistenceRecoveryError, match="recovery validation"):
        _recover(fixture)


def _run_repair_worker(
    fixture: RuntimeFixture,
    operational_calls: list[LLMToolCall],
) -> WorkerContext:
    scheduled = schedule_runnable_targets(
        fixture.spec,
        fixture.fleet_state,
        [fixture.target_spec],
        [fixture.target_state],
        persistence=fixture.store,
    )
    assert scheduled == [fixture.target_spec.target_task_id]
    profile = _worker_profile()
    permissions = PermissionProfile(
        profile_id=fixture.target_spec.permission_profile_id,
        allowed_tool_ids=_WORKER_TOOLS,
    )
    context = compile_worker_context(
        fleet_spec=fixture.spec,
        target_spec=fixture.target_spec,
        target_state=fixture.target_state,
        completion_state=fixture.completion_state,
        catalog=fixture.catalog,
        target_definition=fixture.definition,
        worker_profile=profile,
        permission_profile=permissions,
        worker_instructions=WorkerInstructions(
            worker_profile_id=profile.profile_id,
            target_id=fixture.target_spec.target_id,
            target_contract_version=fixture.target_spec.target_contract_version,
            shared="Use controlled tools for every mutation.",
            target_specific="Repair the current candidate findings.",
        ),
        graph_overview=_GRAPH_OVERVIEW,
        persistence=fixture.store,
    )
    client = DummyLLMClient(
        [
            _response(*operational_calls),
            _response(_call("finalize", "request_finalization", {})),
        ]
    )
    outcome = asyncio.run(
        run_worker_cycle(
            fleet_spec=fixture.spec,
            fleet_state=fixture.fleet_state,
            target_spec=fixture.target_spec,
            target_state=fixture.target_state,
            completion_state=fixture.completion_state,
            target_definition=fixture.definition,
            context=context,
            worker_profile=profile,
            permission_profile=permissions,
            context_window_manager=ContextWindowManager(profile),
            llm_client=client,
            navigator=WorkerNavigator(),  # type: ignore[arg-type]
            evidence={},
            questions={},
            coordinator=FleetExecutionCoordinator(),
            persistence=fixture.store,
        )
    )
    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    return context


def _worker_profile() -> WorkerProfile:
    return WorkerProfile(
        profile_id="worker-v1",
        model="gpt-test",
        tokenizer_encoding="o200k_base",
        model_context_window_tokens=100_000,
        reserved_response_tokens=1_000,
    )


def _needs_work_result(artifact_id: str) -> TargetReviewModelResult:
    return TargetReviewModelResult(
        outcome=ReviewVerdict.NEEDS_WORK,
        summary="The central execution path is missing.",
        findings=[
            ReviewFindingDraft(
                criterion_id="execution-paths",
                affected_artifact_refs=[artifact_id],
                affected_obligation_ids=["describe-architecture"],
                message="The central execution path is missing.",
                required_outcome="The artifact explains the central execution path.",
            )
        ],
    )


def _call(call_id: str, name: str, arguments: dict[str, object]) -> LLMToolCall:
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def _response(*calls: LLMToolCall) -> LLMResponse:
    return LLMResponse(
        tool_calls=list(calls),
        usage=LLMUsage(input_tokens=10, output_tokens=5),
        provider="test",
        model="gpt-test",
    )
