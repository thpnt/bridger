import { summarizeFileIndexForPrompt } from "../../context-builder/file-index-summary";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
  type RepoKnowledgePrompt,
} from "../../models/repo-knowledge-doc";
import { formatImportantFilesForPrompt } from "./prompt-formatting";

export function buildRepoAnalysisPrompt(
  input: GenerateRepoKnowledgeDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const fileIndexSummary = summarizeFileIndexForPrompt(parsedInput.fileIndex);

  return {
    system:
      "TODO: Final repo analysis prompt will be written manually. For now, generate grounded repo analysis using only provided repository context.",
    prompt: [
      "TODO: Final repo analysis prompt placeholder.",
      "",
      "Required sections:",
      "- ## Project overview",
      "- ## Detected stack",
      "- ## File and folder evidence",
      "- ## Important files",
      "- ## Observed structure",
      "- ## Observed domains",
      "- ## Assumptions",
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
