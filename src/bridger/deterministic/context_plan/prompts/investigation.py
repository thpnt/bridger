"""Investigation continuation prompt for Context Plan discovery."""

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    InvestigationPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import (
    build_system_message,
    render_json_section,
    render_tool_catalog,
    sorted_paths,
    sorted_strings,
    sorted_tools,
)
from bridger.llm.models import LLMMessage


def build_investigation_prompt(input: InvestigationPromptInput) -> ContextPlanPrompt:
    """Build a tools-enabled continuation without evaluating finalization policy."""

    tools = sorted_tools(input.available_tools)
    latest_results = sorted(
        input.latest_tool_results,
        key=lambda result: (result.call_id, result.tool_name),
    )
    sections = [
        render_json_section("Latest structured tool results", latest_results),
        render_json_section("Inspection progress", input.inspection),
        render_json_section("Discovered paths", sorted_paths(input.discovered_paths)),
        render_json_section("Evidence paths", sorted_paths(input.evidence_paths)),
        render_json_section("Remaining budgets", input.remaining_budgets),
        render_json_section("Warnings", sorted_strings(input.warnings)),
        render_json_section("Open questions", sorted_strings(input.open_questions)),
        render_json_section(
            "Investigation notes", sorted_strings(input.investigation_notes)
        ),
        render_json_section(
            "Durable working-state summary", input.working_state_summary
        ),
        render_json_section(
            "Durable working-state entities", input.working_state_entities
        ),
        render_tool_catalog(list(tools)),
        "Use the state-management tools to externalize durable findings, "
        "relationships, questions, and package candidates with stable evidence IDs. "
        "Choose additional repository tool calls, state-management tool calls, or call "
        "request_context_plan_finalization. Request finalization "
        "only when you believe the grounded evidence can support a useful neutral "
        "Context Plan. Use that structured control tool; never return a prose final "
        "answer. Do not decide whether finalization will be accepted.",
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    "Continue bounded investigation. Open questions are advisory "
                    "context, not a completion requirement."
                )
            ),
            *input.interaction_history,
            LLMMessage.user("\n\n".join(sections)),
        ),
        tools=tools,
    )
