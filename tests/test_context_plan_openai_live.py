import asyncio
import os
from pathlib import Path

import pytest
from test_context_plan_builder import make_builder
from test_discovery_tools import tool_repo as inherited_tool_repo

from bridger.deterministic.context_plan.run_state import DiscoveryBudgetLimits
from bridger.llm import create_llm_client
from bridger.tools.context import BridgerToolContext


@pytest.fixture
def context_with_repo(tmp_path: Path) -> tuple[Path, BridgerToolContext]:
    return inherited_tool_repo.__wrapped__(tmp_path)


@pytest.mark.skipif(
    os.environ.get("BRIDGER_RUN_LIVE_OPENAI") != "1",
    reason="Set BRIDGER_RUN_LIVE_OPENAI=1 to run the live OpenAI builder test",
)
def test_live_openai_context_plan_builder(
    context_with_repo: tuple[Path, BridgerToolContext],
) -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY is required")
    if not os.environ.get("BRIDGER_OPENAI_MODEL", "").strip():
        pytest.skip("BRIDGER_OPENAI_MODEL is required")

    root, context = context_with_repo
    builder = make_builder(
        root,
        context,
        create_llm_client(),
        limits=DiscoveryBudgetLimits(
            model_turns=8,
            tool_calls=20,
            consecutive_no_progress_threshold=4,
        ),
    )

    run = asyncio.run(builder.build(run_id="live-openai-context-plan"))
    plan_path = root / ".bridger/artifacts/context-plan.json"
    run_path = root / ".bridger/artifacts/context-plan-run.json"
    print(
        f"status={run.status.value} "
        f"context_plan={plan_path} context_plan_run={run_path}"
    )

    assert run.status.value == "completed"
    assert plan_path.is_file()
    assert run_path.is_file()
