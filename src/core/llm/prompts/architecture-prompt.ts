import { summarizeFileIndexForPrompt } from "../../context-builder/file-index-summary";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
  type RepoKnowledgePrompt,
} from "../../models/repo-knowledge-doc";
import { formatImportantFilesForPrompt } from "./prompt-formatting";

export function buildArchitecturePrompt(
  input: GenerateRepoKnowledgeDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const fileIndexSummary = summarizeFileIndexForPrompt(parsedInput.fileIndex);

  return {
    system:
      "TODO: Final architecture prompt will be written manually. For now, generate grounded architecture documentation using only provided repository context.",
    prompt: [
      "TODO: Final architecture prompt placeholder.",
      "",
      "Required sections:",
      "- ## Project overview",
      "- ## Detected stack",
      "- ## App structure",
      "- ## Core domains",
      "- ## Important folders",
      "- ## Data flow assumptions",
      "- ## Commands",
      "- ## Risky areas",
      "- ## Unknowns",
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
