import type { GenerateAgentRulesDocInput } from "../../models/agent-rules-doc";
import { GenerateAgentRulesDocInputSchema } from "../../models/agent-rules-doc";
import type { RepoKnowledgePrompt } from "../../models/repo-knowledge-doc";

export function buildAgentRulesPrompt(
  input: GenerateAgentRulesDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateAgentRulesDocInputSchema.parse(input);

  return {
    system:
      "TODO: Final agent rules prompt will be written manually. For now, generate repo-aware agent rules using only provided repository context and generated docs.",
    prompt: [
      "TODO: Final agent rules prompt placeholder.",
      "",
      "The final prompt should generate practical repo-specific instructions for coding agents.",
      "",
      "Required sections:",
      "- ## Project overview",
      "- ## Commands",
      "- ## Rules for agents",
      "- ## Coding conventions",
      "- ## Business logic boundaries",
      "- ## Testing expectations",
      "- ## Risky areas",
      "- ## Task scoping rules",
      "- ## Files/folders to avoid unless explicitly requested",
      "- ## Unknowns",
      "",
      "Repo context:",
      JSON.stringify(parsedInput.repoContext, null, 2),
      "",
      "Generated repo-analysis.md:",
      parsedInput.generatedDocs.repoAnalysis,
      "",
      "Generated architecture.md:",
      parsedInput.generatedDocs.architecture,
      "",
      "Generated conventions.md:",
      parsedInput.generatedDocs.conventions,
      "",
      "Generated business-logic.md:",
      parsedInput.generatedDocs.businessLogic,
      "",
      "Generated testing.md:",
      parsedInput.generatedDocs.testing,
    ].join("\n"),
  };
}
