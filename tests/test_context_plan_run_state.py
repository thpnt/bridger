import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    ContextPlanRunState,
    DiscoveryBudgetLimits,
    DiscoveryBudgetPolicy,
    InspectionCoverageTracker,
    ToolCallFingerprinter,
)
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanRepository,
    ContextPlanSearchRecord,
    ToolBudgetCost,
    ToolCallRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInspectionDelta,
)

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def make_state() -> ContextPlanRunState:
    return ContextPlanRunState(
        run_id="run-1",
        repo=ContextPlanRepository(root_name="example", revision="abc123"),
        safe_file_count=4,
        model_profile="default",
        model_name="test-model",
        started_at=NOW,
    )


def make_request(
    call_id: str = "call-1", arguments: dict[str, object] | None = None
) -> ToolCallRequest:
    return ToolCallRequest(
        call_id=call_id,
        name="read_file_ranges",
        arguments=arguments or {"path": "src/main.py", "line_start": 1},
    )


def make_result(
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
    *,
    delta: ToolInspectionDelta | None = None,
    actual_cost: ToolBudgetCost | None = None,
    output: dict[str, object] | None = None,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        call_id="call-1",
        tool_name="read_file_ranges",
        status=status,
        output=output,
        estimated_cost=ToolBudgetCost(file_reads=1, excerpts=1),
        actual_cost=actual_cost or ToolBudgetCost(file_reads=1, excerpts=1),
        inspection_delta=delta or ToolInspectionDelta(),
    )


def test_fingerprints_are_stable_and_independent_of_key_order() -> None:
    first = make_request(
        arguments={"path": "src/main.py", "filters": {"limit": 5, "exact": False}}
    )
    second = make_request(
        call_id="call-2",
        arguments={"filters": {"exact": False, "limit": 5}, "path": "src/main.py"},
    )

    first_fingerprint = ToolCallFingerprinter.fingerprint(first)
    second_fingerprint = ToolCallFingerprinter.fingerprint(second)

    assert first_fingerprint == second_fingerprint


def test_coverage_tracker_is_idempotent_and_distinguishes_evidence() -> None:
    tracker = InspectionCoverageTracker(safe_file_count=3)
    delta = ToolInspectionDelta(
        discovered_paths=["src/main.py", "src/settings.py"],
        evidence_paths=["src/main.py"],
        excerpts_read=[
            ContextPlanInspectedExcerpt(path="src/main.py", line_start=1, line_end=4)
        ],
        symbols_inspected=[
            ContextPlanInspectedSymbol(identifier="main", path="src/main.py")
        ],
        searches_performed=[
            ContextPlanSearchRecord(
                tool="search_with_context", query="main", result_count=2
            )
        ],
    )

    assert tracker.apply(delta) is True
    assert tracker.apply(delta) is False
    assert tracker.discovered_paths == {"src/main.py", "src/settings.py"}
    assert tracker.evidence_paths == {"src/main.py"}
    snapshot = tracker.snapshot()
    assert snapshot.inspected_files == ["src/main.py"]
    assert snapshot.search_records[0].query == "main"


def test_state_records_result_progress_and_deterministic_snapshot() -> None:
    state = make_state()
    state.start(now=NOW)
    request = make_request()
    fingerprint = state.record_tool_request(
        request, ToolBudgetCost(file_reads=1, excerpts=1), now=NOW
    )
    progress = state.record_tool_result(
        make_result(
            delta=ToolInspectionDelta(
                evidence_paths=["src/main.py"],
                excerpts_read=[
                    ContextPlanInspectedExcerpt(
                        path="src/main.py", line_start=1, line_end=3
                    )
                ],
            )
        ),
        fingerprint,
        now=NOW + timedelta(seconds=1),
    )

    snapshot = state.snapshot(now=NOW + timedelta(seconds=2))

    assert progress is True
    assert snapshot.status.value == "running"
    assert snapshot.inspection.inspected_files == ["src/main.py"]
    assert snapshot.inspection.inspected_file_count == 1
    assert snapshot.inspection.remaining_file_count == 3
    assert state.consumed_cost.file_reads == 1
    assert state.consecutive_no_progress == 0


def test_budget_preflight_charges_actual_usage_and_detects_duplicate_calls() -> None:
    state = make_state()
    policy = DiscoveryBudgetPolicy(
        DiscoveryBudgetLimits(tool_calls=2, searches=1, duplicate_call_threshold=1)
    )
    request = make_request()
    fingerprint = ToolCallFingerprinter.fingerprint(request)

    assert policy.preflight_tool_call(
        state, ToolBudgetCost(searches=1), fingerprint, now=NOW
    ).allowed
    state.record_tool_request(request, ToolBudgetCost(searches=1), now=NOW)
    state.record_tool_result(
        make_result(actual_cost=ToolBudgetCost(searches=1)), fingerprint, now=NOW
    )

    duplicate = policy.preflight_tool_call(
        state, ToolBudgetCost(searches=1), fingerprint, now=NOW
    )
    assert duplicate.allowed is False
    assert duplicate.reasons == ("searches", "duplicate_call_threshold")
    assert duplicate.hard_budget_exhausted is True
    assert policy.remaining_budget_summary(state, now=NOW)["searches"] == 0


def test_stall_detection_and_finalization_context_projection() -> None:
    state = make_state()
    policy = DiscoveryBudgetPolicy(
        DiscoveryBudgetLimits(consecutive_no_progress_threshold=2)
    )
    fingerprint = state.record_tool_request(make_request(), ToolBudgetCost(), now=NOW)
    state.record_tool_result(make_result(), fingerprint, now=NOW)
    state.record_tool_result(make_result(), fingerprint, now=NOW)
    state.record_finalization_request(
        ContextPlanFinalizationRequest(
            explored_areas=["runtime"],
            key_evidence_paths=["src/main.py"],
            unresolved_areas=[],
            sufficiency_reason="Enough factual evidence",
        ),
        now=NOW,
    )

    context = state.finalization_context(policy, now=NOW)

    assert state.is_stalled(policy) is True
    assert context.stalled is True
    assert context.finalization_request_count == 1
    assert context.evidence_paths == []


def test_model_and_elapsed_budget_limits_are_enforced() -> None:
    state = make_state()
    policy = DiscoveryBudgetPolicy(
        DiscoveryBudgetLimits(model_turns=1, token_usage=10, elapsed_seconds=30)
    )
    state.record_model_call_completed(10, now=NOW)

    decision = policy.preflight_model_turn(state, now=NOW)

    assert decision.allowed is False
    assert decision.reasons == ("model_turns", "token_usage")
    assert policy.hard_budget_exhausted(state, now=NOW) is True
    assert policy.preflight_tool_call(
        state,
        ToolBudgetCost(),
        "other",
        now=NOW + timedelta(seconds=30),
    ).reasons == ("elapsed_seconds",)


def test_hard_exhaustion_includes_each_tool_cost_counter() -> None:
    state = make_state()
    policy = DiscoveryBudgetPolicy(DiscoveryBudgetLimits(file_reads=1))
    fingerprint = state.record_tool_request(make_request(), ToolBudgetCost(), now=NOW)
    state.record_tool_result(
        make_result(actual_cost=ToolBudgetCost(file_reads=1)),
        fingerprint,
        now=NOW,
    )

    assert policy.hard_budget_exhausted(state, now=NOW) is True


def test_recorder_persists_failure_and_excludes_sensitive_tool_data(
    tmp_path: Path,
) -> None:
    state = make_state()
    fingerprint = state.record_tool_request(make_request(), ToolBudgetCost(), now=NOW)
    state.record_tool_result(
        make_result(
            output={
                "prompt": "private prompt",
                "reasoning": "private reasoning",
                "source": "private source excerpt",
            }
        ),
        fingerprint,
        now=NOW,
    )
    state.fail("handler failed", now=NOW + timedelta(seconds=1))
    recorder = ContextPlanRunRecorder(
        tmp_path / ".bridger/artifacts/context-plan-run.json"
    )

    snapshot = recorder.persist(state, now=NOW + timedelta(seconds=2))
    payload = json.loads(recorder.destination.read_text())

    assert snapshot.status.value == "failed"
    assert payload["errors"][0]["message"] == "handler failed"
    assert "private prompt" not in recorder.destination.read_text()
    assert "private reasoning" not in recorder.destination.read_text()
    assert "private source excerpt" not in recorder.destination.read_text()
    assert not any(
        path.name.endswith(".tmp") for path in recorder.destination.parent.iterdir()
    )


def test_interruption_retains_a_valid_snapshot(tmp_path: Path) -> None:
    state = make_state()
    state.interrupt("process interrupted", now=NOW)
    recorder = ContextPlanRunRecorder(tmp_path / "context-plan-run.json")

    snapshot = recorder.persist(state, now=NOW)

    assert snapshot.status.value == "interrupted"
    payload = json.loads(recorder.destination.read_text())
    assert payload["artifact"] == "context-plan-run"
