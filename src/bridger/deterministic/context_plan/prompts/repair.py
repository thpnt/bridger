"""Single-pass repair prompt for invalid Context Plan synthesis output."""

import json

from pydantic import JsonValue

from bridger.deterministic.context_plan.prompts.models import (
    ContextPlanPrompt,
    ContextPlanRepairPromptInput,
)
from bridger.deterministic.context_plan.prompts.shared import build_system_message
from bridger.deterministic.context_plan.prompts.synthesis import (
    build_final_synthesis_prompt,
)
from bridger.llm.models import LLMMessage
from bridger.models.context_plan import ContextPlan


def build_context_plan_repair_prompt(
    input: ContextPlanRepairPromptInput,
) -> ContextPlanPrompt:
    """Build one tool-free repair request from the original evidence boundary."""

    synthesis_prompt = build_final_synthesis_prompt(input.synthesis_evidence)
    synthesis_message = synthesis_prompt.messages[-1]
    assert synthesis_message.content is not None
    repair_sections = [
        """Correct only the reported structural or validation defects.

Preserve the candidate's supported repository meaning. Do not introduce new
repository facts, paths, ranges, packages, findings, relationships, or
interpretations.

Do not use the repair pass to compensate for missing investigation or semantic
coverage.

Invented, unsafe, uninspected, or unsupported paths and provenance remain forbidden.
A path appearing in the invalid candidate is not evidence. The repaired candidate
must pass the full normal ContextPlan validation.

Return only the corrected structured ContextPlan.""",
        _render_exact_json_section(
            "Invalid ContextPlan candidate",
            input.invalid_output,
        ),
        _render_exact_json_section(
            "Exact ContextPlan validation issues",
            [issue.model_dump(mode="json") for issue in input.validation_issues],
        ),
        "Original validated synthesis evidence and schema requirements:\n\n"
        f"{synthesis_message.content}",
    ]
    return ContextPlanPrompt(
        messages=(
            LLMMessage.system(
                build_system_message(
                    """Repair one ContextPlan synthesis result. No repository,
state-management, or control tools are available. Use only the exact synthesis input
manifest and selected evidence repeated in this prompt. Do not recover repository
facts from conversation memory."""
                )
            ),
            LLMMessage.user("\n\n".join(repair_sections)),
        ),
        output_type=ContextPlan,
    )


def _render_exact_json_section(title: str, value: JsonValue) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{title}:\n```json\n{serialized}\n```"
