"""Final structured Context Plan synthesis prompt."""

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    FinalSynthesisPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import (
    build_system_message,
    render_exact_json_section,
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
    exclusions = sorted(
        input.intentionally_excluded,
        key=lambda exclusion: (exclusion.path_or_pattern, exclusion.reason),
    )
    selected_evidence = [
        record.model_dump(mode="json", exclude={"content"})
        for record in input.selected_evidence
    ]
    projected_sections = [
        render_exact_json_section("Synthesis input manifest", input.synthesis_manifest),
        render_exact_json_section(
            "Selected package candidates", input.selected_candidates
        ),
        render_exact_json_section(
            "Selected established findings", input.selected_findings
        ),
        render_exact_json_section(
            "Selected relationships", input.selected_relationships
        ),
        render_exact_json_section(
            "Selected unresolved questions", input.selected_questions
        ),
        render_exact_json_section("Selected typed evidence", selected_evidence),
    ]
    legacy_sections = [
        render_exact_json_section(
            "Validated evidence paths", sorted_paths(input.validated_evidence_paths)
        ),
        render_exact_json_section("Inspected excerpts", excerpts),
        render_exact_json_section("Inspected symbols", symbols),
        render_exact_json_section("Manifest evidence", manifests),
        render_exact_json_section(
            "Collected findings", sorted_strings(input.collected_findings)
        ),
    ]
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
        render_exact_json_section(
            "Context Plan bootstrap facts", input.context_plan_bootstrap
        ),
        *(
            projected_sections
            if input.synthesis_manifest is not None
            else legacy_sections
        ),
        render_exact_json_section("Warnings", sorted_strings(input.warnings)),
        render_exact_json_section("Unknowns", sorted_strings(input.unknowns)),
        render_exact_json_section("Intentionally excluded candidates", exclusions),
        render_exact_json_section(
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
