import { summarizeFileIndexForPrompt } from "../context-builder/file-index-summary";
import type { FileIndex } from "../models/file-index";
import type { ImportantFile } from "../models/important-file";
import type { RepoContext } from "../models/repo-context";

export interface KnowledgeDocGenerationInput {
  repoContext: RepoContext;
  fileIndex: FileIndex;
  fileIndexSummary: string;
  importantFiles: ImportantFile[];
}

export function buildKnowledgeDocGenerationInput(input: {
  repoContext: RepoContext;
  fileIndex: FileIndex;
  importantFiles: ImportantFile[];
}): KnowledgeDocGenerationInput {
  return {
    repoContext: input.repoContext,
    fileIndex: input.fileIndex,
    fileIndexSummary: summarizeFileIndexForPrompt(input.fileIndex),
    importantFiles: input.importantFiles,
  };
}
