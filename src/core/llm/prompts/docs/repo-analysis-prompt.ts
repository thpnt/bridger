import type { KnowledgeDocGenerationInput } from "../../../doc-generator/knowledge-doc-input";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import {
  formatGroundingRules,
  formatKnowledgeDocContext,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

export function buildRepoAnalysisPrompt(
  input: KnowledgeDocGenerationInput,
): KnowledgeDocPrompt {
  return {
    system:
      "You generate grounded repository analysis documentation for software repositories.",
    prompt: [
      "# Task",
      "Generate a grounded repository analysis document for this repository.",
      "",
      "# Required sections",
      formatRequiredSections(KNOWLEDGE_DOC_SPECS.repoAnalysis.requiredSections),
      "",
      "# Analysis guidance",
      "- Summarize what the repository appears to be and how it is organized.",
      "- Use file and folder evidence from the file index and important files.",
      "- Highlight the entry points, feature areas, and notable implementation patterns that are visible.",
      "- Separate observed facts from assumptions.",
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
