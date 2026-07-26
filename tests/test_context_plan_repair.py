import asyncio
from pathlib import Path

import pytest
from pydantic import JsonValue, RootModel
from test_context_plan_builder import (
    finalization_call,
    read_app_ranges_call,
    synthesis_response,
    tool_response,
    valid_plan,
)
from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.builder import ContextPlanBuilder
from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.deterministic.context_plan.discovery_tools import DiscoveryToolExecutor
from bridger.deterministic.context_plan.prompts import (
    ContextPlanRepairPromptInput,
    build_context_plan_repair_prompt,
)
from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    ContextPlanRunState,
    DiscoveryBudgetLimits,
    DiscoveryBudgetPolicy,
)
from bridger.deterministic.context_plan.validation import ContextPlanValidationError
from bridger.llm.models import LLMResponse, LLMUsage
from bridger.llm.testing import DummyLLMClient
from bridger.models.context_plan import ContextPlan
from bridger.tools.context import BridgerToolContext
from bridger.tools.services.artifact_store import ArtifactStore


class InvalidContextPlanOutput(RootModel[dict[str, JsonValue]]):
    pass


@pytest.fixture
def context_with_repo(tmp_path: Path) -> tuple[Path, BridgerToolContext]:
    return inherited_tool_repo.__wrapped__(tmp_path)


def invalid_schema_response(
    *,
    usage: LLMUsage | None = None,
    latency_ms: int | None = None,
) -> LLMResponse:
    payload = valid_plan().model_dump(mode="json")
    del payload["summary"]
    return LLMResponse(
        structured_output=InvalidContextPlanOutput(payload),
        provider="dummy",
        model="scripted",
        usage=usage or LLMUsage(total_tokens=11),
        latency_ms=latency_ms,
    )


def discovery_responses() -> list[LLMResponse]:
    return [
        tool_response(read_app_ranges_call()),
        tool_response(finalization_call()),
    ]


def make_repair_builder(
    root: Path,
    context: BridgerToolContext,
    client: DummyLLMClient,
    *,
    model_turns: int,
    token_usage: int | None = None,
    captured_inputs: list[ContextPlanRepairPromptInput] | None = None,
    captured_states: list[ContextPlanRunState] | None = None,
) -> ContextPlanBuilder:
    def build_repair_prompt(input: ContextPlanRepairPromptInput):
        if captured_inputs is not None:
            captured_inputs.append(input)
        return build_context_plan_repair_prompt(input)

    def make_state(**kwargs):
        state = ContextPlanRunState(**kwargs)
        if captured_states is not None:
            captured_states.append(state)
        return state

    return ContextPlanBuilder(
        llm_client=client,
        artifact_store=ArtifactStore(root),
        tool_executor=DiscoveryToolExecutor(context),
        budget_policy=DiscoveryBudgetPolicy(
            DiscoveryBudgetLimits(
                model_turns=model_turns,
                token_usage=token_usage,
                consecutive_no_progress_threshold=10,
            )
        ),
        completion_policy=ContextPlanCompletionPolicy(context.path_safety),
        run_recorder=ContextPlanRunRecorder(
            root / ".bridger/artifacts/context-plan-run.json"
        ),
        context_plan_destination=root / ".bridger/artifacts/context-plan.json",
        run_state_factory=make_state,
        repair_prompt_builder=build_repair_prompt,
    )


def test_invalid_synthesis_is_repaired_once_without_tools_and_keeps_evidence(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    captured_inputs: list[ContextPlanRepairPromptInput] = []
    captured_states: list[ContextPlanRunState] = []
    repaired = synthesis_response(valid_plan()).model_copy(
        update={
            "usage": LLMUsage(input_tokens=9, output_tokens=8, total_tokens=17),
            "latency_ms": 19,
        }
    )
    client = DummyLLMClient(
        [
            *discovery_responses(),
            invalid_schema_response(
                usage=LLMUsage(input_tokens=6, output_tokens=5, total_tokens=11),
                latency_ms=13,
            ),
            repaired,
        ]
    )
    builder = make_repair_builder(
        root,
        context,
        client,
        model_turns=4,
        captured_inputs=captured_inputs,
        captured_states=captured_states,
    )

    run = asyncio.run(builder.build(run_id="repair-success"))

    assert run.status.value == "completed"
    assert len(client.requests) == 4
    repair_request = client.requests[-1]
    assert repair_request.tools == []
    assert repair_request.metadata["context_plan_attempt"] == "repair"
    assert client.output_types[-1] is ContextPlan
    assert len(captured_inputs) == 1
    repair_input = captured_inputs[0]
    assert repair_input.validation_issues == run.validation_attempts[0].issues
    assert repair_input.validation_issues[0].code == "schema_validation_error"
    assert repair_input.synthesis_evidence.validated_evidence_paths == ["src/app.py"]
    assert repair_input.synthesis_evidence.inspected_excerpts[0].path == "src/app.py"
    repair_text = repair_request.messages[-1].content or ""
    assert "Invalid ContextPlan candidate" in repair_text
    assert "Exact ContextPlan validation issues" in repair_text
    assert "from src.util import helper" in repair_text

    state = captured_states[0]
    assert run.model_turns == 4
    assert run.token_usage == 48
    assert run.input_tokens == 15
    assert run.output_tokens == 13
    assert run.model_latency_ms == 32
    event_types = [event.event_type for event in state.events]
    assert event_types.count("repair_started") == 1
    assert event_types.count("repair_completed") == 1


@pytest.mark.parametrize(
    ("invalid_plan", "expected_issue"),
    [
        (
            lambda: valid_plan().model_copy(
                update={
                    "packages": [
                        valid_plan()
                        .packages[0]
                        .model_copy(
                            update={
                                "ordered_items": [
                                    valid_plan()
                                    .packages[0]
                                    .ordered_items[0]
                                    .model_copy(update={"path": "invented.py"})
                                ]
                            }
                        )
                    ]
                }
            ),
            "unknown_path",
        ),
        (
            lambda: valid_plan().model_copy(
                update={
                    "packages": [
                        valid_plan()
                        .packages[0]
                        .model_copy(
                            update={
                                "provenance": [
                                    valid_plan()
                                    .packages[0]
                                    .provenance[0]
                                    .model_copy(update={"line_end": 99})
                                ]
                            }
                        )
                    ]
                }
            ),
            "line_range_out_of_bounds",
        ),
        (
            lambda: valid_plan().model_copy(
                update={
                    "packages": [
                        valid_plan()
                        .packages[0]
                        .model_copy(
                            update={
                                "ordered_items": [
                                    valid_plan()
                                    .packages[0]
                                    .ordered_items[0]
                                    .model_copy(update={"path": "src/util.py"})
                                ],
                                "provenance": [
                                    valid_plan()
                                    .packages[0]
                                    .provenance[0]
                                    .model_copy(update={"path": "src/util.py"})
                                ],
                            }
                        )
                    ]
                }
            ),
            "unknown_path",
        ),
    ],
    ids=["invented-path", "unsupported-provenance", "safe-uninspected-path"],
)
def test_invalid_repair_is_rejected_by_normal_validation_and_preserves_plan(
    context_with_repo: tuple[Path, BridgerToolContext],
    invalid_plan,
    expected_issue: str,
) -> None:
    root, context = context_with_repo
    destination = root / ".bridger/artifacts/context-plan.json"
    previous = b'{"previous":"valid artifact"}\n'
    destination.write_bytes(previous)
    states: list[ContextPlanRunState] = []
    client = DummyLLMClient(
        [
            *discovery_responses(),
            synthesis_response(valid_plan(line_end=99)),
            synthesis_response(invalid_plan()),
        ]
    )
    builder = make_repair_builder(
        root,
        context,
        client,
        model_turns=4,
        captured_states=states,
    )

    with pytest.raises(ContextPlanValidationError) as caught:
        asyncio.run(builder.build(run_id=f"repair-failure-{expected_issue}"))

    assert expected_issue in {issue.code for issue in caught.value.issues}
    assert len(client.requests) == 4
    assert destination.read_bytes() == previous
    assert states[0].status.value == "failed"
    assert len(states[0].validation_attempts) == 2
    assert all(not attempt.succeeded for attempt in states[0].validation_attempts)
    assert [event.event_type for event in states[0].events].count("repair_started") == 1


@pytest.mark.parametrize(
    ("model_turns", "token_usage", "expected_reason"),
    [(3, None, "model_turns"), (4, 31, "token_usage")],
    ids=["model-turn-budget", "token-budget"],
)
def test_budget_rejection_prevents_repair_call_and_records_outcome(
    context_with_repo: tuple[Path, BridgerToolContext],
    model_turns: int,
    token_usage: int | None,
    expected_reason: str,
) -> None:
    root, context = context_with_repo
    states: list[ContextPlanRunState] = []
    client = DummyLLMClient(
        [
            *discovery_responses(),
            invalid_schema_response(
                usage=LLMUsage(input_tokens=4, output_tokens=7, total_tokens=11),
                latency_ms=23,
            ),
        ]
    )
    builder = make_repair_builder(
        root,
        context,
        client,
        model_turns=model_turns,
        token_usage=token_usage,
        captured_states=states,
    )

    with pytest.raises(ContextPlanValidationError):
        asyncio.run(builder.build(run_id=f"repair-budget-rejected-{expected_reason}"))

    assert len(client.requests) == 3
    assert states[0].model_turns == 3
    assert states[0].token_usage == 31
    assert states[0].model_latency_ms == 23
    budget_event = next(
        event
        for event in states[0].events
        if event.event_type == "repair_budget_rejected"
    )
    assert budget_event.metadata["reasons"] == expected_reason
    assert states[0].status.value == "failed"
    assert not (root / ".bridger/artifacts/context-plan.json").exists()


def test_second_schema_invalid_output_ends_after_one_repair(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    states: list[ContextPlanRunState] = []
    client = DummyLLMClient(
        [
            *discovery_responses(),
            invalid_schema_response(),
            invalid_schema_response(),
        ]
    )
    builder = make_repair_builder(
        root,
        context,
        client,
        model_turns=4,
        captured_states=states,
    )

    with pytest.raises(ContextPlanValidationError) as caught:
        asyncio.run(builder.build(run_id="repair-schema-failure"))

    assert len(client.requests) == 4
    assert {issue.code for issue in caught.value.issues} == {"schema_validation_error"}
    assert len(states[0].validation_attempts) == 2
    assert states[0].status.value == "failed"


def test_valid_synthesis_does_not_trigger_repair(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    captured_inputs: list[ContextPlanRepairPromptInput] = []
    client = DummyLLMClient([*discovery_responses(), synthesis_response(valid_plan())])
    builder = make_repair_builder(
        root,
        context,
        client,
        model_turns=3,
        captured_inputs=captured_inputs,
    )

    run = asyncio.run(builder.build(run_id="no-repair"))

    assert run.status.value == "completed"
    assert len(client.requests) == 3
    assert captured_inputs == []
