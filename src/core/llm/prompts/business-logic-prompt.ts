import { summarizeFileIndexForPrompt } from "../../context-builder/file-index-summary";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
  type RepoKnowledgePrompt,
} from "../../models/repo-knowledge-doc";
import { formatImportantFilesForPrompt } from "./prompt-formatting";

export function buildBusinessLogicPrompt(
  input: GenerateRepoKnowledgeDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const fileIndexSummary = summarizeFileIndexForPrompt(parsedInput.fileIndex);

  return {
    system:
      "TODO: Final business logic prompt will be written manually. For now, generate grounded business logic documentation using only provided repository context.",
    prompt: [
      "TODO: Final business logic prompt placeholder.",
      "",
      "Required sections:",
      "- ## Product/domain overview",
      "- ## Observed domain concepts",
      "- ## Observed entities and models",
      "- ## Observed business rules",
      "- ## Observed workflows",
      "- ## Data ownership and persistence",
      "- ## External integrations",
      "- ## Assumptions",
      "- ## Unknowns",
      "- ## Evidence map",
      "",
      "Repo context:",
      JSON.stringify(parsedInput.repoContext, null, 2),
      "",
      "File index summary:",
      fileIndexSummary,
      "",
      "Important files:",
      formatImportantFilesForPrompt(parsedInput.importantFiles),
    ].join("\n"),
  };
}
