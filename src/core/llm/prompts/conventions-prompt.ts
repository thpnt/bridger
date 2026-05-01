import { summarizeFileIndexForPrompt } from "../../context-builder/file-index-summary";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
  type RepoKnowledgePrompt,
} from "../../models/repo-knowledge-doc";
import { formatImportantFilesForPrompt } from "./prompt-formatting";

export function buildConventionsPrompt(
  input: GenerateRepoKnowledgeDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const fileIndexSummary = summarizeFileIndexForPrompt(parsedInput.fileIndex);

  return {
    system:
      "TODO: Final coding conventions prompt will be written manually. For now, generate grounded conventions documentation using only provided repository context.",
    prompt: [
      "TODO: Final conventions prompt placeholder.",
      "",
      "Required sections:",
      "- ## TypeScript conventions",
      "- ## Component conventions",
      "- ## Server/client boundary conventions",
      "- ## Validation conventions",
      "- ## Styling conventions",
      "- ## Data access conventions",
      "- ## Testing conventions",
      "- ## Naming conventions",
      "- ## Observed conventions",
      "- ## Recommended conventions",
      "- ## Things agents should avoid",
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
