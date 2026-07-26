import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.builder import ContextPlanBuilder
from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.deterministic.context_plan.discovery_tools import DiscoveryToolExecutor
from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    DiscoveryBudgetLimits,
    DiscoveryBudgetPolicy,
)
from bridger.deterministic.context_plan.validation import ContextPlanValidationError
from bridger.llm.models import LLMResponse, LLMToolCall, LLMUsage
from bridger.llm.testing import DummyLLMClient
from bridger.models.context_plan import ContextPlan, ContextPlanRun, ToolBudgetCost
from bridger.tools.context import BridgerToolContext
from bridger.tools.errors import BridgerToolError
from bridger.tools.services.artifact_store import ArtifactStore


@pytest.fixture
def context_with_repo(tmp_path: Path) -> tuple[Path, BridgerToolContext]:
    return inherited_tool_repo.__wrapped__(tmp_path)


def tool_response(*calls: LLMToolCall) -> LLMResponse:
    return LLMResponse(
        tool_calls=list(calls),
        provider="dummy",
        model="scripted",
        usage=LLMUsage(total_tokens=10),
    )


def text_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        provider="dummy",
        model="scripted",
        usage=LLMUsage(total_tokens=5),
    )


def finalization_call(call_id: str = "finalize") -> LLMToolCall:
    return LLMToolCall(
        id=call_id,
        name="request_context_plan_finalization",
        arguments={
            "explored_areas": ["application entrypoint"],
            "key_evidence_paths": ["src/app.py"],
            "unresolved_areas": [],
            "sufficiency_reason": "The inspected entrypoint excerpt is sufficient.",
        },
    )


def read_app_ranges_call(call_id: str = "read") -> LLMToolCall:
    return LLMToolCall(
        id=call_id,
        name="read_file_ranges",
        arguments={
            "path": "src/app.py",
            "ranges": [{"line_start": 1, "line_end": 2}],
        },
    )


def valid_plan(*, line_end: int = 2) -> ContextPlan:
    return ContextPlan.model_validate(
        {
            "generated_at": "2026-07-23T12:00:00Z",
            "repo": {"root_name": "fixture", "revision": "test"},
            "summary": {
                "repository_purpose": "Fixture application",
                "project_type": "Python application",
                "detected_stack": ["Python"],
                "main_runtime_flow": "The app module imports its helper.",
                "confidence": 0.9,
            },
            "packages": [
                {
                    "package_id": "pkg.application",
                    "title": "Application",
                    "purpose": "Explain the application entrypoint.",
                    "priority": 1,
                    "topics": ["application-runtime"],
                    "ordered_items": [
                        {
                            "path": "src/app.py",
                            "line_start": 1,
                            "line_end": line_end,
                            "role": "entrypoint",
                            "reason": "Contains application startup.",
                            "expected_use": "Trace the runtime flow.",
                        }
                    ],
                    "provenance": [
                        {
                            "source_type": "file_excerpt",
                            "path": "src/app.py",
                            "line_start": 1,
                            "line_end": line_end,
                            "evidence_note": "Inspected entrypoint excerpt.",
                        }
                    ],
                    "confidence": 0.9,
                    "warnings": [],
                    "unknowns": [],
                }
            ],
            "intentionally_excluded": [],
            "global_warnings": [],
            "global_unknowns": [],
        }
    )


def synthesis_response(plan: ContextPlan) -> LLMResponse:
    return LLMResponse(
        structured_output=plan,
        provider="dummy",
        model="scripted",
        usage=LLMUsage(total_tokens=20),
    )


def make_builder(
    root: Path,
    context: BridgerToolContext,
    client: DummyLLMClient,
    *,
    limits: DiscoveryBudgetLimits,
    executor: DiscoveryToolExecutor | None = None,
    artifact_store: ArtifactStore | None = None,
    writer: Callable | None = None,
) -> ContextPlanBuilder:
    arguments = {
        "llm_client": client,
        "artifact_store": artifact_store or ArtifactStore(root),
        "tool_executor": executor or DiscoveryToolExecutor(context),
        "budget_policy": DiscoveryBudgetPolicy(limits),
        "completion_policy": ContextPlanCompletionPolicy(context.path_safety),
        "run_recorder": ContextPlanRunRecorder(
            root / ".bridger/artifacts/context-plan-run.json"
        ),
        "context_plan_destination": (root / ".bridger/artifacts/context-plan.json"),
    }
    if writer is not None:
        arguments["context_plan_writer"] = writer
    return ContextPlanBuilder(**arguments)


def read_run(root: Path) -> ContextPlanRun:
    return ContextPlanRun.model_validate_json(
        (root / ".bridger/artifacts/context-plan-run.json").read_bytes()
    )


def test_dummy_workflow_recovers_from_rejection_and_writes_both_artifacts(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    destination = root / ".bridger/artifacts/context-plan.json"
    destination.write_bytes(b"previous artifact")
    client = DummyLLMClient(
        [
            tool_response(LLMToolCall(id="list", name="list_files", arguments={})),
            tool_response(
                LLMToolCall(
                    id="search",
                    name="search_symbols",
                    arguments={"query": "main", "path": "src/app.py"},
                )
            ),
            tool_response(finalization_call("premature")),
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call("grounded")),
            synthesis_response(valid_plan()),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=6,
            tool_calls=20,
            consecutive_no_progress_threshold=10,
        ),
    )

    run = asyncio.run(builder.build(run_id="run-happy"))

    assert run.status.value == "completed"
    assert read_run(root) == run
    written_plan = ContextPlan.model_validate_json(destination.read_bytes())
    assert destination.read_bytes() != b"previous artifact"
    assert written_plan.packages[0].package_id == "pkg.application"
    assert len(run.finalization_requests) == 2
    assert run.validation_attempts[0].succeeded is True
    assert run.output is not None

    assert len(client.requests) == 6
    assert client.requests[0].reasoning is not None
    assert client.requests[0].reasoning.effort == "high"
    assert "File index" in client.requests[0].messages[-1].content
    assert any(
        message.role == "tool" and message.tool_call_id == "list"
        for message in client.requests[1].messages
    )
    assert "Latest structured tool results" in (
        client.requests[1].messages[-1].content or ""
    )
    assert "Remaining budgets" in (client.requests[1].messages[-1].content or "")
    assert "uninspected_evidence_path" in (
        client.requests[3].messages[-1].content or ""
    )
    assert client.requests[-1].tools == []
    assert client.output_types[-1] is ContextPlan


def test_tool_calls_execute_in_response_order_and_keep_conversation(
    context_with_repo: tuple[Path, BridgerToolContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, context = context_with_repo
    executor = DiscoveryToolExecutor(context)
    executed: list[str] = []
    original_execute = executor.execute

    def record_execution(request):
        executed.append(request.name)
        return original_execute(request)

    monkeypatch.setattr(executor, "execute", record_execution)
    client = DummyLLMClient(
        [
            tool_response(
                LLMToolCall(
                    id="search",
                    name="search_with_context",
                    arguments={"query": "return", "path_prefix": "src"},
                ),
                read_app_ranges_call(),
            ),
            tool_response(finalization_call()),
            synthesis_response(valid_plan()),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        executor=executor,
        limits=DiscoveryBudgetLimits(
            model_turns=3, consecutive_no_progress_threshold=10
        ),
    )

    run = asyncio.run(builder.build(run_id="run-order"))

    assert run.status.value == "completed"
    assert executed == ["search_with_context", "read_file_ranges"]
    tool_messages = [
        message.tool_call_id
        for message in client.requests[1].messages
        if message.role == "tool"
    ]
    assert tool_messages == ["search", "read"]


def test_prose_only_turns_stall_without_starting_synthesis(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    client = DummyLLMClient(
        [text_response("I am done."), text_response("Here is the final plan.")]
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=4, consecutive_no_progress_threshold=2
        ),
    )

    run = asyncio.run(builder.build(run_id="run-prose"))

    assert run.status.value == "stalled"
    assert len(client.requests) == 2
    assert all(output_type is None for output_type in client.output_types)
    assert not (root / ".bridger/artifacts/context-plan.json").exists()


def test_mixed_finalization_response_rejects_every_call_without_execution(
    context_with_repo: tuple[Path, BridgerToolContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, context = context_with_repo
    executor = DiscoveryToolExecutor(context)
    executed: list[str] = []
    original_execute = executor.execute

    def record_execution(request):
        executed.append(request.name)
        return original_execute(request)

    monkeypatch.setattr(executor, "execute", record_execution)
    client = DummyLLMClient(
        [
            tool_response(
                LLMToolCall(id="list", name="list_files", arguments={}),
                finalization_call(),
            ),
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call("grounded")),
            synthesis_response(valid_plan()),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        executor=executor,
        limits=DiscoveryBudgetLimits(
            model_turns=4, consecutive_no_progress_threshold=10
        ),
    )

    run = asyncio.run(builder.build(run_id="run-mixed"))

    assert run.status.value == "completed"
    assert executed == ["read_file_ranges"]
    assert len(run.finalization_requests) == 1


def test_model_preflight_preserves_the_synthesis_turn(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    client = DummyLLMClient([text_response("unused")])
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(model_turns=1),
    )

    run = asyncio.run(builder.build(run_id="run-model-budget"))

    assert run.status.value == "budget_exhausted"
    assert client.requests == []


def test_tool_preflight_prevents_handler_execution(
    context_with_repo: tuple[Path, BridgerToolContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, context = context_with_repo
    executor = DiscoveryToolExecutor(context)
    definition = executor.registry.get("read_file_ranges")
    assert definition is not None
    executor.registry._definitions["read_file_ranges"] = replace(
        definition,
        cost=ToolBudgetCost(file_reads=2, excerpts=1),
    )
    executed: list[str] = []
    monkeypatch.setattr(
        executor,
        "execute",
        lambda request: executed.append(request.name),
    )
    client = DummyLLMClient([tool_response(read_app_ranges_call())])
    builder = make_builder(
        root,
        context,
        client,
        executor=executor,
        limits=DiscoveryBudgetLimits(model_turns=2, file_reads=1),
    )

    run = asyncio.run(builder.build(run_id="run-tool-budget"))

    assert run.status.value == "budget_exhausted"
    assert executed == []


def test_duplicate_warning_reaches_a_later_investigation_prompt(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    repeated = LLMToolCall(
        id="search-1",
        name="search_with_context",
        arguments={"query": "return", "path_prefix": "src"},
    )
    client = DummyLLMClient(
        [
            tool_response(repeated),
            tool_response(repeated.model_copy(update={"id": "search-2"})),
            text_response("Continue investigating."),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=4,
            duplicate_call_threshold=3,
            consecutive_no_progress_threshold=2,
        ),
    )

    run = asyncio.run(builder.build(run_id="run-duplicate"))

    assert run.status.value == "stalled"
    assert "Duplicate tool call detected for search_with_context" in (
        client.requests[2].messages[-1].content or ""
    )


@pytest.mark.parametrize("existing_plan", [False, True])
def test_invalid_synthesis_never_creates_or_replaces_plan(
    context_with_repo: tuple[Path, BridgerToolContext],
    existing_plan: bool,
) -> None:
    root, context = context_with_repo
    destination = root / ".bridger/artifacts/context-plan.json"
    existing = json.dumps(
        valid_plan().model_dump(mode="json"), sort_keys=True, default=str
    ).encode()
    if existing_plan:
        destination.write_bytes(existing)
    client = DummyLLMClient(
        [
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call()),
            synthesis_response(valid_plan(line_end=99)),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=3, consecutive_no_progress_threshold=10
        ),
    )

    with pytest.raises(ContextPlanValidationError):
        asyncio.run(builder.build(run_id="run-invalid-synthesis"))

    if existing_plan:
        assert destination.read_bytes() == existing
    else:
        assert not destination.exists()
    run = read_run(root)
    assert run.status.value == "failed"
    assert run.validation_attempts[-1].succeeded is False


def test_missing_prerequisite_fails_before_first_model_call(
    context_with_repo: tuple[Path, BridgerToolContext],
    tmp_path: Path,
) -> None:
    _, context = context_with_repo
    missing_root = tmp_path / "missing"
    client = DummyLLMClient([text_response("unused")])
    builder = make_builder(
        missing_root,
        context,
        client,
        artifact_store=ArtifactStore(missing_root),
        limits=DiscoveryBudgetLimits(model_turns=2),
    )

    with pytest.raises(BridgerToolError, match="file-index.json"):
        asyncio.run(builder.build(run_id="run-missing"))

    assert client.requests == []


def test_provider_failure_and_interruption_leave_valid_run_snapshots(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    failed_client = DummyLLMClient([RuntimeError("provider unavailable")])
    failed_builder = make_builder(
        root,
        context,
        failed_client,
        limits=DiscoveryBudgetLimits(model_turns=2),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(failed_builder.build(run_id="run-provider-failure"))

    assert read_run(root).status.value == "failed"

    interrupted_client = DummyLLMClient([asyncio.CancelledError()])
    interrupted_builder = make_builder(
        root,
        context,
        interrupted_client,
        limits=DiscoveryBudgetLimits(model_turns=2),
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(interrupted_builder.build(run_id="run-interrupted"))

    assert read_run(root).status.value == "interrupted"


def test_tool_failure_is_persisted_before_stall(
    context_with_repo: tuple[Path, BridgerToolContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, context = context_with_repo

    def fail_read(*args, **kwargs):
        raise RuntimeError("read failed")

    monkeypatch.setattr(context.file_read, "read_ranges", fail_read)
    client = DummyLLMClient([tool_response(read_app_ranges_call())])
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=3, consecutive_no_progress_threshold=1
        ),
    )

    run = asyncio.run(builder.build(run_id="run-tool-failure"))

    assert run.status.value == "stalled"
    assert read_run(root) == run
    assert run.tool_call_count == 1
    assert run.output is None


def test_artifact_write_failure_does_not_report_completion(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo

    def fail_write(*args, **kwargs):
        raise OSError("disk unavailable")

    client = DummyLLMClient(
        [
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call()),
            synthesis_response(valid_plan()),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        writer=fail_write,
        limits=DiscoveryBudgetLimits(
            model_turns=3, consecutive_no_progress_threshold=10
        ),
    )

    with pytest.raises(OSError, match="disk unavailable"):
        asyncio.run(builder.build(run_id="run-write-failure"))

    run = read_run(root)
    assert run.status.value == "failed"
    assert run.output is None
    assert run.phase.value == "writing"


def test_synthesis_and_repair_reuse_persisted_manifest(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    client = DummyLLMClient(
        [
            tool_response(read_app_ranges_call()),
            tool_response(finalization_call()),
            synthesis_response(valid_plan(line_end=99)),
            synthesis_response(valid_plan()),
        ]
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=4, consecutive_no_progress_threshold=10
        ),
    )

    run = asyncio.run(builder.build(run_id="run-manifest-repair"))

    assert run.synthesis_input_manifest is not None
    manifest_id = run.synthesis_input_manifest.manifest_id
    synthesis_text = client.requests[-2].messages[-1].content or ""
    repair_text = client.requests[-1].messages[-1].content or ""
    assert manifest_id in synthesis_text
    assert manifest_id in repair_text
    assert run.working_state_checksum is not None
    assert (root / ".bridger/artifacts/context-plan-working-state.json").is_file()
