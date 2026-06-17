import { z } from "zod";

import { ConfidenceSchema } from "../../models/file-index";

export const AffectedTraversalRelationSchema = z.enum([
  "dependency",
  "consumer",
  "test",
  "same-cluster",
  "entrypoint-consumer",
]);

export const AffectedTraversalDiagnosticSchema = z.object({
  code: z.enum([
    "seed-file-not-found",
    "seed-file-not-in-codebase-map",
    "max-related-files-reached",
    "no-related-files-found",
  ]),
  message: z.string().min(1),
  path: z.string().min(1).optional(),
  severity: z.enum(["info", "warning"]),
});

export const AffectedFileCandidateSchema = z.object({
  path: z.string().min(1),
  relation: AffectedTraversalRelationSchema,
  distance: z.number().int().positive().optional(),
  score: z.number().int(),
  reasons: z.array(z.string().min(1)).min(1),
  confidence: ConfidenceSchema,
});

export const AffectedTraversalResultSchema = z.object({
  seedFiles: z.array(z.string().min(1)),
  relatedFiles: z.array(AffectedFileCandidateSchema),
  diagnostics: z.array(AffectedTraversalDiagnosticSchema),
});

export type AffectedTraversalRelation = z.infer<
  typeof AffectedTraversalRelationSchema
>;
export type AffectedTraversalDiagnostic = z.infer<
  typeof AffectedTraversalDiagnosticSchema
>;
export type AffectedFileCandidate = z.infer<typeof AffectedFileCandidateSchema>;
export type AffectedTraversalResult = z.infer<
  typeof AffectedTraversalResultSchema
>;
