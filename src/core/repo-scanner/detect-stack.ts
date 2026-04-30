import fs from "fs-extra";
import path from "node:path";

import { RepoContextStackSchema } from "../models/repo-context";
import type { RepoContextStack } from "../models/repo-context";

type PackageJson = {
  packageManager?: string;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  scripts?: Record<string, string>;
};

const CONFIG_EXTENSIONS = [".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"];

function pushUnique(target: string[], value: string): void {
  if (!target.includes(value)) {
    target.push(value);
  }
}

async function pathExists(repoRoot: string, relativePath: string): Promise<boolean> {
  return fs.pathExists(path.join(repoRoot, relativePath));
}

async function hasAnyPath(repoRoot: string, relativePaths: string[]): Promise<boolean> {
  for (const relativePath of relativePaths) {
    if (await pathExists(repoRoot, relativePath)) {
      return true;
    }
  }

  return false;
}

async function hasAnyConfigFile(repoRoot: string, baseName: string): Promise<boolean> {
  for (const extension of CONFIG_EXTENSIONS) {
    if (await pathExists(repoRoot, `${baseName}${extension}`)) {
      return true;
    }
  }

  return false;
}

async function readPackageJson(repoRoot: string): Promise<PackageJson | null> {
  const packageJsonPath = path.join(repoRoot, "package.json");

  if (!(await fs.pathExists(packageJsonPath))) {
    return null;
  }

  try {
    const raw = await fs.readFile(packageJsonPath, "utf8");
    return JSON.parse(raw) as PackageJson;
  } catch {
    return null;
  }
}

function getAllDependencyNames(packageJson: PackageJson | null): Set<string> {
  const names = new Set<string>();

  if (packageJson === null) {
    return names;
  }

  const sections = [
    packageJson.dependencies,
    packageJson.devDependencies,
    packageJson.peerDependencies,
    packageJson.optionalDependencies,
  ];

  for (const section of sections) {
    if (section === undefined) {
      continue;
    }

    for (const name of Object.keys(section)) {
      names.add(name);
    }
  }

  return names;
}

async function detectPackageManager(
  repoRoot: string,
  packageJson: PackageJson | null,
): Promise<string> {
  if (await pathExists(repoRoot, "pnpm-lock.yaml")) {
    return "pnpm";
  }

  if (await pathExists(repoRoot, "yarn.lock")) {
    return "yarn";
  }

  if (await pathExists(repoRoot, "package-lock.json")) {
    return "npm";
  }

  if ((await pathExists(repoRoot, "bun.lockb")) || (await pathExists(repoRoot, "bun.lock"))) {
    return "bun";
  }

  const packageManager = packageJson?.packageManager;

  if (typeof packageManager !== "string") {
    return "unknown";
  }

  if (packageManager.startsWith("pnpm")) {
    return "pnpm";
  }

  if (packageManager.startsWith("yarn")) {
    return "yarn";
  }

  if (packageManager.startsWith("npm")) {
    return "npm";
  }

  if (packageManager.startsWith("bun")) {
    return "bun";
  }

  return "unknown";
}

async function detectFramework(repoRoot: string, dependencies: Set<string>): Promise<string> {
  if (dependencies.has("next")) {
    return "Next.js";
  }

  const hasNextConfig = await hasAnyConfigFile(repoRoot, "next.config");
  const hasAppOrPagesDir = await hasAnyPath(repoRoot, [
    "app",
    "pages",
    "src/app",
    "src/pages",
  ]);

  if (hasNextConfig && hasAppOrPagesDir) {
    return "Next.js";
  }

  return "unknown";
}

async function detectLanguage(
  repoRoot: string,
  dependencies: Set<string>,
  packageJson: PackageJson | null,
): Promise<string> {
  if (await pathExists(repoRoot, "tsconfig.json")) {
    return "TypeScript";
  }

  if (dependencies.has("typescript")) {
    return "TypeScript";
  }

  if (packageJson !== null) {
    return "JavaScript";
  }

  return "unknown";
}

async function detectStyling(
  repoRoot: string,
  dependencies: Set<string>,
): Promise<string[]> {
  const styling: string[] = [];

  if (dependencies.has("tailwindcss") || (await hasAnyConfigFile(repoRoot, "tailwind.config"))) {
    pushUnique(styling, "Tailwind");
  }

  if (await pathExists(repoRoot, "components.json")) {
    pushUnique(styling, "shadcn/ui");
  }

  return styling;
}

function detectValidation(dependencies: Set<string>): string[] {
  const validation: string[] = [];

  if (dependencies.has("zod")) {
    pushUnique(validation, "Zod");
  }

  return validation;
}

async function detectDatabase(
  repoRoot: string,
  dependencies: Set<string>,
): Promise<string[]> {
  const database: string[] = [];

  if (dependencies.has("@supabase/supabase-js") || (await pathExists(repoRoot, "supabase"))) {
    pushUnique(database, "Supabase");
  }

  if (
    dependencies.has("prisma") ||
    dependencies.has("@prisma/client") ||
    (await pathExists(repoRoot, "prisma/schema.prisma"))
  ) {
    pushUnique(database, "Prisma");
  }

  if (dependencies.has("drizzle-orm") || (await hasAnyConfigFile(repoRoot, "drizzle.config"))) {
    pushUnique(database, "Drizzle");
  }

  return database;
}

async function detectTestFramework(
  repoRoot: string,
  dependencies: Set<string>,
): Promise<string[]> {
  const testFramework: string[] = [];

  if (dependencies.has("vitest") || (await hasAnyConfigFile(repoRoot, "vitest.config"))) {
    pushUnique(testFramework, "Vitest");
  }

  if (dependencies.has("jest") || (await hasAnyConfigFile(repoRoot, "jest.config"))) {
    pushUnique(testFramework, "Jest");
  }

  if (
    dependencies.has("@playwright/test") ||
    dependencies.has("playwright") ||
    (await hasAnyConfigFile(repoRoot, "playwright.config"))
  ) {
    pushUnique(testFramework, "Playwright");
  }

  if (
    dependencies.has("cypress") ||
    (await pathExists(repoRoot, "cypress")) ||
    (await hasAnyConfigFile(repoRoot, "cypress.config"))
  ) {
    pushUnique(testFramework, "Cypress");
  }

  return testFramework;
}

export async function detectStack(repoRoot: string): Promise<RepoContextStack> {
  const packageJson = await readPackageJson(repoRoot);
  const dependencies = getAllDependencyNames(packageJson);

  const framework = await detectFramework(repoRoot, dependencies);
  const language = await detectLanguage(repoRoot, dependencies, packageJson);
  const packageManager = await detectPackageManager(repoRoot, packageJson);
  const styling = await detectStyling(repoRoot, dependencies);
  const validation = detectValidation(dependencies);
  const database = await detectDatabase(repoRoot, dependencies);
  const testFramework = await detectTestFramework(repoRoot, dependencies);

  const stack = {
    framework,
    language,
    packageManager,
    styling,
    validation,
    database,
    testFramework,
  };

  return RepoContextStackSchema.parse(stack);
}
