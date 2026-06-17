import fg from "fast-glob";
import fs from "fs-extra";
import path from "node:path";

import { FileIndexSchema } from "../models/file-index";
import { RepoRelativePathSchema } from "../models/path";
import type {
  FileIndex,
  FileIndexEntry,
  FileIndexLanguage,
  FileRole,
  ScanWarning,
  SkipReason,
  SkippedFile,
} from "../models/file-index";
import {
  detectFileLanguage,
  getFileConfidence,
  getFileRoles,
  getIncludeReason,
  uniqueSortedRoles,
} from "./file-classification";
import {
  getFileSignals,
  readPackageBinPaths,
} from "./file-signals";
import { createGitignoreFilter } from "./gitignore";

const NOISE_DIRECTORY_PATTERNS = [
  "**/node_modules/**",
  "**/.next/**",
  "**/dist/**",
  "**/build/**",
  "**/coverage/**",
  "**/.git/**",
  "**/.bridger/**",
  "**/.agents/**",
];

const NOISE_DIRECTORIES = new Set([
  "node_modules",
  ".git",
  ".bridger",
  ".agents",
  "dist",
  "build",
  "coverage",
  ".next",
]);

const GENERATED_DIRECTORIES = new Set(["dist", "build", "coverage", ".next"]);

const BINARY_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".ico",
  ".mp4",
  ".mov",
  ".woff",
  ".woff2",
  ".ttf",
  ".pdf",
  ".zip",
  ".tar",
  ".gz",
  ".sqlite",
  ".db",
]);

const LOCKFILE_NAMES = new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb",
]);

const MAX_INDEXED_FILE_BYTES = 1_000_000;

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
  const packageBinPaths = await readPackageBinPaths(repoRoot);
  const discoveredPaths = await fg("**/*", {
    cwd: repoRoot,
    onlyFiles: true,
    dot: true,
    ignore: NOISE_DIRECTORY_PATTERNS,
    followSymbolicLinks: false,
  });

  const skippedFiles: SkippedFile[] = await getSkippedNoiseDirectories(repoRoot);
  const files: FileIndexEntry[] = [];

  for (const relativePath of discoveredPaths
    .map(toPosixPath)
    .sort((left, right) => left.localeCompare(right))) {
    const absolutePath = path.join(repoRoot, relativePath);
    const stats = await fs.stat(absolutePath);
    const extension = path.posix.extname(relativePath);
    const skipReason = getSkipReason({
      relativePath,
      sizeBytes: stats.size,
      gitignoreFilter,
    });

    if (skipReason) {
      skippedFiles.push({
        path: RepoRelativePathSchema.parse(relativePath),
        reason: skipReason.reason,
        detail: skipReason.detail,
      });
      continue;
    }

    const tags = getFileTags(relativePath);
    const language = detectFileLanguage(relativePath, extension || undefined);
    const roles = getFileRoles(relativePath, tags);
    const rolesWithEntrypoint = packageBinPaths.has(relativePath)
      ? uniqueSortedRoles([...roles, "entrypoint-candidate"])
      : roles;
    const signals = await getFileSignals({
      repoRoot,
      relativePath,
      sizeBytes: stats.size,
      packageBinPaths,
    });

    files.push({
      path: RepoRelativePathSchema.parse(relativePath),
      extension: extension || undefined,
      sizeBytes: stats.size,
      language,
      roles: rolesWithEntrypoint,
      confidence: getFileConfidence(rolesWithEntrypoint),
      includeReason: getIncludeReason({
        language,
        roles: rolesWithEntrypoint,
      }),
      signals,
      tags,
      reason: getFileReason(relativePath),
    });
  }

  skippedFiles.sort(compareSkippedFiles);
  const warnings = getWarnings(files, skippedFiles);

  return FileIndexSchema.parse({
    schemaVersion: 2,
    generatedAt: new Date().toISOString(),
    files,
    skippedFiles,
    warnings,
    stats: buildStats({
      totalFilesDiscovered: files.length + skippedFiles.length,
      files,
      skippedFiles,
    }),
  });
}

function getSkipReason(input: {
  relativePath: string;
  sizeBytes: number;
  gitignoreFilter: (relativePath: string) => boolean;
}): { reason: SkipReason; detail?: string } | null {
  const lowerPath = input.relativePath.toLowerCase();
  const extension = path.posix.extname(lowerPath);

  if (isSensitivePath(lowerPath)) {
    return {
      reason: "sensitive",
      detail: "Sensitive environment or secrets-like file.",
    };
  }

  if (BINARY_EXTENSIONS.has(extension)) {
    return {
      reason: "binary",
      detail: `Binary or media extension ${extension}.`,
    };
  }

  if (!input.gitignoreFilter(input.relativePath)) {
    return {
      reason: "ignored",
      detail: "Ignored by repository gitignore rules.",
    };
  }

  if (!LOCKFILE_NAMES.has(path.posix.basename(lowerPath)) && input.sizeBytes > MAX_INDEXED_FILE_BYTES) {
    return {
      reason: "too-large",
      detail: `File exceeds ${MAX_INDEXED_FILE_BYTES} bytes.`,
    };
  }

  return null;
}

async function getSkippedNoiseDirectories(repoRoot: string): Promise<SkippedFile[]> {
  const skippedFiles: SkippedFile[] = [];

  for (const directory of [...NOISE_DIRECTORIES].sort((left, right) => left.localeCompare(right))) {
    if (!(await fs.pathExists(path.join(repoRoot, directory)))) {
      continue;
    }

    skippedFiles.push({
      path: RepoRelativePathSchema.parse(directory),
      reason: GENERATED_DIRECTORIES.has(directory) ? "generated" : "noise-directory",
      detail: "Directory excluded from repository inventory traversal.",
    });
  }

  return skippedFiles;
}

function isSensitivePath(lowerPath: string): boolean {
  const fileName = path.posix.basename(lowerPath);

  return (
    fileName === ".env" ||
    fileName.startsWith(".env.") ||
    fileName === "secrets.json" ||
    fileName === "secrets.yaml" ||
    fileName === "secrets.yml" ||
    fileName === "credentials.json" ||
    fileName.endsWith(".pem") ||
    fileName.endsWith(".key")
  );
}

function buildStats(input: {
  totalFilesDiscovered: number;
  files: FileIndexEntry[];
  skippedFiles: SkippedFile[];
}): NonNullable<FileIndex["stats"]> {
  const byLanguage: Record<FileIndexLanguage, number> = {
    typescript: 0,
    javascript: 0,
    python: 0,
    markdown: 0,
    json: 0,
    yaml: 0,
    css: 0,
    html: 0,
    shell: 0,
    unknown: 0,
  };
  const byRole = {} as Record<FileRole, number>;
  const bySkipReason = {} as Record<SkipReason, number>;
  let totalIncludedBytes = 0;

  for (const file of input.files) {
    totalIncludedBytes += file.sizeBytes;
    byLanguage[file.language ?? "unknown"] += 1;

    for (const role of file.roles ?? []) {
      byRole[role] = (byRole[role] ?? 0) + 1;
    }
  }

  for (const skippedFile of input.skippedFiles) {
    bySkipReason[skippedFile.reason] = (bySkipReason[skippedFile.reason] ?? 0) + 1;
  }

  return {
    totalFilesDiscovered: input.totalFilesDiscovered,
    includedFileCount: input.files.length,
    skippedFileCount: input.skippedFiles.length,
    totalIncludedBytes,
    byLanguage,
    byRole,
    bySkipReason,
  };
}

function getWarnings(
  files: FileIndexEntry[],
  skippedFiles: SkippedFile[],
): ScanWarning[] {
  const warnings: ScanWarning[] = [];

  if (!files.some((file) => file.roles?.includes("source"))) {
    warnings.push({
      code: "no-source-files",
      message: "No source files were detected in the repository inventory.",
      severity: "warning",
    });
  }

  for (const skippedFile of skippedFiles) {
    if (skippedFile.reason === "sensitive") {
      warnings.push({
        code: "sensitive-file-skipped",
        message: `Skipped sensitive file ${skippedFile.path}.`,
        filePath: skippedFile.path,
        severity: "warning",
      });
    }

    if (skippedFile.reason === "too-large") {
      warnings.push({
        code: "large-file-skipped",
        message: `Skipped large file ${skippedFile.path}.`,
        filePath: skippedFile.path,
        severity: "info",
      });
    }
  }

  if (skippedFiles.length > files.length * 2 && skippedFiles.length > 20) {
    warnings.push({
      code: "many-skipped-files",
      message: "Skipped file count is much larger than included file count.",
      severity: "info",
    });
  }

  return warnings.sort(compareWarnings);
}

function compareSkippedFiles(left: SkippedFile, right: SkippedFile): number {
  return left.path.localeCompare(right.path) || left.reason.localeCompare(right.reason);
}

function compareWarnings(left: ScanWarning, right: ScanWarning): number {
  return (
    left.code.localeCompare(right.code) ||
    (left.filePath ?? "").localeCompare(right.filePath ?? "") ||
    left.message.localeCompare(right.message)
  );
}
