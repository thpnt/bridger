import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from test_context_plan_builder import make_builder, read_run, valid_plan
from test_discovery_tools import tool_repo as inherited_tool_repo
from test_llm_openai import FakeOpenAI, text_response

from bridger.deterministic.context_plan.run_state import DiscoveryBudgetLimits
from bridger.llm.errors import LLMTimeoutError
from bridger.llm.profiles import LLMProfile, RetryPolicy
from bridger.llm.providers.openai import OpenAILLMClient
from bridger.models.context_plan import ContextPlan
from bridger.tools.context import BridgerToolContext


@pytest.fixture
def context_with_repo(tmp_path: Path) -> tuple[Path, BridgerToolContext]:
    return inherited_tool_repo.__wrapped__(tmp_path)


def openai_profile(*, max_attempts: int = 1) -> LLMProfile:
    return LLMProfile(
        name="balanced",
        provider="openai",
        model="gpt-test",
        retry_policy=RetryPolicy(max_attempts=max_attempts),
    )


def function_call_response(
    call_id: str,
    name: str,
    arguments: str,
) -> dict[str, Any]:
    return text_response(
        output=[
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
        ]
    )


def deterministic_clock() -> Callable[[], float]:
    values = iter([0.0, 1.0, 2.0, 4.0, 5.0, 8.0, 9.0, 13.0])

    def clock() -> float:
        return next(values)

    return clock


def test_openai_client_runs_the_same_builder_through_repair_and_accounting(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    invalid_plan = valid_plan().model_dump(mode="json")
    del invalid_plan["summary"]
    fake = FakeOpenAI(
        [
            function_call_response(
                "read",
                "read_file_excerpt",
                '{"path":"src/app.py","end_line":2}',
            ),
            function_call_response(
                "finalize",
                "request_context_plan_finalization",
                (
                    '{"explored_areas":["application entrypoint"],'
                    '"key_evidence_paths":["src/app.py"],'
                    '"unresolved_areas":[],'
                    '"sufficiency_reason":"The inspected excerpt is sufficient."}'
                ),
            ),
            text_response(output_text=json.dumps(invalid_plan)),
            text_response(output_text=valid_plan().model_dump_json()),
        ]
    )
    client = OpenAILLMClient(
        openai_client=fake,
        profile=openai_profile(),
        clock=deterministic_clock(),
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=4,
            consecutive_no_progress_threshold=10,
        ),
    )

    run = asyncio.run(builder.build(run_id="openai-repair"))

    assert run.status.value == "completed"
    assert [attempt.succeeded for attempt in run.validation_attempts] == [False, True]
    assert run.model_turns == 4
    assert run.token_usage == 32
    assert run.input_tokens == 12
    assert run.output_tokens == 20
    assert run.cached_input_tokens == 4
    assert run.reasoning_tokens == 8
    assert run.model_latency_ms == 10_000
    assert (
        ContextPlan.model_validate_json(
            (root / ".bridger/artifacts/context-plan.json").read_bytes()
        )
        == valid_plan()
    )

    assert len(fake.responses.calls) == 4
    investigation_input = fake.responses.calls[1]["input"]
    assert any(item.get("type") == "function_call" for item in investigation_input)
    assert any(
        item.get("type") == "function_call_output" for item in investigation_input
    )
    repair_payload = fake.responses.calls[-1]
    assert "tools" not in repair_payload
    assert repair_payload["text"]["format"]["name"] == "ContextPlan"
    assert repair_payload["text"]["format"]["schema"] == ContextPlan.model_json_schema()


def test_openai_timeout_fails_the_generic_run_and_preserves_the_plan(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    root, context = context_with_repo
    destination = root / ".bridger/artifacts/context-plan.json"
    previous = b'{"previous":"valid artifact"}\n'
    destination.write_bytes(previous)
    fake = FakeOpenAI(
        [
            function_call_response(
                "read",
                "read_file_excerpt",
                '{"path":"src/app.py","end_line":2}',
            ),
            function_call_response(
                "finalize",
                "request_context_plan_finalization",
                (
                    '{"explored_areas":["application entrypoint"],'
                    '"key_evidence_paths":["src/app.py"],'
                    '"unresolved_areas":[],'
                    '"sufficiency_reason":"The inspected excerpt is sufficient."}'
                ),
            ),
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
        ]
    )
    client = OpenAILLMClient(
        openai_client=fake,
        profile=openai_profile(max_attempts=1),
    )
    builder = make_builder(
        root,
        context,
        client,
        limits=DiscoveryBudgetLimits(
            model_turns=3,
            consecutive_no_progress_threshold=10,
        ),
    )

    with pytest.raises(LLMTimeoutError):
        asyncio.run(builder.build(run_id="openai-timeout"))

    run = read_run(root)
    assert run.status.value == "failed"
    assert run.model_turns == 3
    assert run.token_usage == 16
    assert destination.read_bytes() == previous
