"""Final structured Context Plan synthesis prompt."""

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    FinalSynthesisPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import (
    build_system_message,
    render_json_section,
    sorted_paths,
    sorted_strings,
)
from bridger.llm.models import LLMMessage
from bridger.models.context_plan import ContextPlan


def build_final_synthesis_prompt(input: FinalSynthesisPromptInput) -> ContextPlanPrompt:
    """Build a tool-free structured-output prompt from validated evidence only."""

    excerpts = sorted(
        input.inspected_excerpts,
        key=lambda excerpt: (excerpt.path, excerpt.line_start, excerpt.line_end),
    )
    symbols = sorted(
        input.inspected_symbols,
        key=lambda symbol: (symbol.path or "", symbol.identifier),
    )
    manifests = sorted(input.manifest_evidence, key=lambda manifest: manifest.path)
    entrypoints = sorted(
        input.confirmed_entrypoints,
        key=lambda entrypoint: (entrypoint.path, entrypoint.source),
    )
    exclusions = sorted(
        input.intentionally_excluded,
        key=lambda exclusion: (exclusion.path_or_pattern, exclusion.reason),
    )
    sections = [
        "Return only a structured ContextPlan matching the supplied schema. Build "
        "neutral, reusable packages; group files by coherent repository topic, "
        "subsystem, workflow, convention, or concern rather than by a former "
        "memory-target design. A package may support one or more downstream "
        "consumers.",
        "Do not add memory_targets or target_memory_kind. Do not assign a package "
        "to a memory agent. Do not create packages merely to satisfy any former "
        "five-memory-target design. Distinguish confirmed facts from interpretation, "
        "preserve warnings and unknowns, and include only paths and provenance backed "
        "by the supplied validated evidence.",
        render_json_section("Repository bootstrap facts", input.repository_bootstrap),
        render_json_section(
            "Validated evidence paths", sorted_paths(input.validated_evidence_paths)
        ),
        render_json_section("Inspected excerpts", excerpts),
        render_json_section("Inspected symbols", symbols),
        render_json_section("Manifest evidence", manifests),
        render_json_section("Graph evidence", input.graph_evidence),
        render_json_section(
            "Collected findings", sorted_strings(input.collected_findings)
        ),
        render_json_section("Confirmed entrypoints", entrypoints),
        render_json_section("Warnings", sorted_strings(input.warnings)),
        render_json_section("Unknowns", sorted_strings(input.unknowns)),
        render_json_section("Intentionally excluded candidates", exclusions),
        render_json_section(
            "ContextPlan output schema", ContextPlan.model_json_schema()
        ),
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    "Synthesize only from the validated evidence supplied in this "
                    "prompt. No repository or control tools are available."
                )
            ),
            LLMMessage.user("\n\n".join(sections)),
        ),
        output_type=ContextPlan,
    )
