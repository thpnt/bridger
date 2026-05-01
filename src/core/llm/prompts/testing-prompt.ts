import { summarizeFileIndexForPrompt } from "../../context-builder/file-index-summary";
import {
  GenerateRepoKnowledgeDocInputSchema,
  type GenerateRepoKnowledgeDocInput,
  type RepoKnowledgePrompt,
} from "../../models/repo-knowledge-doc";
import { formatImportantFilesForPrompt } from "./prompt-formatting";

export function buildTestingPrompt(
  input: GenerateRepoKnowledgeDocInput,
): RepoKnowledgePrompt {
  const parsedInput = GenerateRepoKnowledgeDocInputSchema.parse(input);
  const fileIndexSummary = summarizeFileIndexForPrompt(parsedInput.fileIndex);

  return {
    system:
      "TODO: Final testing profile prompt will be written manually. For now, generate grounded testing documentation using only provided repository context.",
    prompt: [
      "TODO: Final testing profile prompt placeholder.",
      "",
      "The final prompt should help agents understand what should be tested when implementing new work, what test types are expected, and what testing conventions are visible in this repo.",
      "",
      "Required sections:",
      "- ## Testing philosophy",
      "- ## Test types and when to use them",
      "- ## Unit testing conventions",
      "- ## Integration testing conventions",
      "- ## Regression testing conventions",
      "- ## Component and UI testing conventions",
      "- ## Manual QA expectations",
      "- ## Existing test evidence",
      "- ## Testing gaps and unknowns",
      "- ## Things agents should avoid",
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
