import type { GenerateAgentRulesDocInput } from "../../../models/agent-rules-doc";
import { GenerateAgentRulesDocInputSchema } from "../../../models/agent-rules-doc";
import { KNOWLEDGE_DOC_SPECS } from "../../../doc-generator/doc-specs";
import type { KnowledgeDocPrompt } from "../../../doc-generator/knowledge-doc-prompt";
import {
  formatCommands,
  formatDetectedStack,
  formatGroundingRules,
  formatImportantFiles,
  formatMarkdownOutputRules,
  formatRequiredSections,
} from "../shared/prompt-formatting";

function formatRepoContext(repoContext: GenerateAgentRulesDocInput["repoContext"]): string {
  return [
    "## Repo root",
    repoContext.repoRoot,
    "",
    "## Generated at",
    repoContext.generatedAt,
    "",
    "## Detected stack",
    formatDetectedStack(repoContext.stack),
    "",
    "## Commands",
    formatCommands(repoContext.commands),
    "",
    "## Important files",
    formatImportantFiles(repoContext.importantFiles),
  ].join("\n");
}

function formatGeneratedDocs(
  generatedDocs: GenerateAgentRulesDocInput["generatedDocs"],
): string {
  return [
    `## ${KNOWLEDGE_DOC_SPECS.repoAnalysis.filename}`,
    generatedDocs.repoAnalysis,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.architecture.filename}`,
    generatedDocs.architecture,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.conventions.filename}`,
    generatedDocs.conventions,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.businessLogic.filename}`,
    generatedDocs.businessLogic,
    "",
    `## ${KNOWLEDGE_DOC_SPECS.testing.filename}`,
    generatedDocs.testing,
  ].join("\n");
}

export function buildAgentRulesPrompt(
  input: GenerateAgentRulesDocInput,
): KnowledgeDocPrompt {
  const parsedInput = GenerateAgentRulesDocInputSchema.parse(input);

  return {
    system:
      "You generate repo-aware agent rules from repository context and the generated documentation.",
    prompt: [
      "# Task",
      "Generate practical, repo-specific rules for coding agents.",
      "",
      "# Required sections",
      formatRequiredSections(KNOWLEDGE_DOC_SPECS.agentRules.requiredSections),
      "",
      "# Agent guidance",
      "- Explain how agents should work safely in this repository.",
      "- Ground the rules in the repository context and the generated docs.",
      "- Be specific about commands, testing expectations, risky areas, and scoping rules.",
      "- Call out files and folders to avoid unless explicitly needed.",
      "",
      "# Grounding rules",
      formatGroundingRules(),
      "",
      "# Output rules",
      formatMarkdownOutputRules(),
      "",
      "# Repo context",
      formatRepoContext(parsedInput.repoContext),
      "",
      "# Generated docs",
      formatGeneratedDocs(parsedInput.generatedDocs),
      "",
    ].join("\n"),
  };
}
