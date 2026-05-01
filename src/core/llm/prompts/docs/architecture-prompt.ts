import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import {
  formatGroundingRules,
  formatKnowledgeDocContext,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

export function buildArchitecturePrompt(
  input: KnowledgeDocGenerationInput,
): KnowledgeDocPrompt {
  return {
    system:
      "You generate grounded architecture documentation for software repositories.",
    prompt: [
      "# Task",
      "Generate a grounded architecture document for this repository.",
      "",
      "# Required sections",
      formatRequiredSections(KNOWLEDGE_DOC_SPECS.architecture.requiredSections),
      "",
      "# Architecture guidance",
      "- Explain the application structure and how the major folders relate to each other.",
      "- Identify core domains only when files provide enough evidence.",
      "- State data flow assumptions explicitly.",
      "- Call out risky areas, boundaries, and missing evidence.",
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
