import { z } from "zod";

import { RepoContextSchema } from "./repo-context";

export const GeneratedDocsContentSchema = z.object({
  repoAnalysis: z.string(),
  architecture: z.string(),
  conventions: z.string(),
  businessLogic: z.string(),
  testing: z.string(),
});

export const GenerateAgentRulesDocInputSchema = z.object({
  repoContext: RepoContextSchema,
  generatedDocs: GeneratedDocsContentSchema,
});

export type GeneratedDocsContent = z.infer<typeof GeneratedDocsContentSchema>;
export type GenerateAgentRulesDocInput = z.infer<
  typeof GenerateAgentRulesDocInputSchema
>;
