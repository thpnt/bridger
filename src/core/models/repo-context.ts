import { z } from "zod";

import {
  RepoRelativePathSchema,
  type RepoRelativePath,
} from "./path";
import type { GeneratedDocPaths } from "../project/bridger-paths";

export const RepoContextStackSchema = z.object({
  framework: z.string(),
  language: z.string(),
  packageManager: z.string(),
  styling: z.array(z.string()),
  validation: z.array(z.string()),
  database: z.array(z.string()),
  testFramework: z.array(z.string()),
});

export const RepoContextCommandsSchema = z.object({
  install: z.string().optional(),
  dev: z.string().optional(),
  build: z.string().optional(),
  lint: z.string().optional(),
  typecheck: z.string().optional(),
  test: z.string().optional(),
  format: z.string().optional(),
});

export const RepoContextImportantFileSchema = z.object({
  path: z.string(),
  reason: z.string(),
});

export const RepoContextGeneratedDocsSchema = z.object({
  repoAnalysisPath: RepoRelativePathSchema,
  architecturePath: RepoRelativePathSchema,
  conventionsPath: RepoRelativePathSchema,
  businessLogicPath: RepoRelativePathSchema,
  testingPath: RepoRelativePathSchema,
  agentRulesPath: RepoRelativePathSchema,
  ticketTemplatePath: RepoRelativePathSchema,
});

export const RepoContextSchema = z.object({
  repoRoot: z.string(),
  generatedAt: z.iso.datetime(),
  stack: RepoContextStackSchema,
  commands: RepoContextCommandsSchema,
  importantFiles: z.array(RepoContextImportantFileSchema),
  generatedDocs: RepoContextGeneratedDocsSchema,
});

export type RepoContextStack = z.infer<typeof RepoContextStackSchema>;
export type RepoContextCommands = z.infer<typeof RepoContextCommandsSchema>;
export type RepoContextImportantFile = z.infer<
  typeof RepoContextImportantFileSchema
>;
export type RepoContextGeneratedDocs = GeneratedDocPaths & {
  ticketTemplatePath: RepoRelativePath;
};
export type RepoContext = z.infer<typeof RepoContextSchema>;
