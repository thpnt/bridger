from datetime import UTC, datetime
from typing import get_type_hints

import pytest
from pydantic import ValidationError

import bridger.models.context_plan as context_plan_models
import bridger.models.repository_path as repository_path_models
from bridger.models.context_plan import (
    ContextPlanInspectedExcerpt,
    ContextPlanInspectedSymbol,
    ContextPlanRunStatus,
    ContextPlanSearchRecord,
    ContextPlanValidationIssue,
    FinalizationContext,
    FinalizationDecision,
    FinalizationDecisionCode,
    ToolBudgetCost,
    ToolCallRequest,
    ToolExecutionEvent,
    ToolExecutionEventType,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolInspectionDelta,
)
from bridger.models.repository_path import RepositoryPath


def make_cost() -> ToolBudgetCost:
    return ToolBudgetCost()


def make_result(status: ToolExecutionStatus) -> ToolExecutionResult:
    return ToolExecutionResult(
        call_id="call_1",
        tool_name="read_file_excerpt",
        status=status,
        output={"path": "src/main.py"},
        estimated_cost=make_cost(),
        actual_cost=make_cost(),
    )


def test_shared_contract_path_fields_use_repository_path() -> None:
    delta_hints = get_type_hints(ToolInspectionDelta, include_extras=True)
    context_hints = get_type_hints(FinalizationContext, include_extras=True)

    assert delta_hints["discovered_paths"] == list[RepositoryPath]
    assert delta_hints["evidence_paths"] == list[RepositoryPath]
    assert delta_hints["manifests_inspected"] == list[RepositoryPath]
    assert delta_hints["excerpts_read"] == list[ContextPlanInspectedExcerpt]
    assert delta_hints["symbols_inspected"] == list[ContextPlanInspectedSymbol]
    assert delta_hints["searches_performed"] == list[ContextPlanSearchRecord]
    assert context_hints["evidence_paths"] == list[RepositoryPath]


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.py"])
def test_shared_contracts_reject_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ToolInspectionDelta(evidence_paths=[path])

    with pytest.raises(ValidationError):
        FinalizationContext(
            run_status=ContextPlanRunStatus.RUNNING,
            stalled=False,
            hard_budget_exhausted=False,
            evidence_paths=[path],
            finalization_request_count=0,
        )


def test_repository_relative_path_contract_is_not_introduced() -> None:
    assert not hasattr(context_plan_models, "RepositoryRelativePath")
    assert not hasattr(repository_path_models, "RepositoryRelativePath")


@pytest.mark.parametrize(
    "field_name",
    [
        "tool_calls",
        "file_reads",
        "excerpts",
        "searches",
        "symbol_queries",
    ],
)
def test_tool_budget_cost_rejects_negative_counters(field_name: str) -> None:
    with pytest.raises(ValidationError):
        ToolBudgetCost(**{field_name: -1})


def test_collection_defaults_are_independent() -> None:
    first_delta = ToolInspectionDelta()
    second_delta = ToolInspectionDelta()
    first_result = make_result(ToolExecutionStatus.COMPLETED)
    second_result = make_result(ToolExecutionStatus.COMPLETED)
    first_decision = FinalizationDecision(
        accepted=True,
        code=FinalizationDecisionCode.ACCEPTED,
    )
    second_decision = FinalizationDecision(
        accepted=True,
        code=FinalizationDecisionCode.ACCEPTED,
    )
    first_event = ToolExecutionEvent(
        event_type=ToolExecutionEventType.TOOL_CALL_REQUESTED,
        call_id="call_1",
        tool_name="read_file_excerpt",
        fingerprint="fingerprint",
        occurred_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    second_event = ToolExecutionEvent(
        event_type=ToolExecutionEventType.TOOL_CALL_REQUESTED,
        call_id="call_2",
        tool_name="read_file_excerpt",
        fingerprint="fingerprint",
        occurred_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    first_context = FinalizationContext(
        run_status=ContextPlanRunStatus.RUNNING,
        stalled=False,
        hard_budget_exhausted=False,
        finalization_request_count=0,
    )
    second_context = FinalizationContext(
        run_status=ContextPlanRunStatus.RUNNING,
        stalled=False,
        hard_budget_exhausted=False,
        finalization_request_count=0,
    )

    first_delta.discovered_paths.append("src/main.py")
    first_result.inspection_delta.evidence_paths.append("src/main.py")
    first_result.issues.append(
        ContextPlanValidationIssue(
            code="warning",
            location=["output"],
            message="Warning",
            context={},
        )
    )
    first_decision.issues.append(
        ContextPlanValidationIssue(
            code="warning",
            location=["request"],
            message="Warning",
            context={},
        )
    )
    first_event.issue_codes.append("warning")
    first_context.evidence_paths.append("src/main.py")

    assert second_delta.discovered_paths == []
    assert second_result.issues == []
    assert second_result.inspection_delta.evidence_paths == []
    assert second_decision.issues == []
    assert second_event.issue_codes == []
    assert second_context.evidence_paths == []


def test_tool_call_request_accepts_json_compatible_arguments() -> None:
    request = ToolCallRequest(
        call_id="call_1",
        name="search_symbols",
        arguments={"query": "main", "filters": {"limit": 5}, "exact": False},
    )

    assert request.arguments["filters"] == {"limit": 5}


def test_tool_execution_status_values_are_stable() -> None:
    assert {item.value for item in ToolExecutionStatus} == {
        "completed",
        "rejected",
        "failed",
    }


def test_shared_event_and_decision_code_values_are_stable() -> None:
    assert {item.value for item in ToolExecutionEventType} == {
        "tool_call_requested",
        "tool_call_rejected",
        "tool_call_completed",
        "tool_call_failed",
    }
    assert {item.value for item in FinalizationDecisionCode} == {
        "accepted",
        "invalid_request",
        "run_not_active",
        "run_not_synthesizable",
        "run_stalled",
        "run_failed",
        "budget_exhausted",
        "unsafe_evidence_path",
        "unknown_evidence_path",
        "uninspected_evidence_path",
    }


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.COMPLETED,
        ToolExecutionStatus.REJECTED,
        ToolExecutionStatus.FAILED,
    ],
)
def test_tool_execution_result_accepts_all_execution_statuses(
    status: ToolExecutionStatus,
) -> None:
    assert make_result(status).status is status


def test_tool_inspection_delta_keeps_discovery_and_evidence_distinct() -> None:
    delta = ToolInspectionDelta(
        discovered_paths=["src/main.py", "src/settings.py"],
        evidence_paths=["src/main.py"],
        excerpts_read=[
            ContextPlanInspectedExcerpt(path="src/main.py", line_start=1, line_end=5)
        ],
        symbols_inspected=[
            ContextPlanInspectedSymbol(identifier="main", path="src/main.py")
        ],
        searches_performed=[
            ContextPlanSearchRecord(tool="search", query="main", result_count=2)
        ],
    )

    assert delta.discovered_paths == ["src/main.py", "src/settings.py"]
    assert delta.evidence_paths == ["src/main.py"]


def test_tool_execution_event_serializes_compact_operational_fields() -> None:
    event = ToolExecutionEvent(
        event_type=ToolExecutionEventType.TOOL_CALL_COMPLETED,
        call_id="call_1",
        tool_name="read_file_excerpt",
        fingerprint="fingerprint",
        estimated_cost=make_cost(),
        actual_cost=make_cost(),
        inspection_delta=ToolInspectionDelta(evidence_paths=["src/main.py"]),
        occurred_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    payload = event.model_dump(mode="json")

    assert "output" not in payload
    assert "source_code" not in payload
    assert "prompt" not in payload
    assert "reasoning" not in payload


def test_finalization_context_validates_paths_and_request_count() -> None:
    context = FinalizationContext(
        run_status=ContextPlanRunStatus.RUNNING,
        stalled=False,
        hard_budget_exhausted=False,
        evidence_paths=["src/main.py"],
        finalization_request_count=2,
    )

    assert context.evidence_paths == ["src/main.py"]

    with pytest.raises(ValidationError):
        FinalizationContext(
            run_status=ContextPlanRunStatus.RUNNING,
            stalled=False,
            hard_budget_exhausted=False,
            finalization_request_count=-1,
        )


def test_finalization_decision_serializes_code_and_issues() -> None:
    decision = FinalizationDecision(
        accepted=False,
        code=FinalizationDecisionCode.UNINSPECTED_EVIDENCE_PATH,
        issues=[
            ContextPlanValidationIssue(
                code="uninspected_evidence_path",
                location=["key_evidence_paths", 0],
                message="Evidence path was not inspected",
                context={"path": "src/main.py"},
            )
        ],
    )

    assert decision.model_dump(mode="json") == {
        "accepted": False,
        "code": "uninspected_evidence_path",
        "issues": [
            {
                "code": "uninspected_evidence_path",
                "location": ["key_evidence_paths", 0],
                "message": "Evidence path was not inspected",
                "context": {"path": "src/main.py"},
            }
        ],
    }
