"""Orientation prompt for a new Context Plan investigation."""

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    OrientationPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import (
    build_system_message,
    render_json_section,
    render_tool_catalog,
    sorted_strings,
    sorted_tools,
)
from bridger.llm.models import LLMMessage


def build_orientation_prompt(input: OrientationPromptInput) -> ContextPlanPrompt:
    """Build the first tools-enabled discovery turn without starting synthesis."""

    tools = sorted_tools(input.available_tools)
    sections = [
        "Context Plan mission: discover enough grounded repository context to "
        "eventually describe coherent, reusable packages by topic, subsystem, "
        "workflow, convention, or concern.",
        render_json_section("Repository bootstrap facts", input.repository_bootstrap),
        render_json_section(
            "Repository context facts", input.repository_context
        )
        if input.repository_context is not None
        else "Repository context facts: no additional artifact supplied.",
        render_json_section("Graph facts", input.graph_summary)
        if input.graph_summary is not None
        else "Graph facts: use the bootstrap compact context until inspected.",
        render_json_section(
            "Configured budgets",
            {
                "repository_tool_output_limits": input.repository_bootstrap.budgets,
                "run_budget_limits": input.run_budget_limits,
            },
        ),
        render_json_section("Initial warnings", sorted_strings(input.initial_warnings)),
        render_tool_catalog(list(tools)),
        "Begin investigating now by responding with repository tool calls. Do not "
        "request Context Plan finalization during orientation and do not return a "
        "prose synthesis.",
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    "Use the supplied repository tools to orient yourself before "
                    "drawing conclusions."
                )
            ),
            LLMMessage.user("\n\n".join(sections)),
        ),
        tools=tools,
    )
