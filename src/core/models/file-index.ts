import { z } from "zod";
import { RepoRelativePathSchema } from "./path";

export const FileIndexLanguageSchema = z.enum([
  "typescript",
  "javascript",
  "python",
  "markdown",
  "json",
  "yaml",
  "css",
  "html",
  "shell",
  "unknown",
]);

export const FileRoleSchema = z.enum([
  "source",
  "test",
  "fixture",
  "docs",
  "config",
  "project-config",
  "fixture-config",
  "lockfile",
  "planning-doc",
  "generated",
  "entrypoint-candidate",
  "command",
  "route",
  "api-route",
  "script",
  "model",
  "schema",
  "type",
  "service",
  "utility",
  "component",
  "builder",
  "generator",
  "resolver",
  "extractor",
  "reader",
  "writer",
  "migration",
]);

export const ConfidenceSchema = z.enum(["observed", "inferred", "ambiguous"]);

export const IncludeReasonSchema = z.enum([
  "source",
  "project-metadata",
  "documentation",
  "test",
  "fixture",
  "config",
  "script",
  "unknown",
]);

export const SkipReasonSchema = z.enum([
  "ignored",
  "sensitive",
  "binary",
  "too-large",
  "generated",
  "lockfile",
  "unsupported",
  "noise-directory",
]);

export const FileSignalSchema = z.object({
  kind: z.enum([
    "framework",
    "schema",
    "model",
    "validation",
    "cli",
    "testing",
    "database",
    "frontend",
    "entrypoint",
    "unknown",
  ]),
  source: z.enum(["import", "path", "package-json", "extension"]),
  value: z.string().min(1),
  confidence: ConfidenceSchema,
  reason: z.string().min(1),
});

export const FileIndexEntrySchema = z.object({
  path: RepoRelativePathSchema,
  extension: z.string().optional(),
  sizeBytes: z.number(),
  language: FileIndexLanguageSchema,
  roles: z.array(FileRoleSchema),
  confidence: ConfidenceSchema,
  includeReason: IncludeReasonSchema,
  signals: z.array(FileSignalSchema),
  reason: z.string().optional(),
  tags: z.array(z.string()),
});

export const SkippedFileSchema = z.object({
  path: RepoRelativePathSchema,
  reason: SkipReasonSchema,
  detail: z.string().optional(),
});

export const ScanWarningSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  filePath: RepoRelativePathSchema.optional(),
  severity: z.enum(["info", "warning"]),
});

export const FileIndexStatsSchema = z.object({
  totalFilesDiscovered: z.number().int().nonnegative(),
  includedFileCount: z.number().int().nonnegative(),
  skippedFileCount: z.number().int().nonnegative(),
  totalIncludedBytes: z.number().int().nonnegative(),
  byLanguage: z.partialRecord(
    FileIndexLanguageSchema,
    z.number().int().nonnegative(),
  ),
  byRole: z.partialRecord(FileRoleSchema, z.number().int().nonnegative()),
  bySkipReason: z.partialRecord(
    SkipReasonSchema,
    z.number().int().nonnegative(),
  ),
});

export const FileIndexSchema = z.object({
  schemaVersion: z.literal(2),
  generatedAt: z.iso.datetime(),
  files: z.array(FileIndexEntrySchema),
  skippedFiles: z.array(SkippedFileSchema),
  warnings: z.array(ScanWarningSchema),
  stats: FileIndexStatsSchema,
});

export type FileIndexLanguage = z.infer<typeof FileIndexLanguageSchema>;
export type FileRole = z.infer<typeof FileRoleSchema>;
export type Confidence = z.infer<typeof ConfidenceSchema>;
export type IncludeReason = z.infer<typeof IncludeReasonSchema>;
export type SkipReason = z.infer<typeof SkipReasonSchema>;
export type FileSignal = z.infer<typeof FileSignalSchema>;
export type SkippedFile = z.infer<typeof SkippedFileSchema>;
export type ScanWarning = z.infer<typeof ScanWarningSchema>;
export type FileIndexStats = z.infer<typeof FileIndexStatsSchema>;

type ValidatedFileIndexEntry = z.infer<typeof FileIndexEntrySchema>;
type ValidatedFileIndex = z.infer<typeof FileIndexSchema>;

export type FileIndexEntry = Omit<
  ValidatedFileIndexEntry,
  "language" | "roles" | "confidence" | "includeReason" | "signals"
> &
  Partial<
    Pick<
      ValidatedFileIndexEntry,
      "language" | "roles" | "confidence" | "includeReason" | "signals"
    >
  >;

export type FileIndex = Omit<
  ValidatedFileIndex,
  "schemaVersion" | "files" | "skippedFiles" | "warnings" | "stats"
> & {
  schemaVersion?: 2;
  files: FileIndexEntry[];
  skippedFiles?: SkippedFile[];
  warnings?: ScanWarning[];
  stats?: FileIndexStats;
};
