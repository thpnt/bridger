import { z } from "zod";

export const RepoGraphNodeKindSchema = z.enum(["file", "directory"]);

export const RepoGraphEdgeTypeSchema = z.enum(["contains", "imports"]);

export const RepoGraphEdgeConfidenceSchema = z.enum(["high", "medium", "low"]);

export const RepoGraphEdgeSourceSchema = z.enum([
  "filesystem",
  "typescript-js-imports",
  "python-imports",
]);

export const RepoGraphDiagnosticLevelSchema = z.enum(["info", "warning"]);

export const RepoGraphDiagnosticCodeSchema = z.enum([
  "unresolved-import",
  "unsupported-language",
  "skipped-large-file",
  "ambiguous-import",
  "read-error",
]);

export const RepoGraphLanguageSchema = z.enum([
  "typescript",
  "javascript",
  "python",
  "markdown",
  "json",
  "unknown",
]);

export const RepoGraphNodeTagSchema = z.enum([
  "root",
  "config",
  "docs",
  "source",
  "test",
  "entrypoint-candidate",
  "component",
  "service",
  "utility",
  "route",
  "api-route",
]);

export const RepoGraphNodeSchema = z.object({
  id: z.string().min(1),
  path: z.string().min(1),
  kind: RepoGraphNodeKindSchema,
  extension: z.string().nullable(),
  language: RepoGraphLanguageSchema,
  sizeBytes: z.number().int().nonnegative(),
  tags: z.array(RepoGraphNodeTagSchema),
});

export const RepoGraphEdgeSchema = z.object({
  from: z.string().min(1),
  to: z.string().min(1),
  type: RepoGraphEdgeTypeSchema,
  confidence: RepoGraphEdgeConfidenceSchema,
  source: RepoGraphEdgeSourceSchema,
  importSpecifier: z.string().min(1).optional(),
});

export const RepoGraphDiagnosticSchema = z.object({
  level: RepoGraphDiagnosticLevelSchema,
  code: RepoGraphDiagnosticCodeSchema,
  file: z.string().min(1).optional(),
  message: z.string().min(1),
});

export const RepoGraphStatsSchema = z.object({
  fileCount: z.number().int().nonnegative(),
  directoryCount: z.number().int().nonnegative(),
  containsEdgeCount: z.number().int().nonnegative(),
  importEdgeCount: z.number().int().nonnegative(),
  unresolvedImportCount: z.number().int().nonnegative(),
  supportedLanguageFileCount: z.number().int().nonnegative(),
});

export const RepoGraphSchema = z.object({
  generatedAt: z.iso.datetime(),
  graphVersion: z.literal(1),
  repoRoot: z.string().min(1),
  nodes: z.array(RepoGraphNodeSchema),
  edges: z.array(RepoGraphEdgeSchema),
  diagnostics: z.array(RepoGraphDiagnosticSchema),
  stats: RepoGraphStatsSchema,
});

export type RepoGraphNodeKind = z.infer<typeof RepoGraphNodeKindSchema>;
export type RepoGraphEdgeType = z.infer<typeof RepoGraphEdgeTypeSchema>;
export type RepoGraphEdgeConfidence = z.infer<
  typeof RepoGraphEdgeConfidenceSchema
>;
export type RepoGraphEdgeSource = z.infer<typeof RepoGraphEdgeSourceSchema>;
export type RepoGraphDiagnosticLevel = z.infer<
  typeof RepoGraphDiagnosticLevelSchema
>;
export type RepoGraphDiagnosticCode = z.infer<
  typeof RepoGraphDiagnosticCodeSchema
>;
export type RepoGraphLanguage = z.infer<typeof RepoGraphLanguageSchema>;
export type RepoGraphNodeTag = z.infer<typeof RepoGraphNodeTagSchema>;

export type RepoGraphNode = z.infer<typeof RepoGraphNodeSchema>;
export type RepoGraphEdge = z.infer<typeof RepoGraphEdgeSchema>;
export type RepoGraphDiagnostic = z.infer<typeof RepoGraphDiagnosticSchema>;
export type RepoGraphStats = z.infer<typeof RepoGraphStatsSchema>;
export type RepoGraph = z.infer<typeof RepoGraphSchema>;
