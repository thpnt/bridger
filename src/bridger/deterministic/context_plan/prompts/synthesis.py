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
            "Selected unresolved questions and contradictions",
            input.selected_questions,
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
        """Return only a structured ContextPlan matching the supplied schema.

Build neutral reusable packages around coherent repository systems, workflows,
contracts, conventions, and concerns. Do not group files merely because they share a
directory or were discovered together.

A package must be sufficient for a bounded downstream agent to understand its stated
purpose without reopening general repository exploration.

For each package:

* give it one clear repository concern;
* select evidence that collectively establishes the concern;
* order items by logical understanding or runtime flow, not arbitrary file order;
* include construction, trigger, core processing, state, persistence, integrations,
  outputs, failures, and tests where they materially apply;
* include important relationships to other components;
* narrow the package when evidence supports only part of a broader concern;
* preserve material warnings, contradictions, and unknowns.

Prefer inspected implementation evidence over documentation when describing runtime
behaviour. Use manifests, schemas, configuration, symbols, and documentation for the
facts they can establish, but do not treat them as substitutes for implementation
evidence.

Symbol existence, imports, endpoint declarations, and filenames can support
navigation or structural claims. They are not sufficient evidence for behavioural
claims.

Use established findings and relationships to connect evidence into coherent
packages. Do not merely reproduce lists of inspected files.

Avoid:

* duplicate packages covering the same concern;
* broad packages supported by only one workflow stage;
* packages built solely from symbols or search matches;
* repeated evidence without a distinct purpose;
* unsupported architectural interpretations;
* suppressing uncertainty to make the plan appear complete.

Ensure that every major covered subsystem and principal workflow is represented by an
appropriate package, or is preserved as a justified exclusion or unknown.

Do not add memory_targets or target_memory_kind. Do not assign packages to downstream
memory agents. Do not create packages merely to satisfy any former five-memory-target
design.

Include only paths, ranges, findings, relationships, and provenance backed by the
supplied validated evidence.""",
        render_exact_json_section(
            "Context Plan bootstrap facts", input.context_plan_bootstrap
        ),
        render_exact_json_section(
            "Semantic coverage summary", _semantic_coverage(input)
        ),
        render_exact_json_section(
            "Principal workflow stage coverage", _workflow_coverage(input)
        ),
        *(
            projected_sections
            if input.synthesis_manifest is not None
            else legacy_sections
        ),
        render_exact_json_section(
            "Evidence-selection and omission report",
            _evidence_selection_report(input),
        ),
        render_exact_json_section("Warnings", sorted_strings(input.warnings)),
        render_exact_json_section("Unknowns", sorted_strings(input.unknowns)),
        render_exact_json_section("Intentionally excluded candidates", exclusions),
        render_exact_json_section(
            "ContextPlan output schema", ContextPlan.model_json_schema()
        ),
        """Before returning the structured output, verify internally that:

* every package has a coherent and distinct purpose;
* behavioural claims have implementation evidence;
* package items collectively support the stated purpose;
* important workflow stages have not silently disappeared;
* unknowns and exclusions remain visible;
* all paths and ranges originate from validated evidence;
* the result matches the supplied schema.

Return only the structured ContextPlan.""",
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    """Synthesize only from the validated durable evidence and coverage
state supplied in this prompt. No repository, state-management, or control tools are
available.

Do not recover missing evidence from conversation memory. Do not broaden a claim
beyond the evidence depth supplied."""
                )
            ),
            LLMMessage.user("\n\n".join(sections)),
        ),
        output_type=ContextPlan,
    )


def _semantic_coverage(input: FinalSynthesisPromptInput) -> object:
    manifest = input.synthesis_manifest
    if manifest is None:
        return {
            "coverage_basis": "legacy validated evidence",
            "represented_paths": sorted_paths(input.validated_evidence_paths),
        }
    return {
        "represented_area_keys": manifest.represented_area_keys,
        "selected_candidate_ids": manifest.selected_candidate_ids,
        "selected_finding_ids": manifest.selected_finding_ids,
        "selected_relationship_ids": manifest.selected_relationship_ids,
        "selected_question_ids": manifest.selected_question_ids,
    }


def _workflow_coverage(input: FinalSynthesisPromptInput) -> object:
    return {
        "coverage_basis": (
            "selected package candidates; no separate workflow-stage artifact "
            "was supplied"
        ),
        "selected_package_candidates": [
            {
                "area_keys": item.area_keys,
                "candidate_id": item.candidate_id,
                "purpose": item.purpose,
                "question_ids": item.question_ids,
                "title": item.title,
            }
            for item in input.selected_candidates
        ],
    }


def _evidence_selection_report(input: FinalSynthesisPromptInput) -> object:
    manifest = input.synthesis_manifest
    if manifest is None:
        return {
            "available_record_count": len(input.validated_evidence_paths),
            "omitted_record_count": 0,
            "selection_basis": "legacy validated evidence",
        }
    return {
        "available_record_count": manifest.available_record_count,
        "estimated_size": manifest.estimated_size,
        "omission_reasons": manifest.omission_reasons,
        "omitted_by_area": manifest.omitted_by_area,
        "omitted_by_kind": manifest.omitted_by_kind,
        "omitted_by_path": manifest.omitted_by_path,
        "omitted_counts": manifest.omitted_counts,
        "omitted_record_count": manifest.omitted_record_count,
        "selected_record_count": manifest.selected_record_count,
        "selection_limits": manifest.selection_limits,
    }
