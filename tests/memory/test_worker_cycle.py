"""Focused Stage 4 worker-cycle contract tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import bridger.memory.runtime.worker_cycle as worker_cycle
from bridger.contracts.files import (
    FileDisposition,
    FileRecord,
    SourceReadResult,
)
from bridger.contracts.memory.core import (
    ActivationMode,
    CompletionItemState,
    CompletionObligationDefinition,
    CompletionStatus,
    ExecutionBudget,
    FindingOrigin,
    FindingRef,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    ObligationApplicability,
    SourceBinding,
    TargetActivation,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.hydration import (
    CompletionObligationView,
    GraphOverview,
    PermissionProfile,
    RemainingExecutionBudget,
    TargetContractView,
    WorkerContext,
    WorkerContextMode,
    WorkerCycleFocus,
    WorkerCycleFocusKind,
    WorkerProfile,
)
from bridger.contracts.memory.worker_cycle import (
    EvidenceKind,
    EvidenceReference,
    FileEvidenceLocator,
    OpenQuestion,
)
from bridger.contracts.navigation import FileOverview
from bridger.llm.errors import LLMConnectionError
from bridger.llm.models import (
    LLMCompactedContext,
    LLMCompactionResult,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolResult,
    LLMUsage,
)
from bridger.llm.providers.openai import _tool_to_openai
from bridger.llm.testing import DummyLLMClient
from bridger.memory import (
    CompletionStateUpdater,
    ContextWindowManager,
    EvidenceRecorder,
    FleetExecutionCoordinator,
    ProgressUpdater,
    TargetWorkspace,
    WorkerCycleOutcome,
    WorkerCyclePreflightError,
    WorkerRunner,
    WorkerRuntimeLimits,
    WorkerToolRuntime,
    run_worker_cycle,
)
from bridger.memory.runtime.worker_tools import (
    REPOSITORY_TOOL_IDS,
    WORKER_TOOL_IDS,
)
from bridger.navigation.tools import NAVIGATION_TOOL_IDS

_SOURCE = SourceBinding(
    repository_id="repository-1",
    repository_revision="a" * 40,
    graph_snapshot_id="snapshot-1",
)
_ALL_LOCAL_TOOLS = (
    "list_target_artifacts",
    "read_target_artifact",
    "write_target_artifact",
    "edit_target_artifact_range",
    "delete_target_artifact",
    "move_target_artifact",
    "record_evidence",
    "update_completion_item",
    "update_progress",
)
_GRAPH_OVERVIEW = GraphOverview(
    graph_snapshot_id="snapshot-1",
    graph_contract_version="bridger.graph.v1",
    build_mode="full",
    node_count=1,
    edge_count=0,
    hyperedge_count=0,
    community_count=1,
    central_nodes=(),
    central_nodes_truncated=False,
    surprising_connections=(),
    surprising_connections_truncated=False,
    suggested_questions=(),
    suggested_questions_truncated=False,
)


def test_complete_memory_worker_tool_surface_is_openai_strict_compatible(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, allowed_tools=WORKER_TOOL_IDS)
    runner = fixture.runner([])

    emitted_tools = [
        _tool_to_openai(definition) for definition in runner._tool_definitions
    ]

    assert {tool["name"] for tool in emitted_tools} >= set(WORKER_TOOL_IDS)
    assert REPOSITORY_TOOL_IDS == NAVIGATION_TOOL_IDS
    assert {tool["name"] for tool in emitted_tools} >= set(NAVIGATION_TOOL_IDS)
    assert all(tool["strict"] is True for tool in emitted_tools)
    for tool in emitted_tools:
        _assert_no_empty_schema_nodes(tool["parameters"])


def _assert_no_empty_schema_nodes(value: object) -> None:
    _assert_schema_node(value, is_schema_node=True)


def _assert_schema_node(value: object, *, is_schema_node: bool) -> None:
    if isinstance(value, dict):
        if is_schema_node:
            assert value, "OpenAI schema contains an unconstrained empty object"
        for key, child in value.items():
            _assert_schema_node(
                child,
                is_schema_node=key not in {"properties", "$defs"},
            )
    elif isinstance(value, list):
        for child in value:
            _assert_schema_node(child, is_schema_node=True)


def test_assembled_worker_request_combines_graph_strategy_context_and_tools(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, allowed_tools=WORKER_TOOL_IDS)
    shared_instructions = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "bridger"
        / "memory"
        / "prompts"
        / "worker"
        / "system.md"
    ).read_text(encoding="utf-8")
    fixture.context = fixture.context.model_copy(
        update={"shared_worker_instructions": shared_instructions}
    )
    client = DummyLLMClient([_response(_call("finalize", "request_finalization", {}))])

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    request = client.requests[0]
    assert request.instructions is not None
    assert "Graph-guided navigation" in request.instructions
    assert "Repository graph overview" in request.instructions
    assert '"node_count":1' in request.instructions
    assert {tool.name for tool in request.tools} >= set(NAVIGATION_TOOL_IDS)


class CountingContextWindowManager(ContextWindowManager):
    """Context manager spy that retains the real counting behavior."""

    def __init__(self, profile: WorkerProfile) -> None:
        super().__init__(profile)
        self.inspections = 0

    def inspect_request(
        self,
        serialized_request_input: str,
        *,
        provider_framing_tokens: int = 0,
        reserved_response_tokens: int | None = None,
    ) -> Any:
        self.inspections += 1
        return super().inspect_request(
            serialized_request_input,
            provider_framing_tokens=provider_framing_tokens,
            reserved_response_tokens=reserved_response_tokens,
        )


class FakeNavigator:
    """Narrow deterministic fake for the existing Layer 6 authority."""

    source_identity = (
        _SOURCE.repository_id,
        _SOURCE.repository_revision,
        _SOURCE.graph_snapshot_id,
        None,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def search_repository(self, query: str, **_: object) -> list[dict[str, str]]:
        self.calls.append(("search_repository", query))
        return [{"kind": "file", "path": "service.py", "query": query}]

    def get_file_overview(self, path: str, **_: object) -> FileOverview:
        self.calls.append(("get_file_overview", path))
        return FileOverview(
            file=FileRecord(
                path=path,
                git_object_id="b" * 40,
                size_bytes=20,
                content_type="source",
                language="python",
                disposition=FileDisposition(
                    read_mode="full",
                    processing_mode="extract",
                ),
            ),
            symbol_ids=["symbol-1"],
            graph_node_ids=["node-1"],
            symbols_truncated=False,
            graph_nodes_truncated=False,
        )

    def read_file_ranges(
        self,
        path: str,
        ranges: list[tuple[int, int]],
        **_: object,
    ) -> list[SourceReadResult]:
        self.calls.append(("read_file_ranges", (path, ranges)))
        start, end = ranges[0]
        return [
            SourceReadResult(
                path=path,
                revision=_SOURCE.repository_revision,
                content="source line",
                start_line=start,
                end_line=end,
                content_digest="c" * 64,
                encoding="utf-8",
                truncated=False,
            )
        ]

    def read_symbol_excerpt(self, symbol_id: str, **_: object) -> SourceReadResult:
        self.calls.append(("read_symbol_excerpt", symbol_id))
        return SourceReadResult(
            path="service.py",
            revision=_SOURCE.repository_revision,
            content="def service(): pass",
            start_line=1,
            end_line=1,
            content_digest="d" * 64,
            encoding="utf-8",
            truncated=False,
        )

    def get_graph_entity(
        self, target_type: str, target_ref: object, **_: object
    ) -> dict[str, object]:
        self.calls.append(("get_graph_entity", (target_type, target_ref)))
        return {"target_type": target_type, "target_ref": target_ref}


@dataclass
class WorkerFixture:
    fleet_spec: MemoryFleetSpec
    fleet_state: FleetRunState
    target_spec: TargetTaskSpec
    target_state: TargetTaskState
    completion_state: TargetCompletionState
    definition: TargetDefinition
    profile: WorkerProfile
    permissions: PermissionProfile
    context: WorkerContext
    manager: CountingContextWindowManager
    navigator: FakeNavigator
    evidence: dict[str, EvidenceReference]
    questions: dict[str, OpenQuestion]

    def runner(
        self,
        responses: list[LLMResponse | BaseException],
        *,
        client: DummyLLMClient | None = None,
        limits: WorkerRuntimeLimits | None = None,
    ) -> WorkerRunner:
        workspace = TargetWorkspace(self.target_spec, self.target_state)
        evidence_recorder = EvidenceRecorder(
            self.target_spec,
            self.target_state,
            self.navigator,  # type: ignore[arg-type]
            self.evidence,
        )
        completion_updater = CompletionStateUpdater(
            self.target_spec,
            self.target_state,
            self.completion_state,
            self.definition,
            self.evidence,
        )
        progress_updater = ProgressUpdater(
            self.target_spec,
            self.target_state,
            self.questions,
        )
        tools = WorkerToolRuntime(
            self.context,
            self.permissions,
            self.navigator,  # type: ignore[arg-type]
            workspace,
            evidence_recorder,
            completion_updater,
            progress_updater,
        )
        return WorkerRunner(
            fleet_spec=self.fleet_spec,
            fleet_state=self.fleet_state,
            target_spec=self.target_spec,
            target_state=self.target_state,
            completion_state=self.completion_state,
            context=self.context,
            worker_profile=self.profile,
            context_window_manager=self.manager,
            llm_client=client or DummyLLMClient(responses),  # type: ignore[arg-type]
            tools=tools,
            evidence=self.evidence,
            questions=self.questions,
            coordinator=FleetExecutionCoordinator(),
            limits=limits,
        )


def test_worker_cycle_runs_multiple_turns_and_charges_both_scopes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner(
        [
            _response(
                _call(
                    "write-1",
                    "write_target_artifact",
                    {"path": "architecture.md", "content": "# Architecture\n"},
                ),
                _call(
                    "completion-1",
                    "update_completion_item",
                    {
                        "obligation_id": "describe-runtime",
                        "status": "covered",
                        "resolution_note": "Runtime structure documented.",
                        "evidence_refs": [],
                    },
                ),
                usage=LLMUsage(input_tokens=100, output_tokens=20),
            ),
            _response(
                _call("final-1", "request_finalization", {}),
                usage=LLMUsage(input_tokens=120, output_tokens=5),
            ),
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert fixture.target_state.phase is TargetPhase.WORKING
    assert fixture.target_state.usage.cycles == 1
    assert fixture.target_state.usage.model_calls == 2
    assert fixture.target_state.usage.tool_calls == 2
    assert fixture.target_state.usage.input_tokens == 220
    assert fixture.target_state.usage.output_tokens == 25
    assert fixture.fleet_state.usage == fixture.target_state.usage
    assert fixture.completion_state.items[0].status is CompletionStatus.COVERED
    assert (tmp_path / "workspace" / "architecture.md").is_file()
    assert fixture.manager.inspections == 2


def test_standalone_yield_ends_only_the_current_cycle(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    client = DummyLLMClient([_response(_call("yield", "yield_cycle", {}))])

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    assert fixture.target_state.usage.cycles == 1
    assert fixture.target_state.usage.model_calls == 1
    assert fixture.target_state.usage.tool_calls == 0
    assert {tool.name for tool in client.requests[0].tools} >= {
        "yield_cycle",
        "request_finalization",
    }


def test_yield_requires_no_arguments(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    client = DummyLLMClient(
        [
            _response(_call("invalid-yield", "yield_cycle", {"reason": "done"})),
            _response(_call("valid-yield", "yield_cycle", {})),
        ]
    )

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    assert fixture.target_state.usage.model_calls == 2
    assert fixture.target_state.usage.tool_calls == 0
    assert "yield_cycle must have no arguments" in client.requests[1].model_dump_json()


def test_yield_preserves_all_durable_progress_domains(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner(
        [
            _response(
                _call(
                    "evidence",
                    "record_evidence",
                    {"kind": "file", "locator": {"path": "service.py"}},
                )
            ),
            _response(
                _call(
                    "artifact",
                    "write_target_artifact",
                    {"path": "progress.md", "content": "Durable progress."},
                ),
                _call(
                    "completion",
                    "update_completion_item",
                    {
                        "obligation_id": "describe-runtime",
                        "status": "covered",
                        "resolution_note": "The bounded obligation is resolved.",
                        "evidence_refs": [],
                    },
                ),
                _call(
                    "progress",
                    "update_progress",
                    {"working_summary": "Continue from the next obligation."},
                ),
            ),
            _response(_call("yield", "yield_cycle", {})),
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    assert fixture.target_state.artifact_refs[0].relative_path == "progress.md"
    assert len(fixture.target_state.evidence_refs) == 1
    assert fixture.completion_state.items[0].status is CompletionStatus.COVERED
    assert fixture.target_state.working_summary == "Continue from the next obligation."


def test_mixed_yield_executes_operations_and_requires_later_standalone_yield(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    client = DummyLLMClient(
        [
            _response(
                _call(
                    "write",
                    "write_target_artifact",
                    {"path": "progress.md", "content": "Persisted progress."},
                ),
                _call("mixed-yield", "yield_cycle", {}),
            ),
            _response(_call("standalone-yield", "yield_cycle", {})),
        ]
    )

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    assert fixture.target_state.usage.tool_calls == 1
    assert (tmp_path / "workspace" / "progress.md").read_text() == (
        "Persisted progress."
    )
    assert "protocol_error" in client.requests[1].model_dump_json()


def test_yield_and_finalization_together_succeed_as_neither_control(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    client = DummyLLMClient(
        [
            _response(
                _call("yield", "yield_cycle", {}),
                _call("final", "request_finalization", {}),
            ),
            _response(_call("yield-alone", "yield_cycle", {})),
        ]
    )

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert fixture.target_state.phase is TargetPhase.SCHEDULED
    second_request = client.requests[1].model_dump_json()
    assert second_request.count("cannot be requested together") == 2


def test_response_ids_continue_only_with_incremental_tool_outputs(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first = _response(_call("list", "list_target_artifacts", {})).model_copy(
        update={"response_id": "response-a"}
    )
    second = _response(_call("yield", "yield_cycle", {})).model_copy(
        update={"response_id": "response-b"}
    )
    client = DummyLLMClient([first, second])

    outcome = asyncio.run(fixture.runner([], client=client).run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    initial, continued = client.requests
    assert initial.continuation_ref is None
    assert initial.messages == []
    assert initial.store is True
    assert initial.reasoning is not None
    assert initial.reasoning.effort == "xhigh"
    assert initial.reasoning.context == "all_turns"
    assert continued.continuation_ref == "response-a"
    assert [message.role for message in continued.messages] == ["tool"]
    assert continued.instructions is not None
    assert continued.instructions.startswith(initial.instructions or "")
    assert "Current execution-state overlay" in continued.instructions
    assert initial.prompt_cache is not None
    assert continued.prompt_cache == initial.prompt_cache
    final_breakpoint = initial.prompt_cache.instruction_breakpoints[-1]
    assert initial.instructions is not None
    assert continued.instructions[:final_breakpoint] == initial.instructions
    assert continued.instructions[final_breakpoint:].startswith(
        "\n\nCurrent execution-state overlay"
    )
    assert [tool.model_dump(mode="json") for tool in continued.tools] == [
        tool.model_dump(mode="json") for tool in initial.tools
    ]
    assert client.compaction_requests == []
    assert "response-a" not in fixture.target_state.model_dump_json()
    assert "response-b" not in fixture.target_state.model_dump_json()


def test_prompt_cache_identity_and_prefix_levels_are_deterministic(
    tmp_path: Path,
) -> None:
    base_root = tmp_path / "base"
    cycle_root = tmp_path / "cycle"
    target_root = tmp_path / "target"
    base_root.mkdir()
    cycle_root.mkdir()
    target_root.mkdir()

    base = _fixture(base_root)
    base_client = DummyLLMClient(
        [_response(_call("base-final", "request_finalization", {}))]
    )
    asyncio.run(base.runner([], client=base_client).run())

    changed_cycle = _fixture(cycle_root)
    changed_cycle.context = changed_cycle.context.model_copy(
        update={
            "cycle_focus": WorkerCycleFocus(
                kind=WorkerCycleFocusKind.OBLIGATION,
                obligation_id="another-obligation",
            )
        }
    )
    cycle_client = DummyLLMClient(
        [_response(_call("cycle-final", "request_finalization", {}))]
    )
    asyncio.run(changed_cycle.runner([], client=cycle_client).run())

    changed_target = _fixture(target_root)
    changed_target.target_spec = changed_target.target_spec.model_copy(
        update={"target_id": "security"}
    )
    changed_target.definition = changed_target.definition.model_copy(
        update={"target_id": "security"}
    )
    changed_target.context = changed_target.context.model_copy(
        update={
            "target_worker_instructions": "Investigate and document security.",
            "target_contract": changed_target.context.target_contract.model_copy(
                update={"target_id": "security"}
            ),
        }
    )
    target_client = DummyLLMClient(
        [_response(_call("target-final", "request_finalization", {}))]
    )
    asyncio.run(changed_target.runner([], client=target_client).run())

    base_request = base_client.requests[0]
    cycle_request = cycle_client.requests[0]
    target_request = target_client.requests[0]
    assert base_request.prompt_cache is not None
    assert cycle_request.prompt_cache is not None
    assert target_request.prompt_cache is not None
    assert base_request.prompt_cache.key == cycle_request.prompt_cache.key
    assert base_request.prompt_cache.key != target_request.prompt_cache.key

    base_sections = _prompt_cache_sections(base_request)
    cycle_sections = _prompt_cache_sections(cycle_request)
    target_sections = _prompt_cache_sections(target_request)
    assert base_sections[:2] == cycle_sections[:2]
    assert base_sections[2] != cycle_sections[2]
    assert base_sections[0] == target_sections[0]
    assert base_sections[1] != target_sections[1]


def test_compaction_resets_the_chain_and_can_repeat_with_exact_recent_replay(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.target_spec = fixture.target_spec.model_copy(
        update={
            "budget": fixture.target_spec.budget.model_copy(
                update={"max_input_tokens": 500_000}
            )
        }
    )
    first = _response(
        _call(
            "summary",
            "update_progress",
            {"working_summary": "Authoritative progress after cycle work."},
        ),
        usage=LLMUsage(input_tokens=74_000, output_tokens=1_000),
    ).model_copy(update={"response_id": "response-a"})
    second = _response(
        _call("list", "list_target_artifacts", {}),
        usage=LLMUsage(input_tokens=74_000, output_tokens=1_000),
    ).model_copy(update={"response_id": "response-b"})
    third = _response(
        _call("yield", "yield_cycle", {}),
        usage=LLMUsage(input_tokens=100, output_tokens=10),
    ).model_copy(update={"response_id": "response-c"})
    compacted_a = LLMCompactionResult(
        context=LLMCompactedContext(
            provider="openai",
            payload=[
                {
                    "type": "compaction",
                    "encrypted_content": "opaque-a",
                }
            ],
        ),
        usage=LLMUsage(input_tokens=500, output_tokens=100),
    )
    compacted_b = LLMCompactionResult(
        context=LLMCompactedContext(
            provider="openai",
            payload=[
                {
                    "type": "compaction",
                    "encrypted_content": "opaque-b",
                }
            ],
        ),
        usage=LLMUsage(input_tokens=600, output_tokens=120),
    )
    client = DummyLLMClient(
        [first, second, third],
        compaction_outcomes=[compacted_a, compacted_b],
    )

    runner = fixture.runner(
        [],
        client=client,
        limits=WorkerRuntimeLimits(active_context_soft_limit_tokens=32_000),
    )
    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert [request.continuation_ref for request in client.compaction_requests] == [
        "response-a",
        "response-b",
    ]
    assert all(
        "Authoritative progress after cycle work." in request.instructions
        for request in client.compaction_requests
    )
    first_post_compaction, second_post_compaction = client.requests[1:]
    assert first_post_compaction.continuation_ref is None
    assert first_post_compaction.compacted_context == compacted_a.context
    assert [message.role for message in first_post_compaction.messages] == [
        "assistant",
        "tool",
    ]
    assert second_post_compaction.continuation_ref is None
    assert second_post_compaction.compacted_context == compacted_b.context
    assert [message.role for message in second_post_compaction.messages] == [
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    assert fixture.target_state.usage.model_calls == 5
    assert fixture.fleet_state.usage.model_calls == 5
    assert fixture.target_state.usage.input_tokens == 149_200
    assert fixture.target_state.usage.output_tokens == 2_230
    assert runner._continuation_ref is None
    assert runner._compacted_context is None


def test_compaction_failure_interrupts_without_discarding_the_chain(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first = _response(
        _call("list", "list_target_artifacts", {}),
        usage=LLMUsage(input_tokens=74_000, output_tokens=1_000),
    ).model_copy(update={"response_id": "response-a"})
    failure = LLMConnectionError("compaction unavailable", retryable=True)
    client = DummyLLMClient([first], compaction_outcomes=[failure])
    runner = fixture.runner(
        [],
        client=client,
        limits=WorkerRuntimeLimits(active_context_soft_limit_tokens=32_000),
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
    assert runner.last_runtime_error is failure
    assert fixture.target_state.phase is TargetPhase.WORKING
    assert fixture.target_state.usage.model_calls == 2
    assert client.compaction_requests[0].continuation_ref == "response-a"


def test_compaction_uses_the_active_working_limit_not_provider_capacity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first = _response(
        _call("list", "list_target_artifacts", {}),
        usage=LLMUsage(input_tokens=32_000, output_tokens=1_000),
    ).model_copy(update={"response_id": "response-a"})
    compacted = LLMCompactionResult(
        context=LLMCompactedContext(
            provider="openai",
            payload=[{"type": "compaction", "encrypted_content": "opaque"}],
        ),
        usage=LLMUsage(input_tokens=100, output_tokens=10),
    )
    client = DummyLLMClient(
        [first, _response(_call("yield", "yield_cycle", {}))],
        compaction_outcomes=[compacted],
    )

    outcome = asyncio.run(
        fixture.runner(
            [],
            client=client,
            limits=WorkerRuntimeLimits(active_context_soft_limit_tokens=32_000),
        ).run()
    )

    assert outcome is WorkerCycleOutcome.CYCLE_YIELDED
    assert client.compaction_requests[0].continuation_ref == "response-a"
    assert client.compaction_requests[0].messages[0].tool_call_id == "list"
    assert fixture.profile.model_context_window_tokens == 100_000


def test_generation_context_capacity_is_not_classified_as_budget_exhaustion(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner([])

    with pytest.raises(worker_cycle._ContextCapacityStop):
        runner._maximum_output_tokens(fixture.profile.model_context_window_tokens)


def test_pending_tool_results_are_aggregate_bounded_for_compaction(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.profile = fixture.profile.model_copy(
        update={"model_context_window_tokens": 40_000}
    )
    fixture.manager = CountingContextWindowManager(fixture.profile)
    runner = fixture.runner([])
    runner._continuation_ref = "response-a"
    runner._latest_usage = LLMUsage(input_tokens=35_000, output_tokens=1_000)
    results = [
        LLMToolResult(
            call_id=f"tool-{index}",
            name="list_target_artifacts",
            output={"body": "x" * 32_000},
        )
        for index in range(5)
    ]

    bounded = runner._bound_pending_tool_results(results)
    pending_tokens = fixture.manager.count_text(
        worker_cycle._serialize_messages([result.as_message() for result in bounded])
    )

    assert pending_tokens <= 3_744
    assert any(
        isinstance(result.output, dict) and result.output.get("truncated")
        for result in bounded
    )


def test_runtime_composes_stage4_directly_from_hydrated_authorities(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    outcome = asyncio.run(
        run_worker_cycle(
            fleet_spec=fixture.fleet_spec,
            fleet_state=fixture.fleet_state,
            target_spec=fixture.target_spec,
            target_state=fixture.target_state,
            completion_state=fixture.completion_state,
            target_definition=fixture.definition,
            context=fixture.context,
            worker_profile=fixture.profile,
            permission_profile=fixture.permissions,
            context_window_manager=fixture.manager,
            llm_client=DummyLLMClient(
                [_response(_call("final", "request_finalization", {}))]
            ),
            navigator=fixture.navigator,  # type: ignore[arg-type]
            evidence=fixture.evidence,
            questions=fixture.questions,
            coordinator=FleetExecutionCoordinator(),
        )
    )

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert fixture.target_state.phase is TargetPhase.WORKING
    assert fixture.target_state.usage.cycles == 1


def test_failed_preflight_does_not_enter_working_or_consume_cycle(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.profile = fixture.profile.model_copy(
        update={"provider_input_hard_cap_tokens": 1}
    )
    fixture.manager = CountingContextWindowManager(fixture.profile)
    fixture.context = fixture.context.model_copy(
        update={"worker_profile_id": fixture.profile.profile_id}
    )
    runner = fixture.runner([_response(_call("final", "request_finalization", {}))])

    with pytest.raises(WorkerCyclePreflightError, match="provider-input hard cap"):
        asyncio.run(runner.run())

    assert fixture.target_state.phase is TargetPhase.HYDRATING
    assert fixture.target_state.usage.cycles == 0
    assert fixture.fleet_state.usage.cycles == 0


def test_target_budget_preflight_exhausts_without_charging_cycle(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    constrained_budget = fixture.target_spec.budget.model_copy(
        update={"max_input_tokens": 1}
    )
    fixture.target_spec = fixture.target_spec.model_copy(
        update={"budget": constrained_budget}
    )
    runner = fixture.runner([_response(_call("final", "request_finalization", {}))])

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED
    assert fixture.target_state.phase is TargetPhase.EXHAUSTED
    assert fixture.target_state.usage.cycles == 0
    assert fixture.target_state.usage.model_calls == 0
    assert fixture.fleet_state.usage.cycles == 0


def test_multi_tool_batch_is_rejected_whole_before_any_dispatch(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, max_tool_calls=1)
    runner = fixture.runner(
        [
            _response(
                _call(
                    "write-a",
                    "write_target_artifact",
                    {"path": "a.md", "content": "A"},
                ),
                _call(
                    "write-b",
                    "write_target_artifact",
                    {"path": "b.md", "content": "B"},
                ),
            )
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED
    assert fixture.target_state.phase is TargetPhase.EXHAUSTED
    assert fixture.target_state.usage.tool_calls == 0
    assert fixture.target_state.artifact_refs == []
    assert not (tmp_path / "workspace" / "a.md").exists()
    assert fixture.fleet_state.usage.tool_calls == 0


def test_mixed_finalization_executes_operations_but_requires_later_standalone_call(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner(
        [
            _response(
                _call(
                    "write",
                    "write_target_artifact",
                    {"path": "candidate.md", "content": "Candidate"},
                ),
                _call("mixed-final", "request_finalization", {}),
            ),
            _response(_call("standalone-final", "request_finalization", {})),
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert fixture.target_state.usage.model_calls == 2
    assert fixture.target_state.usage.tool_calls == 1
    assert (tmp_path / "workspace" / "candidate.md").read_text() == "Candidate"


def test_multi_tool_operations_execute_sequentially_in_model_order(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner(
        [
            _response(
                _call(
                    "create",
                    "write_target_artifact",
                    {"path": "ordered.md", "content": "first\nsecond\n"},
                ),
                _call(
                    "edit",
                    "edit_target_artifact_range",
                    {
                        "path": "ordered.md",
                        "expected_revision": 1,
                        "start_line": 2,
                        "end_line": 2,
                        "replacement": "changed\n",
                    },
                ),
            ),
            _response(_call("final", "request_finalization", {})),
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert fixture.target_state.artifact_refs[0].revision == 2
    assert (tmp_path / "workspace" / "ordered.md").read_text() == "first\nchanged\n"


def test_execution_overlay_replaces_prior_state_and_tool_working_set_is_bounded(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    client = DummyLLMClient(
        [
            _response(
                _call(
                    "summary-one",
                    "update_progress",
                    {"working_summary": "summary one"},
                )
            ),
            _response(
                _call(
                    "summary-two",
                    "update_progress",
                    {"working_summary": "summary two"},
                )
            ),
            *[
                _response(
                    _call(
                        f"list-{index}",
                        "list_target_artifacts",
                        {},
                    )
                )
                for index in range(4)
            ],
            _response(_call("final", "request_finalization", {})),
        ]
    )
    runner = fixture.runner(
        [],
        client=client,
        limits=WorkerRuntimeLimits(tool_context_soft_tokens=1),
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    latest_overlay = client.requests[2].instructions
    assert latest_overlay is not None
    assert "summary two" in latest_overlay
    assert "summary one" not in latest_overlay
    final_request = client.requests[-1]
    assistant_batches = [
        message for message in final_request.messages if message.role == "assistant"
    ]
    assert len(assistant_batches) == 3
    assert fixture.manager.inspections == len(client.requests)


def test_execution_permission_is_enforced_after_tool_exposure(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, allowed_tools=("list_target_artifacts",))
    client = DummyLLMClient(
        [
            _response(
                _call(
                    "forbidden",
                    "write_target_artifact",
                    {"path": "forbidden.md", "content": "No"},
                )
            ),
            _response(_call("final", "request_finalization", {})),
        ]
    )
    runner = fixture.runner([], client=client)

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert {tool.name for tool in client.requests[0].tools} == {
        "list_target_artifacts",
        "yield_cycle",
        "request_finalization",
    }
    assert "permission_denied" in client.requests[1].model_dump_json()
    assert fixture.target_state.usage.tool_calls == 1
    assert not (tmp_path / "workspace" / "forbidden.md").exists()


def test_workspace_confinement_and_optimistic_revisions(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.target_state.phase = TargetPhase.WORKING
    workspace = TargetWorkspace(fixture.target_spec, fixture.target_state)

    first = workspace.write_target_artifact("notes.md", "one\ntwo\n")
    second = workspace.edit_target_artifact_range(
        "notes.md",
        expected_revision=first.revision,
        start_line=2,
        end_line=2,
        replacement="changed\n",
    )

    assert first.revision == 1
    assert second.revision == 2
    assert second.artifact_id == first.artifact_id
    assert (tmp_path / "workspace" / "notes.md").read_text() == "one\nchanged\n"
    with pytest.raises(ValueError, match="stale expected_revision"):
        workspace.write_target_artifact(
            "notes.md", "stale", expected_revision=first.revision
        )
    with pytest.raises(ValueError, match="target-relative Markdown"):
        workspace.write_target_artifact("../escape.md", "no")
    with pytest.raises(ValueError, match="target-relative Markdown"):
        workspace.write_target_artifact("candidate.txt", "no")
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (tmp_path / "workspace" / "linked.md").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        workspace.write_target_artifact("linked.md", "no")


def test_evidence_completion_and_progress_services_keep_authority_local(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.target_state.phase = TargetPhase.WORKING
    recorder = EvidenceRecorder(
        fixture.target_spec,
        fixture.target_state,
        fixture.navigator,  # type: ignore[arg-type]
        fixture.evidence,
    )

    first = recorder.record_evidence(
        kind=EvidenceKind.FILE,
        locator=FileEvidenceLocator(path="service.py"),
    )
    repeated = recorder.record_evidence(
        kind=EvidenceKind.FILE,
        locator=FileEvidenceLocator(path="service.py"),
    )
    updater = CompletionStateUpdater(
        fixture.target_spec,
        fixture.target_state,
        fixture.completion_state,
        fixture.definition,
        fixture.evidence,
    )
    completed = updater.update_completion_item(
        "describe-runtime",
        CompletionStatus.COVERED,
        "Grounded in the runtime file.",
        [first.evidence_id],
    )
    progress = ProgressUpdater(
        fixture.target_spec,
        fixture.target_state,
        fixture.questions,
    )
    opened = progress.update_progress(
        working_summary="Inspect the failure path next.",
        questions_to_open=["Where is retry owned?"],
    )
    question_id = opened["open_question_refs"][0]  # type: ignore[index]
    progress.update_progress(question_refs_to_resolve=[question_id])

    assert first == repeated
    assert fixture.target_state.evidence_refs == [first.evidence_id]
    assert completed.evidence_refs == [first.evidence_id]
    assert fixture.target_state.working_summary == "Inspect the failure path next."
    assert fixture.target_state.open_question_refs == []
    assert fixture.questions[question_id].text == "Where is retry owned?"
    with pytest.raises(ValueError, match="conditional"):
        updater.update_completion_item(
            "describe-runtime",
            CompletionStatus.NOT_APPLICABLE,
            "Does not apply.",
            [],
        )
    with pytest.raises(ValueError, match="uninvestigated"):
        updater.update_completion_item(
            "describe-runtime",
            CompletionStatus.UNINVESTIGATED,
            "Reset.",
            [],
        )


def test_repair_cycle_and_runtime_interruption_account_actual_attempts(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, mode=WorkerContextMode.REPAIR)
    runner = fixture.runner([RuntimeError("provider unavailable")])

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
    assert fixture.target_state.phase is TargetPhase.WORKING
    assert fixture.target_state.usage.cycles == 1
    assert fixture.target_state.usage.repair_cycles == 1
    assert fixture.target_state.usage.model_calls == 1
    assert fixture.fleet_state.usage == fixture.target_state.usage


def test_provider_reported_retries_are_not_free_attempts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    response = _response(_call("final", "request_finalization", {})).model_copy(
        update={"retry_count": 2}
    )
    runner = fixture.runner([response])

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED
    assert fixture.target_state.usage.model_calls == 3
    assert fixture.fleet_state.usage.model_calls == 3


def test_exhausted_provider_retries_are_not_free_attempts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    error = LLMConnectionError("provider unavailable", retryable=True)
    error.attempt_count = 3
    runner = fixture.runner([error])

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
    assert fixture.target_state.usage.model_calls == 3
    assert fixture.fleet_state.usage.model_calls == 3


def test_missing_tool_calls_records_worker_protocol_interruption(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner(
        [
            LLMResponse(
                text="I cannot call a tool.",
                provider="test",
                model="gpt-test",
            )
        ]
    )

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
    assert runner.last_interruption is not None
    assert runner.last_interruption.category == "runtime"
    assert runner.last_interruption.operation == "worker-protocol"
    assert runner.last_interruption.message == "model response contained no tool calls"
    assert runner.last_interruption.retryable is True


def test_context_capacity_records_context_build_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runner = fixture.runner([_response(_call("list", "list_target_artifacts", {}))])

    def stop_for_capacity() -> tuple[LLMRequest, int, int]:
        raise worker_cycle._ContextCapacityStop(
            "minimum valid worker request cannot fit"
        )

    monkeypatch.setattr(runner, "_next_request", stop_for_capacity)
    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
    assert runner.last_interruption is not None
    assert runner.last_interruption.category == "context-capacity"
    assert runner.last_interruption.operation == "context-build"
    assert runner.last_interruption.message == "minimum valid worker request cannot fit"


def test_fleet_budget_stop_does_not_relabel_target_exhausted(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, fleet_max_model_calls=1)
    runner = fixture.runner([_response(_call("list", "list_target_artifacts", {}))])

    outcome = asyncio.run(runner.run())

    assert outcome is WorkerCycleOutcome.FLEET_BUDGET_STOP
    assert fixture.target_state.phase is TargetPhase.WORKING
    assert fixture.target_state.usage.model_calls == 1
    assert fixture.fleet_state.usage.model_calls == 1


def test_shared_fleet_output_reservation_cannot_be_double_spent(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    coordinator = FleetExecutionCoordinator()
    second_state = TargetTaskState(
        target_task_id="task-2",
        fleet_run_id="fleet-1",
        phase=TargetPhase.HYDRATING,
    )
    fleet_budget = fixture.fleet_spec.fleet_budget.model_copy(
        update={"max_output_tokens": 100}
    )

    async def reserve_concurrently() -> None:
        first = await coordinator.start_cycle_and_reserve_first_model_call(
            fleet_budget,
            fixture.fleet_state.usage,
            fixture.target_spec.budget,
            fixture.target_state,
            repair=False,
            input_tokens=100,
            requested_output_tokens=100,
        )
        with pytest.raises(RuntimeError, match="fleet budget"):
            await coordinator.start_cycle_and_reserve_first_model_call(
                fleet_budget,
                fixture.fleet_state.usage,
                fixture.target_spec.budget,
                second_state,
                repair=False,
                input_tokens=100,
                requested_output_tokens=100,
            )
        await coordinator.finish_model_call(
            first,
            fixture.target_state.usage,
            fixture.fleet_state.usage,
            LLMUsage(input_tokens=100, output_tokens=20),
        )

    asyncio.run(reserve_concurrently())

    assert second_state.phase is TargetPhase.HYDRATING
    assert second_state.usage.cycles == 0
    assert fixture.fleet_state.usage.cycles == 1


def _fixture(
    tmp_path: Path,
    *,
    max_tool_calls: int = 20,
    fleet_max_model_calls: int = 20,
    allowed_tools: tuple[str, ...] = _ALL_LOCAL_TOOLS,
    mode: WorkerContextMode = WorkerContextMode.INITIAL,
) -> WorkerFixture:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target_budget = ExecutionBudget(
        max_cycles=5,
        max_model_calls=20,
        max_tool_calls=max_tool_calls,
        max_repair_cycles=3,
        max_input_tokens=200_000,
        max_output_tokens=20_000,
    )
    fleet_budget = ExecutionBudget(
        max_cycles=20,
        max_model_calls=fleet_max_model_calls,
        max_tool_calls=100,
        max_repair_cycles=10,
        max_input_tokens=500_000,
        max_output_tokens=100_000,
    )
    fleet_spec = MemoryFleetSpec(
        fleet_run_id="fleet-1",
        source=_SOURCE,
        target_catalog_id="catalog-1",
        target_catalog_version="v1",
        target_ids=["architecture"],
        runtime_profile_id="runtime-v1",
        default_worker_profile_id="worker-v1",
        default_reviewer_profile_id="reviewer-v1",
        default_permission_profile_id="permissions-v1",
        fleet_budget=fleet_budget,
        default_target_budget=target_budget,
        runtime_root=str(tmp_path / "runtime"),
        output_root=str(tmp_path),
    )
    target_spec = TargetTaskSpec(
        target_task_id="task-1",
        fleet_run_id="fleet-1",
        target_id="architecture",
        target_contract_version="v1",
        source=_SOURCE,
        worker_profile_id="worker-v1",
        reviewer_profile_id="reviewer-v1",
        permission_profile_id="permissions-v1",
        budget=target_budget,
        target_workspace=str(workspace),
    )
    target_state = TargetTaskState(
        target_task_id="task-1",
        fleet_run_id="fleet-1",
        phase=TargetPhase.HYDRATING,
        open_finding_refs=(
            []
            if mode is WorkerContextMode.INITIAL
            else [
                FindingRef(
                    finding_id="finding-1",
                    origin=FindingOrigin.TARGET_REVIEW,
                )
            ]
        ),
    )
    fleet_state = FleetRunState(
        fleet_run_id="fleet-1",
        phase=FleetPhase.RUNNING,
        target_task_ids=["task-1"],
    )
    obligation = CompletionObligationDefinition(
        obligation_id="describe-runtime",
        description="Describe the runtime.",
        applicability=ObligationApplicability.ALWAYS,
    )
    definition = TargetDefinition(
        schema_version=1,
        target_id="architecture",
        target_contract_version="v1",
        activation=TargetActivation(mode=ActivationMode.ALWAYS),
        depends_on=[],
        canonical_question="How is the runtime structured?",
        purpose="Document architecture.",
        expected_abstraction="Runtime architecture.",
        always_relevant_scope=["runtime"],
        conditional_scope=[],
        exclusions=[],
        boundary_guidance=[],
        investigation_expectations=["Inspect source."],
        evidence_expectations=["Record source evidence."],
        completion_obligations=[obligation],
        output_quality_expectations=["Be precise."],
    )
    completion_state = TargetCompletionState(
        target_task_id="task-1",
        items=[CompletionItemState(obligation_id="describe-runtime")],
    )
    profile = WorkerProfile(
        profile_id="worker-v1",
        model="gpt-test",
        tokenizer_encoding="o200k_base",
        model_context_window_tokens=100_000,
        reserved_response_tokens=1_000,
    )
    permissions = PermissionProfile(
        profile_id="permissions-v1",
        allowed_tool_ids=allowed_tools,
    )
    context = WorkerContext(
        target_task_id="task-1",
        mode=mode,
        worker_profile_id="worker-v1",
        permission_profile_id="permissions-v1",
        allowed_tool_ids=allowed_tools,
        source=_SOURCE,
        graph_overview=_GRAPH_OVERVIEW,
        shared_worker_instructions="Use controlled tools for every action.",
        global_ownership_guidance=("Stay inside the assigned target.",),
        target_worker_instructions="Investigate and document the runtime.",
        target_contract=TargetContractView(
            target_id="architecture",
            target_contract_version="v1",
            canonical_question=definition.canonical_question,
            purpose=definition.purpose,
            expected_abstraction=definition.expected_abstraction,
            always_relevant_scope=("runtime",),
            conditional_scope=(),
            exclusions=(),
            boundary_guidance=(),
            investigation_expectations=("Inspect source.",),
            evidence_expectations=("Record source evidence.",),
            output_quality_expectations=("Be precise.",),
        ),
        cycle_focus=(
            WorkerCycleFocus(
                kind=WorkerCycleFocusKind.OBLIGATION,
                obligation_id="describe-runtime",
            )
            if mode is WorkerContextMode.INITIAL
            else WorkerCycleFocus(
                kind=WorkerCycleFocusKind.REPAIR_FINDINGS,
                finding_ids=("finding-1",),
            )
        ),
        completion_obligations=(
            CompletionObligationView(
                obligation_id="describe-runtime",
                description="Describe the runtime.",
                applicability=ObligationApplicability.ALWAYS,
                status=CompletionStatus.UNINVESTIGATED,
                evidence_refs=(),
            ),
        ),
        repair_findings=() if mode is WorkerContextMode.INITIAL else (_finding(),),
        open_questions=(),
        remaining_target_budget=RemainingExecutionBudget(
            cycles=5,
            model_calls=20,
            tool_calls=max_tool_calls,
            repair_cycles=3,
            input_tokens=200_000,
            output_tokens=20_000,
        ),
        candidate_artifacts=(),
    )
    return WorkerFixture(
        fleet_spec=fleet_spec,
        fleet_state=fleet_state,
        target_spec=target_spec,
        target_state=target_state,
        completion_state=completion_state,
        definition=definition,
        profile=profile,
        permissions=permissions,
        context=context,
        manager=CountingContextWindowManager(profile),
        navigator=FakeNavigator(),
        evidence={},
        questions={},
    )


def _prompt_cache_sections(request: LLMRequest) -> tuple[str, ...]:
    assert request.instructions is not None
    assert request.prompt_cache is not None
    sections: list[str] = []
    start = 0
    for end in request.prompt_cache.instruction_breakpoints:
        sections.append(request.instructions[start:end])
        start = end
    return tuple(sections)


def _finding() -> Any:
    from bridger.contracts.memory.hydration import RepairFinding

    return RepairFinding(
        finding_id="finding-1",
        origin=FindingOrigin.TARGET_REVIEW,
        content="Clarify the runtime boundary.",
    )


def _call(call_id: str, name: str, arguments: dict[str, Any]) -> LLMToolCall:
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def _response(
    *calls: LLMToolCall,
    usage: LLMUsage | None = None,
) -> LLMResponse:
    return LLMResponse(
        tool_calls=list(calls),
        usage=usage or LLMUsage(input_tokens=10, output_tokens=5),
        provider="test",
        model="gpt-test",
    )
