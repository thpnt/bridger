import { z } from "zod";

import {
  ConfidenceSchema,
  FileIndexLanguageSchema,
  FileRoleSchema,
  FileSignalSchema,
} from "../../models/file-index";

const CountRecordSchema = z.record(z.string(), z.number().int().nonnegative());

export const EntrypointKindSchema = z.enum([
  "node-cli",
  "cli-command",
  "package-bin",
  "next-page",
  "next-route",
  "vite-react",
  "python-script",
  "fastapi-app",
  "django-app",
  "script",
  "job",
  "unknown",
]);

export const EntrypointCandidateSchema = z.object({
  path: z.string().min(1),
  kind: EntrypointKindSchema,
  framework: z.string().min(1).optional(),
  confidence: ConfidenceSchema,
  reasons: z.array(z.string().min(1)),
});

export const ClusterCentralFileSchema = z.object({
  path: z.string().min(1),
  fanIn: z.number().int().nonnegative(),
  fanOut: z.number().int().nonnegative(),
  reasons: z.array(z.string().min(1)),
});

export const ClusterRelationSchema = z.object({
  clusterId: z.string().min(1),
  fileCount: z.number().int().positive(),
  reasons: z.array(z.string().min(1)),
});

export const CodebaseClusterSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  rootPath: z.string().min(1),
  kind: z.enum([
    "source",
    "test",
    "docs",
    "config",
    "scripts",
    "mixed",
    "unknown",
  ]),
  files: z.array(z.string().min(1)),
  roles: CountRecordSchema,
  entrypoints: z.array(z.string().min(1)),
  centralFiles: z.array(ClusterCentralFileSchema),
  tests: z.array(z.string().min(1)),
  fixtures: z.array(z.string().min(1)),
  dependencies: z.array(ClusterRelationSchema),
  consumers: z.array(ClusterRelationSchema),
  confidence: ConfidenceSchema,
  reasons: z.array(z.string().min(1)),
  warnings: z.array(z.string().min(1)),
});

export const CodebaseMapFileSchema = z.object({
  path: z.string().min(1),
  language: FileIndexLanguageSchema,
  roles: z.array(FileRoleSchema),
  signals: z.array(FileSignalSchema),
  clusterId: z.string().min(1).optional(),
  fanIn: z.number().int().nonnegative(),
  fanOut: z.number().int().nonnegative(),
  isCentral: z.boolean(),
  isEntrypoint: z.boolean(),
  isTest: z.boolean(),
  isFixture: z.boolean(),
});

export const CodebaseMapStatsSchema = z.object({
  fileCount: z.number().int().nonnegative(),
  sourceFileCount: z.number().int().nonnegative(),
  testFileCount: z.number().int().nonnegative(),
  fixtureFileCount: z.number().int().nonnegative(),
  docsFileCount: z.number().int().nonnegative(),
  configFileCount: z.number().int().nonnegative(),
  clusterCount: z.number().int().nonnegative(),
  entrypointCount: z.number().int().nonnegative(),
  centralFileCount: z.number().int().nonnegative(),
  unresolvedImportCount: z.number().int().nonnegative(),
});

export const CodebaseSignalSummarySchema = z.object({
  frameworks: CountRecordSchema,
  schemas: CountRecordSchema,
  validation: CountRecordSchema,
  cli: CountRecordSchema,
  testing: CountRecordSchema,
  database: CountRecordSchema,
});

export const UnresolvedImportSummarySchema = z.object({
  count: z.number().int().nonnegative(),
  byFile: z.array(
    z.object({
      path: z.string().min(1),
      count: z.number().int().positive(),
    }),
  ),
});

export const CodebaseMapSchema = z.object({
  schemaVersion: z.literal(1),
  generatedAt: z.iso.datetime(),
  repo: z.object({
    name: z.string().min(1),
    packageManager: z.string().min(1).optional(),
    detectedStack: z.array(z.string().min(1)),
  }),
  stats: CodebaseMapStatsSchema,
  entrypoints: z.array(EntrypointCandidateSchema),
  clusters: z.array(CodebaseClusterSchema),
  files: z.array(CodebaseMapFileSchema),
  signals: CodebaseSignalSummarySchema,
  unresolvedImports: UnresolvedImportSummarySchema,
  warnings: z.array(z.string().min(1)),
});

export type EntrypointCandidate = z.infer<typeof EntrypointCandidateSchema>;
export type ClusterCentralFile = z.infer<typeof ClusterCentralFileSchema>;
export type ClusterRelation = z.infer<typeof ClusterRelationSchema>;
export type CodebaseCluster = z.infer<typeof CodebaseClusterSchema>;
export type CodebaseMapFile = z.infer<typeof CodebaseMapFileSchema>;
export type CodebaseMapStats = z.infer<typeof CodebaseMapStatsSchema>;
export type CodebaseSignalSummary = z.infer<
  typeof CodebaseSignalSummarySchema
>;
export type UnresolvedImportSummary = z.infer<
  typeof UnresolvedImportSummarySchema
>;
export type CodebaseMap = z.infer<typeof CodebaseMapSchema>;
