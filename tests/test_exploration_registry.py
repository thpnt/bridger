from pathlib import Path

from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.discovery_tools import DiscoveryToolExecutor
from bridger.models.context_plan import ToolCallRequest, ToolExecutionStatus
from bridger.tools.context import BridgerToolContext

EXPLORATION_TOOLS = {
    "inspect_repo_discovery",
    "inspect_manifest",
    "list_files",
    "get_file_overview",
    "list_symbols",
    "search_symbols",
    "read_symbol_excerpt",
    "search_with_context",
    "read_file_ranges",
    "read_around_match",
    "get_inspection_status",
    "validate_paths",
}


def context(tmp_path: Path) -> BridgerToolContext:
    _, tool_context = inherited_tool_repo.__wrapped__(tmp_path)
    return tool_context


def call(executor: DiscoveryToolExecutor, name: str, arguments: dict[str, object]):
    return executor.execute(
        ToolCallRequest(call_id=name, name=name, arguments=arguments)
    )


def test_registry_advertises_exact_exploration_tools(tmp_path: Path) -> None:
    executor = DiscoveryToolExecutor(context(tmp_path))
    names = {item.name for item in executor.registry.definitions}

    assert names - {"request_context_plan_finalization"} == EXPLORATION_TOOLS


def test_navigation_and_read_tools_have_common_metadata(tmp_path: Path) -> None:
    executor = DiscoveryToolExecutor(context(tmp_path))
    results = [
        call(executor, "inspect_repo_discovery", {}),
        call(executor, "list_files", {"prefix": "src"}),
        call(executor, "get_file_overview", {"path": "src/app.py"}),
        call(executor, "list_symbols", {"path": "src/app.py"}),
        call(
            executor,
            "read_symbol_excerpt",
            {"symbol_id": "sym:src/app.py:3:main"},
        ),
        call(executor, "search_with_context", {"query": "return"}),
        call(
            executor,
            "read_file_ranges",
            {"path": "src/app.py", "ranges": [{"line_start": 1, "line_end": 2}]},
        ),
        call(executor, "read_around_match", {"path": "src/app.py", "line": 2}),
        call(executor, "validate_paths", {"paths": ["src", "src/app.py"]}),
    ]

    for result in results:
        assert result.status is ToolExecutionStatus.COMPLETED
        assert {
            "status",
            "total_available",
            "returned_count",
            "has_more",
            "next_cursor",
            "truncated",
            "omitted_count",
            "omitted_reasons",
            "warnings",
        } <= set(result.output)


def test_file_and_symbol_cursors_reject_filter_changes(tmp_path: Path) -> None:
    executor = DiscoveryToolExecutor(context(tmp_path))
    first = call(executor, "list_files", {"prefix": "src", "limit": 1})
    assert first.output["has_more"] is True
    changed = call(
        executor,
        "list_files",
        {
            "prefix": "src",
            "extension": "py",
            "limit": 1,
            "cursor": first.output["next_cursor"],
        },
    )

    assert changed.status is ToolExecutionStatus.REJECTED
    assert changed.issues[0].code == "invalid_cursor"


def test_ranges_validate_before_reading(tmp_path: Path) -> None:
    executor = DiscoveryToolExecutor(context(tmp_path))
    result = call(
        executor,
        "read_file_ranges",
        {"path": "src/app.py", "ranges": [{"line_start": 1, "line_end": 999}]},
    )

    assert result.status is ToolExecutionStatus.REJECTED
    assert result.issues[0].code == "invalid_range"
