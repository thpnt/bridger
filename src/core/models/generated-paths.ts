import path from "node:path";

import { z } from "zod";

import { GENERATED_DOC_FILENAMES } from "../doc-generator/doc-filenames";
import type { KnowledgeDocKey } from "../doc-generator/doc-types";

type Brand<K, T> = K & { readonly __brand: T };

export type AbsolutePath = Brand<string, "AbsolutePath">;
export type RepoRelativePath = Brand<string, "RepoRelativePath">;

export const BRIDGER_DIRNAME = ".bridger";
export const GENERATED_DIRNAME = "generated";
export const TICKETS_DIRNAME = "tickets";

export const REPO_CONTEXT_FILENAME = "repo-context.json";
export const FILE_INDEX_FILENAME = "file-index.json";
export const AGENTS_GENERATED_FILENAME = "AGENTS.generated.md";
export const AGENTS_MD_FILENAME = "AGENTS.md";
export const TICKET_TEMPLATE_FILENAME = "ticket-template.md";

export const AbsolutePathSchema = z
  .string()
  .min(1)
  .refine((value) => path.isAbsolute(value), {
    message: "Expected an absolute path",
  })
  .transform((value) => path.normalize(value) as AbsolutePath);

export const RepoRelativePathSchema = z
  .string()
  .min(1)
  .refine((value) => !path.isAbsolute(value), {
    message: "Expected a repo-relative path, not an absolute path",
  })
  .refine((value) => !value.startsWith(".."), {
    message: "Repo-relative path must not escape the repo root",
  })
  .refine((value) => !value.includes(`..${path.sep}`), {
    message: "Repo-relative path must not contain parent traversal",
  })
  .transform((value) => value.replaceAll("\\", "/") as RepoRelativePath);

export function toRepoRelativePath(
  repoRoot: AbsolutePath,
  absoluteFilePath: string,
): RepoRelativePath {
  const relativePath = path.relative(repoRoot, absoluteFilePath);

  return RepoRelativePathSchema.parse(relativePath);
}

export function resolveRepoPath(
  repoRoot: AbsolutePath,
  relativePath: RepoRelativePath,
): AbsolutePath {
  const resolvedPath = path.resolve(repoRoot, relativePath);

  if (!resolvedPath.startsWith(repoRoot)) {
    throw new Error(`Path escapes repo root: ${relativePath}`);
  }

  return resolvedPath as AbsolutePath;
}

export function normalizeRepoRelativePath(value: string): string {
  return value.replaceAll("\\", "/");
}

export interface GeneratedDocPaths {
  repoAnalysisPath: RepoRelativePath;
  architecturePath: RepoRelativePath;
  businessLogicPath: RepoRelativePath;
  conventionsPath: RepoRelativePath;
  testingPath: RepoRelativePath;
  agentRulesPath: RepoRelativePath;
}

export function getGeneratedKnowledgeDocRelativePath(
  key: KnowledgeDocKey,
): RepoRelativePath {
  return RepoRelativePathSchema.parse(
    [BRIDGER_DIRNAME, GENERATED_DIRNAME, GENERATED_DOC_FILENAMES[key]].join(
      "/",
    ),
  );
}

export function getTicketTemplateRelativePath(): RepoRelativePath {
  return RepoRelativePathSchema.parse(
    [BRIDGER_DIRNAME, GENERATED_DIRNAME, TICKET_TEMPLATE_FILENAME].join("/"),
  );
}

export function buildGeneratedDocPaths(): GeneratedDocPaths {
  return {
    repoAnalysisPath: getGeneratedKnowledgeDocRelativePath("repoAnalysis"),
    architecturePath: getGeneratedKnowledgeDocRelativePath("architecture"),
    businessLogicPath: getGeneratedKnowledgeDocRelativePath("businessLogic"),
    conventionsPath: getGeneratedKnowledgeDocRelativePath("conventions"),
    testingPath: getGeneratedKnowledgeDocRelativePath("testing"),
    agentRulesPath: getGeneratedKnowledgeDocRelativePath("agentRules"),
  };
}
