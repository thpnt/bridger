import fg from "fast-glob";
import fs from "fs-extra";
import path from "node:path";

import { FileIndexSchema } from "../models/file-index";
import { RepoRelativePathSchema } from "../models/paths";
import type { FileIndex } from "../models/file-index";
import { createGitignoreFilter } from "./gitignore";

const ALWAYS_EXCLUDE_PATTERNS = [
  "**/node_modules/**",
  "**/.next/**",
  "**/dist/**",
  "**/build/**",
  "**/coverage/**",
  "**/.git/**",
  "**/.bridger/**",
  "**/.agents/**",
  "**/.env",
  "**/.env.*",
  "**/*.png",
  "**/*.jpg",
  "**/*.jpeg",
  "**/*.gif",
  "**/*.webp",
  "**/*.svg",
  "**/*.ico",
  "**/*.mp4",
  "**/*.mov",
  "**/*.woff",
  "**/*.woff2",
  "**/*.ttf",
  "**/*.pdf",
  "**/*.zip",
  "**/*.tar",
  "**/*.gz",
  "**/*.sqlite",
  "**/*.db",
];

function toPosixPath(value: string): string {
  return value.replaceAll(path.sep, "/");
}

function uniqueTags(tags: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const tag of tags) {
    if (seen.has(tag)) {
      continue;
    }

    seen.add(tag);
    result.push(tag);
  }

  return result;
}

function hasPathPrefix(relativePath: string, prefix: string): boolean {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}

function hasFileName(relativePath: string, fileName: string): boolean {
  return path.posix.basename(relativePath) === fileName;
}

function getFileTags(relativePath: string): string[] {
  const tags: string[] = [];

  if (hasFileName(relativePath, "README.md")) {
    tags.push("readme", "documentation", "important");
  }

  if (
    hasFileName(relativePath, "AGENTS.md") ||
    hasFileName(relativePath, "CLAUDE.md")
  ) {
    tags.push("agent-rules", "important");
  }

  if (hasFileName(relativePath, "package.json")) {
    tags.push("package", "config", "important");
  }

  if (hasFileName(relativePath, "tsconfig.json")) {
    tags.push("typescript", "config");
  }

  if (hasFileName(relativePath, "components.json")) {
    tags.push("shadcn", "config");
  }

  if (relativePath.startsWith("next.config.")) {
    tags.push("nextjs", "config");
  }

  if (relativePath.startsWith("tailwind.config.")) {
    tags.push("tailwind", "config");
  }

  if (relativePath.startsWith("drizzle.config.")) {
    tags.push("drizzle", "database", "config");
  }

  if (hasPathPrefix(relativePath, "docs")) {
    tags.push("documentation");
  }

  if (hasPathPrefix(relativePath, "app")) {
    tags.push("app", "route");
  }

  if (hasPathPrefix(relativePath, "pages")) {
    tags.push("pages", "route");
  }

  if (hasPathPrefix(relativePath, "src")) {
    tags.push("src");
  }

  if (hasPathPrefix(relativePath, "src/app")) {
    tags.push("src", "app", "route");
  }

  if (hasPathPrefix(relativePath, "components")) {
    tags.push("components", "ui");
  }

  if (hasPathPrefix(relativePath, "src/components")) {
    tags.push("src", "components", "ui");
  }

  if (hasPathPrefix(relativePath, "lib")) {
    tags.push("lib");
  }

  if (hasPathPrefix(relativePath, "src/lib")) {
    tags.push("src", "lib");
  }

  if (hasPathPrefix(relativePath, "server")) {
    tags.push("server");
  }

  if (hasPathPrefix(relativePath, "src/server")) {
    tags.push("src", "server");
  }

  if (hasPathPrefix(relativePath, "db")) {
    tags.push("database");
  }

  if (hasPathPrefix(relativePath, "src/db")) {
    tags.push("src", "database");
  }

  if (hasPathPrefix(relativePath, "supabase")) {
    tags.push("supabase", "database");
  }

  if (hasPathPrefix(relativePath, "prisma")) {
    tags.push("prisma", "database");
  }

  if (hasPathPrefix(relativePath, "drizzle")) {
    tags.push("drizzle", "database");
  }

  const extension = path.posix.extname(relativePath);

  if (extension === ".ts") {
    tags.push("typescript");
  }

  if (extension === ".tsx") {
    tags.push("typescript", "react");
  }

  if (extension === ".js") {
    tags.push("javascript");
  }

  if (extension === ".jsx") {
    tags.push("javascript", "react");
  }

  if (extension === ".md") {
    tags.push("markdown");
  }

  if (extension === ".mdx") {
    tags.push("markdown", "react");
  }

  if (extension === ".json") {
    tags.push("json");
  }

  if (extension === ".css" || extension === ".scss") {
    tags.push("style");
  }

  if (extension === ".sql") {
    tags.push("database", "sql");
  }

  return uniqueTags(tags);
}

function getFileReason(relativePath: string): string | undefined {
  if (hasFileName(relativePath, "README.md")) {
    return "Project README";
  }

  if (hasFileName(relativePath, "AGENTS.md")) {
    return "Agent instruction file";
  }

  if (hasFileName(relativePath, "CLAUDE.md")) {
    return "Claude agent instruction file";
  }

  if (hasFileName(relativePath, "package.json")) {
    return "Package manifest and scripts/dependencies source";
  }

  if (hasFileName(relativePath, "tsconfig.json")) {
    return "TypeScript configuration";
  }

  if (hasFileName(relativePath, "components.json")) {
    return "shadcn/ui component configuration";
  }

  if (relativePath.startsWith("next.config.")) {
    return "Next.js configuration";
  }

  if (relativePath.startsWith("tailwind.config.")) {
    return "Tailwind CSS configuration";
  }

  if (relativePath.startsWith("drizzle.config.")) {
    return "Drizzle configuration";
  }

  if (hasPathPrefix(relativePath, "docs")) {
    return "Project documentation";
  }

  if (
    hasPathPrefix(relativePath, "app") ||
    hasPathPrefix(relativePath, "src/app")
  ) {
    return "Application route file";
  }

  if (hasPathPrefix(relativePath, "pages")) {
    return "Pages router file";
  }

  if (
    hasPathPrefix(relativePath, "components") ||
    hasPathPrefix(relativePath, "src/components")
  ) {
    return "UI component file";
  }

  if (
    hasPathPrefix(relativePath, "lib") ||
    hasPathPrefix(relativePath, "src/lib")
  ) {
    return "Library/helper file";
  }

  if (
    hasPathPrefix(relativePath, "server") ||
    hasPathPrefix(relativePath, "src/server")
  ) {
    return "Server-side code file";
  }

  if (
    hasPathPrefix(relativePath, "db") ||
    hasPathPrefix(relativePath, "src/db")
  ) {
    return "Database-related file";
  }

  if (hasPathPrefix(relativePath, "supabase")) {
    return "Supabase-related file";
  }

  if (hasPathPrefix(relativePath, "prisma")) {
    return "Prisma-related file";
  }

  if (hasPathPrefix(relativePath, "drizzle")) {
    return "Drizzle-related file";
  }

  return undefined;
}

export async function buildFileIndex(repoRoot: string): Promise<FileIndex> {
  const gitignoreFilter = await createGitignoreFilter(repoRoot);
  const discoveredPaths = await fg("**/*", {
    cwd: repoRoot,
    onlyFiles: true,
    dot: true,
    ignore: ALWAYS_EXCLUDE_PATTERNS,
    followSymbolicLinks: false,
  });

  const includedPaths = discoveredPaths
    .map(toPosixPath)
    .filter(gitignoreFilter)
    .sort((left, right) => left.localeCompare(right));

  const files: FileIndex["files"] = [];

  for (const relativePath of includedPaths) {
    const absolutePath = path.join(repoRoot, relativePath);
    const stats = await fs.stat(absolutePath);
    const extension = path.posix.extname(relativePath);

    files.push({
      path: RepoRelativePathSchema.parse(relativePath),
      extension: extension || undefined,
      sizeBytes: stats.size,
      tags: getFileTags(relativePath),
      reason: getFileReason(relativePath),
    });
  }

  return FileIndexSchema.parse({
    generatedAt: new Date().toISOString(),
    files,
  });
}
