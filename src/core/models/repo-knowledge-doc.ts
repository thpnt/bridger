import { z } from "zod";

import { FileIndexSchema } from "./file-index";
import { ImportantFilesSchema } from "./important-file";
import { RepoContextSchema } from "./repo-context";

export const GenerateRepoKnowledgeDocInputSchema = z.object({
  repoContext: RepoContextSchema,
  fileIndex: FileIndexSchema,
  importantFiles: ImportantFilesSchema,
});

export const RepoKnowledgePromptSchema = z.object({
  system: z.string(),
  prompt: z.string(),
});

export type GenerateRepoKnowledgeDocInput = z.infer<
  typeof GenerateRepoKnowledgeDocInputSchema
>;
export type RepoKnowledgePrompt = z.infer<typeof RepoKnowledgePromptSchema>;
