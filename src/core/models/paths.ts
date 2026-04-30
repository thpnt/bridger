import path from "node:path";
import { z } from "zod";

type Brand<K, T> = K & { readonly __brand: T };

export type AbsolutePath = Brand<string, "AbsolutePath">;
export type RepoRelativePath = Brand<string, "RepoRelativePath">;

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
