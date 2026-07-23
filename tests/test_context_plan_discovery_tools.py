from pathlib import Path

import pytest
from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.discovery_tools import (
    DiscoveryToolExecutor,
    tool_call_request_from_llm_call,
    tool_result_to_llm_message,
)
from bridger.llm.models import LLMToolCall
from bridger.models.context_plan import (
    ContextPlanFinalizationRequest,
    ContextPlanRunStatus,
    FinalizationContext,
    FinalizationDecision,
    FinalizationDecisionCode,
    ToolCallRequest,
    ToolExecutionStatus,
)
from bridger.tools.context import BridgerToolContext

REQUIRED_TOOLS = {
    "inspect_repo_discovery",
    "inspect_graph_summary",
    "inspect_manifest",
    "list_files",
    "search_paths",
    "grep_contents",
    "read_file_excerpt",
    "list_config_files",
    "list_docs_files",
    "list_instruction_files",
    "search_symbols",
    "list_symbols",
    "get_symbol",
    "get_graph_neighbors",
    "get_reverse_imports",
    "list_file_imports",
    "list_declared_entrypoints",
    "validate_paths",
    "request_context_plan_finalization",
}


class AcceptingFinalizationEvaluator:
    def evaluate(
        self,
        request: ContextPlanFinalizationRequest,
        context: FinalizationContext,
    ) -> FinalizationDecision:
        assert request.key_evidence_paths == ["src/app.py"]
        assert context.evidence_paths == ["src/app.py"]
        return FinalizationDecision(
            accepted=True,
            code=FinalizationDecisionCode.ACCEPTED,
        )


def active_context() -> FinalizationContext:
    return FinalizationContext(
        run_status=ContextPlanRunStatus.RUNNING,
        stalled=False,
        hard_budget_exhausted=False,
        evidence_paths=["src/app.py"],
        finalization_request_count=0,
    )


@pytest.fixture
def context_with_repo(
    tmp_path: Path,
) -> BridgerToolContext:
    tool_repo = inherited_tool_repo.__wrapped__(tmp_path)
    _, context = tool_repo
    return context


def test_registry_contains_required_tools_and_llm_definitions(
    context_with_repo: BridgerToolContext,
) -> None:
    executor = DiscoveryToolExecutor(context_with_repo)

    assert {definition.name for definition in executor.registry.definitions} == (
        REQUIRED_TOOLS
    )
    assert {definition.name for definition in executor.registry.llm_definitions()} == (
        REQUIRED_TOOLS
    )
    assert (
        executor.registry.get("read_file_excerpt").input_model.model_json_schema()[
            "type"
        ]
        == "object"
    )


def test_safe_excerpt_records_evidence_and_bounded_output(
    context_with_repo: BridgerToolContext,
) -> None:
    result = DiscoveryToolExecutor(context_with_repo).execute(
        ToolCallRequest(
            call_id="call_1",
            name="read_file_excerpt",
            arguments={"path": "src/app.py", "start_line": 1, "end_line": 10},
        )
    )

    assert result.status is ToolExecutionStatus.COMPLETED
    assert result.output["path"] == "src/app.py"
    assert result.truncated is True
    assert result.actual_cost.file_reads == 1
    assert result.inspection_delta.evidence_paths == ["src/app.py"]
    assert result.inspection_delta.excerpts_read[0].line_end == 2


@pytest.mark.parametrize("path", ["/src/app.py", "../src/app.py", ".env"])
def test_unsafe_or_skipped_path_is_rejected(
    context_with_repo: BridgerToolContext, path: str
) -> None:
    result = DiscoveryToolExecutor(context_with_repo).execute(
        ToolCallRequest(
            call_id="call_1",
            name="read_file_excerpt",
            arguments={"path": path},
        )
    )

    assert result.status is ToolExecutionStatus.REJECTED
    assert result.inspection_delta.evidence_paths == []


def test_search_reports_discovery_without_evidence(
    context_with_repo: BridgerToolContext,
) -> None:
    result = DiscoveryToolExecutor(context_with_repo).execute(
        ToolCallRequest(
            call_id="call_1",
            name="search_paths",
            arguments={"query": "src/"},
        )
    )

    assert result.status is ToolExecutionStatus.COMPLETED
    assert result.inspection_delta.discovered_paths == ["src/app.py", "src/util.py"]
    assert result.inspection_delta.evidence_paths == []
    assert result.inspection_delta.searches_performed[0].tool == "search_paths"


def test_finalization_control_tool_uses_injected_evaluator(
    context_with_repo: BridgerToolContext,
) -> None:
    executor = DiscoveryToolExecutor(
        context_with_repo,
        finalization_evaluator=AcceptingFinalizationEvaluator(),
        finalization_context_provider=active_context,
    )
    result = executor.execute(
        ToolCallRequest(
            call_id="call_1",
            name="request_context_plan_finalization",
            arguments={
                "explored_areas": ["application"],
                "key_evidence_paths": ["src/app.py"],
                "unresolved_areas": [],
                "sufficiency_reason": "The inspected excerpt provides the evidence.",
            },
        )
    )

    assert result.status is ToolExecutionStatus.COMPLETED
    assert result.output["decision"]["code"] == "accepted"


def test_llm_adapters_keep_call_identity_and_result_status(
    context_with_repo: BridgerToolContext,
) -> None:
    request = tool_call_request_from_llm_call(
        LLMToolCall(id="call_1", name="search_paths", arguments={"query": "src"})
    )
    result = DiscoveryToolExecutor(context_with_repo).execute(request)
    message = tool_result_to_llm_message(result)

    assert message.tool_call_id == "call_1"
    assert message.tool_name == "search_paths"
    assert message.tool_failed is False
    assert message.tool_result["status"] == "completed"
