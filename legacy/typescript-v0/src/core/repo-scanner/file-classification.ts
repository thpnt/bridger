import path from "node:path";

import type {
  Confidence,
  FileIndexLanguage,
  FileRole,
  IncludeReason,
} from "../models/file-index";
import { isEntrypointCandidatePath } from "./file-signals";

const LOCKFILE_NAMES = new Set([
  "pnpm-lock.yaml",
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb",
]);

const CONFIG_FILE_NAMES = new Set([
  "package.json",
  "tsconfig.json",
  "jsconfig.json",
  "components.json",
  "pyproject.toml",
  "requirements.txt",
]);

const GENERATED_DIRECTORIES = new Set(["dist", "build", "coverage", ".next"]);

export function detectFileLanguage(
  relativePath: string,
  extension?: string,
): FileIndexLanguage {
  const fileName = path.posix.basename(relativePath);

  if (fileName === ".gitignore" || fileName === ".env") {
    return "unknown";
  }

  switch (extension) {
    case ".ts":
    case ".tsx":
    case ".mts":
    case ".cts":
      return "typescript";
    case ".js":
    case ".jsx":
    case ".mjs":
    case ".cjs":
      return "javascript";
    case ".py":
      return "python";
    case ".md":
    case ".mdx":
      return "markdown";
    case ".json":
      return "json";
    case ".yaml":
    case ".yml":
      return "yaml";
    case ".css":
    case ".scss":
      return "css";
    case ".html":
      return "html";
    case ".sh":
    case ".bash":
    case ".zsh":
      return "shell";
    default:
      return "unknown";
  }
}

export function getFileRoles(relativePath: string, tags: string[]): FileRole[] {
  const roles: FileRole[] = [];
  const lowerPath = relativePath.toLowerCase();
  const fileName = path.posix.basename(lowerPath);
  const extension = path.posix.extname(lowerPath);

  if (isSourceExtension(extension)) {
    roles.push("source");
  }

  if (
    lowerPath.includes("/__tests__/") ||
    lowerPath.includes("/tests/") ||
    lowerPath.startsWith("tests/") ||
    /\.(test|spec)\.[cm]?[jt]sx?$/.test(lowerPath) ||
    lowerPath.endsWith("_test.py")
  ) {
    roles.push("test");
  }

  if (
    lowerPath.includes("/fixtures/") ||
    lowerPath.startsWith("fixtures/") ||
    lowerPath.includes("/fixture/")
  ) {
    roles.push("fixture");
  }

  if (
    extension === ".md" ||
    extension === ".mdx" ||
    hasPathPrefix(lowerPath, "docs") ||
    ["readme.md", "agents.md", "claude.md"].includes(fileName)
  ) {
    roles.push("docs");
  }

  if (isConfigPath(lowerPath)) {
    roles.push("config");
  }

  if (
    CONFIG_FILE_NAMES.has(fileName) ||
    lowerPath.endsWith(".config.ts") ||
    lowerPath.endsWith(".config.js")
  ) {
    roles.push("project-config");
  }

  if (roles.includes("fixture") && roles.includes("config")) {
    roles.push("fixture-config");
  }

  if (LOCKFILE_NAMES.has(fileName)) {
    roles.push("lockfile");
  }

  if (
    lowerPath.includes("planning") ||
    lowerPath.includes("ticket") ||
    lowerPath.includes("roadmap")
  ) {
    roles.push("planning-doc");
  }

  if (hasGeneratedPathSegment(lowerPath)) {
    roles.push("generated");
  }

  if (isEntrypointCandidatePath(relativePath)) {
    roles.push("entrypoint-candidate");
  }

  if (hasPathPrefix(lowerPath, "src/cli") || hasPathPrefix(lowerPath, "cli")) {
    roles.push("command");
  }

  if (tags.includes("route")) {
    roles.push("route");
  }

  if (
    fileName === "route.ts" ||
    fileName === "route.js" ||
    lowerPath.includes("/api/")
  ) {
    roles.push("api-route");
  }

  if (hasPathPrefix(lowerPath, "scripts") || lowerPath.includes("/scripts/")) {
    roles.push("script");
  }

  addMatchingRole(roles, lowerPath, ["/models/", "model"], "model");
  addMatchingRole(roles, lowerPath, ["/schemas/", "schema"], "schema");
  addMatchingRole(roles, lowerPath, ["/types/", ".d.ts"], "type");
  addMatchingRole(roles, lowerPath, ["/services/", "/service"], "service");
  addMatchingRole(
    roles,
    lowerPath,
    ["/utils/", "/utility", "/lib/"],
    "utility",
  );
  addMatchingRole(
    roles,
    lowerPath,
    ["/components/", "components/"],
    "component",
  );
  addMatchingRole(roles, lowerPath, ["build", "builder"], "builder");
  addMatchingRole(roles, lowerPath, ["generator"], "generator");
  addMatchingRole(roles, lowerPath, ["resolver"], "resolver");
  addMatchingRole(roles, lowerPath, ["extractor"], "extractor");
  addMatchingRole(roles, lowerPath, ["reader"], "reader");
  addMatchingRole(roles, lowerPath, ["writer"], "writer");

  if (extension === ".sql") {
    roles.push("schema");
  }

  if (hasPathPrefix(lowerPath, "migrations") || lowerPath.includes("/migrations/")) {
    roles.push("migration");
  }

  return uniqueSortedRoles(roles);
}

export function getIncludeReason(input: {
  language: FileIndexLanguage;
  roles: FileRole[];
}): IncludeReason {
  if (input.roles.includes("test")) {
    return "test";
  }

  if (input.roles.includes("fixture")) {
    return "fixture";
  }

  if (
    input.roles.includes("lockfile") ||
    input.roles.includes("project-config")
  ) {
    return "project-metadata";
  }

  if (input.roles.includes("docs")) {
    return "documentation";
  }

  if (input.roles.includes("config")) {
    return "config";
  }

  if (input.roles.includes("script")) {
    return "script";
  }

  if (input.roles.includes("source")) {
    return "source";
  }

  return input.language === "unknown" ? "unknown" : "source";
}

export function getFileConfidence(roles: FileRole[]): Confidence {
  if (roles.includes("lockfile") || roles.includes("project-config")) {
    return "observed";
  }

  return roles.length === 0 ? "ambiguous" : "inferred";
}

export function uniqueSortedRoles(roles: FileRole[]): FileRole[] {
  return [...new Set(roles)].sort((left, right) => left.localeCompare(right));
}

function isSourceExtension(extension: string): boolean {
  return [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"].includes(
    extension,
  );
}

function isConfigPath(lowerPath: string): boolean {
  const fileName = path.posix.basename(lowerPath);

  return (
    CONFIG_FILE_NAMES.has(fileName) ||
    LOCKFILE_NAMES.has(fileName) ||
    lowerPath.endsWith(".config.ts") ||
    lowerPath.endsWith(".config.js") ||
    lowerPath.endsWith(".config.mjs") ||
    lowerPath.endsWith(".config.cjs") ||
    lowerPath.endsWith(".config.json") ||
    fileName.startsWith(".")
  );
}

function hasGeneratedPathSegment(lowerPath: string): boolean {
  return lowerPath
    .split("/")
    .some((segment) => GENERATED_DIRECTORIES.has(segment));
}

function hasPathPrefix(relativePath: string, prefix: string): boolean {
  return relativePath === prefix || relativePath.startsWith(`${prefix}/`);
}

function addMatchingRole(
  roles: FileRole[],
  lowerPath: string,
  matches: string[],
  role: FileRole,
): void {
  if (matches.some((match) => lowerPath.includes(match))) {
    roles.push(role);
  }
}
