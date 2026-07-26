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
        """Begin repository orientation.

Your immediate objective is to identify:

* repository identity, languages, toolchain, and workspace boundaries;
* concrete application, service, CLI, worker, or library entrypoints;
* likely major runtime areas;
* likely principal workflows;
* configuration, persistence, integration, testing, and convention anchors;
* important contradictions or missing operational context;
* central files that require targeted implementation inspection.

Use the available tools progressively. For long or central files, inspect their
overview and symbols before selecting targeted implementation ranges. Do not
repeatedly read only the beginning of large files.

Do not attempt final synthesis during orientation.""",
        render_json_section(
            "Context Plan bootstrap facts", input.context_plan_bootstrap
        )
        if input.context_plan_bootstrap is not None
        else "Context Plan bootstrap facts: no additional artifact supplied.",
        render_json_section(
            "Repository discovery and inventory health",
            _repository_discovery(input),
        ),
        render_json_section("File index", input.file_index)
        if input.file_index is not None
        else "File index: no additional artifact supplied.",
        render_json_section("Symbol index summary", input.symbol_index)
        if input.symbol_index is not None
        else "Symbol index summary: no additional artifact supplied.",
        render_json_section(
            "Manifest and repository-context facts", input.repository_context
        )
        if input.repository_context is not None
        else "Manifest and repository-context facts: no additional artifact supplied.",
        render_json_section(
            "Repository instructions and documentation anchors",
            _instruction_and_documentation_anchors(input),
        ),
        render_json_section("Configured budgets", input.run_budget_limits),
        render_json_section(
            "Initial warnings and deterministic diagnostics",
            sorted_strings(input.initial_warnings),
        ),
        render_tool_catalog(list(tools)),
        "Begin investigating through repository tool calls. Do not request Context "
        "Plan finalization during orientation and do not return a prose synthesis.",
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    """Orient from deterministic repository facts before drawing
architectural or behavioural conclusions.

Use inventory, manifests, instructions, configuration anchors, entrypoint
declarations, top-level symbols, tests, and repository structure to identify what
should be investigated next.

During orientation, form hypotheses about repository areas and workflows, but do not
treat those hypotheses as established findings until implementation evidence has
been inspected.

During orientation, normally begin with inspect_repo_discovery, then inspect relevant
manifests and navigate likely repository areas with list_files.

Use get_file_overview, list_symbols, and search_symbols to form investigation
hypotheses. Do not record broad behavioural findings from orientation-only or
symbol-only evidence.

Orientation should identify what needs deeper inspection; it should not attempt to
prove complete workflows."""
                )
            ),
            LLMMessage.user("\n\n".join(sections)),
        ),
        tools=tools,
    )


def _repository_discovery(input: OrientationPromptInput) -> object:
    bootstrap = input.context_plan_bootstrap
    file_index = input.file_index
    return {
        "artifact_paths": (
            bootstrap.artifacts.model_dump(mode="json")
            if bootstrap is not None
            else None
        ),
        "compact_context": (
            bootstrap.compact_context.model_dump(mode="json")
            if bootstrap is not None
            else None
        ),
        "file_count": len(file_index.files) if file_index is not None else None,
        "skipped_file_count": (
            len(file_index.skipped_files) if file_index is not None else None
        ),
    }


def _instruction_and_documentation_anchors(
    input: OrientationPromptInput,
) -> object:
    repository_context = input.repository_context
    if repository_context is None:
        return {
            "documentation": [],
            "instructions": [],
        }
    return {
        "documentation": repository_context.docs_files,
        "instructions": repository_context.instruction_files,
    }
