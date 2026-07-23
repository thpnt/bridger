from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.deterministic.context_plan.discovery_tools import DiscoveryToolExecutor
from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    ContextPlanRunState,
    DiscoveryBudgetPolicy,
)
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanRepository,
    ToolCallRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from bridger.tools.context import BridgerToolContext

NOW = datetime(2026, 7, 23, tzinfo=UTC)


@pytest.fixture
def context_with_repo(tmp_path: Path) -> BridgerToolContext:
    _, context = inherited_tool_repo.__wrapped__(tmp_path)
    return context


def make_state(context: BridgerToolContext) -> ContextPlanRunState:
    state = ContextPlanRunState(
        run_id="run-1",
        repo=ContextPlanRepository(
            root_name=context.repo_discovery.artifact.repo.root_name,
            revision=context.repo_discovery.artifact.repo.revision,
        ),
        safe_file_count=len(context.path_safety.safe_paths),
        started_at=NOW,
    )
    state.start(now=NOW)
    return state


def read_request(call_id: str = "read-1") -> ToolCallRequest:
    return ToolCallRequest(
        call_id=call_id,
        name="read_file_excerpt",
        arguments={"path": "src/app.py", "start_line": 1, "end_line": 5},
    )


def finalization_request() -> ToolCallRequest:
    return ToolCallRequest(
        call_id="finalize-1",
        name="request_context_plan_finalization",
        arguments={
            "explored_areas": ["application entrypoint"],
            "key_evidence_paths": ["src/app.py"],
            "unresolved_areas": [],
            "sufficiency_reason": "The excerpt is grounded evidence.",
        },
    )


def execute_and_record(
    state: ContextPlanRunState,
    executor: DiscoveryToolExecutor,
    request: ToolCallRequest,
) -> tuple[str, ToolExecutionResult]:
    definition = executor.registry.get(request.name)
    assert definition is not None
    fingerprint = state.record_tool_request(request, definition.estimated_cost, now=NOW)
    result = executor.execute(request)
    state.record_tool_result(result, fingerprint, now=NOW)
    return fingerprint, result


def test_safe_inspection_records_evidence_and_persists_snapshot(
    context_with_repo: BridgerToolContext, tmp_path: Path
) -> None:
    state = make_state(context_with_repo)
    _, result = execute_and_record(
        state, DiscoveryToolExecutor(context_with_repo), read_request()
    )

    snapshot = ContextPlanRunRecorder(tmp_path / "context-plan-run.json").persist(
        state, now=NOW
    )

    assert result.status is ToolExecutionStatus.COMPLETED
    assert snapshot.inspection.inspected_files == ["src/app.py"]
    assert snapshot.inspection.inspected_excerpts[0].path == "src/app.py"


def test_unsafe_request_records_rejection_without_inspection_progress(
    context_with_repo: BridgerToolContext,
) -> None:
    state = make_state(context_with_repo)
    request = ToolCallRequest(
        call_id="unsafe-1",
        name="read_file_excerpt",
        arguments={"path": "/etc/passwd"},
    )
    _, result = execute_and_record(
        state, DiscoveryToolExecutor(context_with_repo), request
    )

    assert result.status is ToolExecutionStatus.REJECTED
    assert state.coverage.evidence_paths == set()
    assert state.events[-1].event_type.value == "tool_call_rejected"


def test_equivalent_requests_share_a_duplicate_fingerprint(
    context_with_repo: BridgerToolContext,
) -> None:
    state = make_state(context_with_repo)
    executor = DiscoveryToolExecutor(context_with_repo)
    first, _ = execute_and_record(state, executor, read_request("read-1"))
    second, _ = execute_and_record(state, executor, read_request("read-2"))

    assert first == second
    assert state.fingerprint_counts[first] == 2


def test_discovered_only_path_is_rejected_for_finalization(
    context_with_repo: BridgerToolContext,
) -> None:
    state = make_state(context_with_repo)
    executor = DiscoveryToolExecutor(context_with_repo)
    _, result = execute_and_record(
        state,
        executor,
        ToolCallRequest(
            call_id="search-1", name="search_paths", arguments={"query": "src/app.py"}
        ),
    )
    policy = ContextPlanCompletionPolicy(context_with_repo.path_safety)
    decision = policy.evaluate(
        ContextPlanFinalizationRequest.model_validate(finalization_request().arguments),
        state.finalization_context(DiscoveryBudgetPolicy(), now=NOW),
    )

    assert result.status is ToolExecutionStatus.COMPLETED
    assert state.coverage.discovered_paths == {"src/app.py"}
    assert decision.accepted is False
    assert decision.code.value == "uninspected_evidence_path"


def test_grounded_finalization_uses_task_four_through_control_tool(
    context_with_repo: BridgerToolContext,
) -> None:
    state = make_state(context_with_repo)
    policy = ContextPlanCompletionPolicy(context_with_repo.path_safety)
    budget_policy = DiscoveryBudgetPolicy()
    executor = DiscoveryToolExecutor(
        context_with_repo,
        finalization_evaluator=policy,
        finalization_context_provider=lambda: state.finalization_context(
            budget_policy, now=NOW
        ),
    )
    execute_and_record(state, executor, read_request())
    request = finalization_request()
    state.record_finalization_request(
        ContextPlanFinalizationRequest.model_validate(request.arguments), now=NOW
    )
    _, result = execute_and_record(state, executor, request)

    assert result.status is ToolExecutionStatus.COMPLETED
    assert result.output["decision"]["accepted"] is True


def test_execution_failure_leaves_a_durable_run_snapshot(
    context_with_repo: BridgerToolContext,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = make_state(context_with_repo)

    def fail_read(*_: object) -> dict[str, object]:
        raise RuntimeError("unexpected read failure")

    monkeypatch.setattr(context_with_repo.file_read, "read_excerpt", fail_read)
    _, result = execute_and_record(
        state, DiscoveryToolExecutor(context_with_repo), read_request()
    )
    state.fail("tool execution failed", now=NOW)
    snapshot = ContextPlanRunRecorder(tmp_path / "context-plan-run.json").persist(
        state, now=NOW
    )

    assert result.status is ToolExecutionStatus.FAILED
    assert state.events[-2].event_type.value == "tool_call_failed"
    assert snapshot.status.value == "failed"
    assert (tmp_path / "context-plan-run.json").is_file()
