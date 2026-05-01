import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import {
  formatGroundingRules,
  formatKnowledgeDocContext,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

export function buildBusinessLogicPrompt(
  input: KnowledgeDocGenerationInput,
): KnowledgeDocPrompt {
  return {
    system:
      "You generate grounded business logic documentation for software repositories.",
    prompt: [
      "# Task",
      "Generate a grounded business logic document for this repository.",
      "",
      "# Required sections",
      formatRequiredSections(
        KNOWLEDGE_DOC_SPECS.businessLogic.requiredSections,
      ),
      "",
      "# Business logic guidance",
      "- Describe the product or domain purpose only from observed evidence.",
      "- Capture entities, workflows, rules, and integrations that are visible in the codebase.",
      "- Separate observed behavior from inferred behavior.",
      "- Point to assumptions when the evidence is incomplete.",
      "",
      "# Grounding rules",
      formatGroundingRules(),
      "",
      "# Output rules",
      formatMarkdownOutputRules(),
      "",
      "# Repo context",
      formatKnowledgeDocContext(input),
    ].join("\n"),
  };
}
