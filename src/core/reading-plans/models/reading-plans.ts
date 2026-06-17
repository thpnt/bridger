import { z } from "zod";

import { ConfidenceSchema } from "../../models/file-index";

export const ReadingPlanKindSchema = z.enum([
  "repo-analysis",
  "architecture",
  "business-logic",
  "conventions",
  "testing",
  "agent-rules",
]);

export const ReadingPlanFileRoleSchema = z.enum([
  "orientation",
  "entrypoint",
  "cluster-central-file",
  "contract",
  "schema",
  "model",
  "service",
  "route",
  "utility",
  "test-setup",
  "representative-test",
  "fixture",
  "config",
  "convention-example",
  "risk-signal",
  "supporting-context",
]);

export const ReadingPlanEvidenceSchema = z.object({
  source: z.enum([
    "file-index",
    "repo-context",
    "repo-graph",
    "graph-summary",
    "codebase-map",
  ]),
  detail: z.string().min(1),
});

export const ReadingPlanFileSchema = z.object({
  path: z.string().min(1),
  roleInBatch: ReadingPlanFileRoleSchema,
  reason: z.string().min(1),
  evidence: z.array(ReadingPlanEvidenceSchema).min(1),
  confidence: ConfidenceSchema,
  estimatedBytes: z.number().int().nonnegative(),
});

export const ReadingPlanWarningSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  planKind: ReadingPlanKindSchema.optional(),
  batchId: z.string().min(1).optional(),
  path: z.string().min(1).optional(),
  severity: z.enum(["info", "warning"]),
});

const ReadingBudgetSchema = z.object({
  maxFiles: z.number().int().positive(),
  estimatedBytes: z.number().int().nonnegative(),
  truncated: z.boolean(),
});

export const ReadingBatchSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  purpose: z.string().min(1),
  order: z.number().int().positive(),
  selectionRule: z.string().min(1),
  files: z.array(ReadingPlanFileSchema),
  budget: ReadingBudgetSchema,
});

export const ReadingPlanSchema = z.object({
  kind: ReadingPlanKindSchema,
  targetMemoryFile: z.string().min(1),
  title: z.string().min(1),
  purpose: z.string().min(1),
  inputStrategy: z.object({
    agentFocus: z.string().min(1),
    shouldAnswer: z.array(z.string().min(1)),
    shouldAvoid: z.array(z.string().min(1)),
  }),
  batches: z.array(ReadingBatchSchema),
  budget: ReadingBudgetSchema,
  warnings: z.array(ReadingPlanWarningSchema),
});

export const ReadingPlansStatsSchema = z.object({
  planCount: z.number().int().nonnegative(),
  batchCount: z.number().int().nonnegative(),
  uniqueFileCount: z.number().int().nonnegative(),
  repeatedFileReferences: z.number().int().nonnegative(),
  estimatedTotalBytes: z.number().int().nonnegative(),
});

export const ReadingPlansSchema = z.object({
  schemaVersion: z.literal(1),
  generatedAt: z.iso.datetime(),
  sourceArtifacts: z.object({
    fileIndexSchemaVersion: z.number().int().positive().optional(),
    repoGraphVersion: z.union([z.string(), z.number()]).optional(),
    graphSummaryVersion: z.union([z.string(), z.number()]).optional(),
    codebaseMapSchemaVersion: z.number().int().positive().optional(),
  }),
  plans: z.array(ReadingPlanSchema).length(6),
  stats: ReadingPlansStatsSchema,
  warnings: z.array(ReadingPlanWarningSchema),
});

export type ReadingPlanKind = z.infer<typeof ReadingPlanKindSchema>;
export type ReadingPlanFileRole = z.infer<typeof ReadingPlanFileRoleSchema>;
export type ReadingPlanEvidence = z.infer<typeof ReadingPlanEvidenceSchema>;
export type ReadingPlanFile = z.infer<typeof ReadingPlanFileSchema>;
export type ReadingPlanWarning = z.infer<typeof ReadingPlanWarningSchema>;
export type ReadingBatch = z.infer<typeof ReadingBatchSchema>;
export type ReadingPlan = z.infer<typeof ReadingPlanSchema>;
export type ReadingPlansStats = z.infer<typeof ReadingPlansStatsSchema>;
export type ReadingPlans = z.infer<typeof ReadingPlansSchema>;
