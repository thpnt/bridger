import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import {
  formatGroundingRules,
  formatKnowledgeDocContext,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

export function buildTestingPrompt(
  input: KnowledgeDocGenerationInput,
): KnowledgeDocPrompt {
  return {
    system:
      "You generate grounded testing documentation for software repositories.",
    prompt: [
      "# Task",
      "Generate a grounded testing document for this repository.",
      "",
      "The document should help agents understand what should be tested when implementing new work, what test types are expected, and what testing conventions are visible in this repository.",
      "",
      "# Required sections",
      formatRequiredSections(KNOWLEDGE_DOC_SPECS.testing.requiredSections),
      "",
      "# Testing guidance",
      "- Explain the testing approach that is visible in the repository.",
      "- Describe available test commands and when each command should be used.",
      "- Summarize unit, integration, regression, component/UI, and manual QA expectations when evidence supports them.",
      "- Call out testing gaps and practical verification steps.",
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
