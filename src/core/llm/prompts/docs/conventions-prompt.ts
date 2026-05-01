import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import {
  formatGroundingRules,
  formatKnowledgeDocContext,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

export function buildConventionsPrompt(
  input: KnowledgeDocGenerationInput,
): KnowledgeDocPrompt {
  return {
    system:
      "You generate grounded conventions documentation for software repositories.",
    prompt: [
      "# Task",
      "Generate a grounded conventions document for this repository.",
      "",
      "# Required sections",
      formatRequiredSections(KNOWLEDGE_DOC_SPECS.conventions.requiredSections),
      "",
      "# Conventions guidance",
      "- Focus on conventions that are observable in the repository.",
      "- Cover TypeScript, component, server/client boundary, validation, styling, data access, testing, and naming conventions.",
      "- Distinguish observed conventions from recommendations.",
      "- Highlight things agents should avoid when working in this codebase.",
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
