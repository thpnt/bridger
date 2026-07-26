"""Production dependency assembly for Context Plan generation."""

from pathlib import Path

from bridger.deterministic.context_plan.builder import ContextPlanBuilder
from bridger.deterministic.context_plan.completion_policy import (
    ContextPlanCompletionPolicy,
)
from bridger.deterministic.context_plan.discovery_tools import DiscoveryToolExecutor
from bridger.deterministic.context_plan.run_state import (
    ContextPlanRunRecorder,
    DiscoveryBudgetPolicy,
)
from bridger.llm.client import LLMClient
from bridger.tools.context import build_tool_context


def create_context_plan_builder(
    repo_root: Path,
    *,
    llm_client: LLMClient,
    model_profile: str,
) -> ContextPlanBuilder:
    """Create the provider-independent builder over persisted repository artifacts."""
    context = build_tool_context(repo_root)
    artifacts = context.artifact_store.artifact_dir
    return ContextPlanBuilder(
        llm_client=llm_client,
        artifact_store=context.artifact_store,
        tool_executor=DiscoveryToolExecutor(context),
        budget_policy=DiscoveryBudgetPolicy(),
        completion_policy=ContextPlanCompletionPolicy(context.path_safety),
        run_recorder=ContextPlanRunRecorder(artifacts / "context-plan-run.json"),
        context_plan_destination=artifacts / "context-plan.json",
        model_profile=model_profile,
    )
