import { z } from "zod";

import { RepoGraphStatsSchema } from "./repo-graph";

export const GraphSummaryRankedFileSchema = z.object({
  path: z.string().min(1),
  count: z.number().int().nonnegative(),
  reason: z.string().min(1),
});

export const GraphSummarySchema = z.object({
  generatedAt: z.iso.datetime(),
  graphVersion: z.literal(1),
  entrypoints: z.array(z.string().min(1)),
  rootFiles: z.array(z.string().min(1)),
  configFiles: z.array(z.string().min(1)),
  docsFiles: z.array(z.string().min(1)),
  highFanInFiles: z.array(GraphSummaryRankedFileSchema),
  highFanOutFiles: z.array(GraphSummaryRankedFileSchema),
  leafFiles: z.array(z.string().min(1)),
  isolatedFiles: z.array(z.string().min(1)),
  architectureFirstOrder: z.array(z.string().min(1)),
  dependencyFirstOrder: z.array(z.string().min(1)),
  stats: RepoGraphStatsSchema,
});

export type GraphSummaryRankedFile = z.infer<
  typeof GraphSummaryRankedFileSchema
>;

export type GraphSummary = z.infer<typeof GraphSummarySchema>;
