import fs from "fs-extra";
import path from "node:path";

import {
  RepoContextCommandsSchema,
  type RepoContextCommands,
} from "../models/repo-context";

type PackageManager = "pnpm" | "npm" | "yarn" | "bun";

type PackageJson = {
  packageManager?: string;
  scripts?: Record<string, string>;
};

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

function normalizePackageManager(
  packageManager?: string,
): PackageManager | undefined {
  if (packageManager === "pnpm" || packageManager?.startsWith("pnpm")) {
    return "pnpm";
  }

  if (packageManager === "npm" || packageManager?.startsWith("npm")) {
    return "npm";
  }

  if (packageManager === "yarn" || packageManager?.startsWith("yarn")) {
    return "yarn";
  }

  if (packageManager === "bun" || packageManager?.startsWith("bun")) {
    return "bun";
  }

  return undefined;
}

function formatInstallCommand(packageManager: PackageManager): string {
  if (packageManager === "pnpm") {
    return "pnpm install";
  }

  if (packageManager === "yarn") {
    return "yarn install";
  }

  if (packageManager === "bun") {
    return "bun install";
  }

  return "npm install";
}

function formatScriptCommand(
  packageManager: PackageManager,
  scriptName: string,
): string {
  if (packageManager === "pnpm") {
    return `pnpm ${scriptName}`;
  }

  if (packageManager === "yarn") {
    return `yarn ${scriptName}`;
  }

  if (packageManager === "bun") {
    return `bun run ${scriptName}`;
  }

  return `npm run ${scriptName}`;
}

function findScript(
  scripts: Record<string, string>,
  candidates: readonly string[],
): string | undefined {
  for (const candidate of candidates) {
    if (Object.prototype.hasOwnProperty.call(scripts, candidate)) {
      return candidate;
    }
  }

  return undefined;
}

export async function detectCommands(
  repoRoot: string,
  packageManager?: string,
): Promise<RepoContextCommands> {
  const packageJson = await readPackageJson(repoRoot);

  if (packageJson === null) {
    return RepoContextCommandsSchema.parse({});
  }

  const resolvedPackageManager =
    normalizePackageManager(packageManager) ??
    normalizePackageManager(packageJson.packageManager) ??
    "npm";

  const scripts = packageJson.scripts ?? {};
  const commands: RepoContextCommands = {
    install: formatInstallCommand(resolvedPackageManager),
  };

  const devScript = findScript(scripts, ["dev", "start"]);
  if (devScript !== undefined) {
    commands.dev = formatScriptCommand(resolvedPackageManager, devScript);
  }

  const buildScript = findScript(scripts, ["build"]);
  if (buildScript !== undefined) {
    commands.build = formatScriptCommand(resolvedPackageManager, buildScript);
  }

  const lintScript = findScript(scripts, ["lint"]);
  if (lintScript !== undefined) {
    commands.lint = formatScriptCommand(resolvedPackageManager, lintScript);
  }

  const typecheckScript = findScript(scripts, [
    "typecheck",
    "check-types",
    "check:types",
    "tsc",
  ]);
  if (typecheckScript !== undefined) {
    commands.typecheck = formatScriptCommand(resolvedPackageManager, typecheckScript);
  }

  const testScript = findScript(scripts, ["test", "test:unit"]);
  if (testScript !== undefined) {
    commands.test = formatScriptCommand(resolvedPackageManager, testScript);
  }

  const formatScript = findScript(scripts, ["format", "prettier"]);
  if (formatScript !== undefined) {
    commands.format = formatScriptCommand(resolvedPackageManager, formatScript);
  }

  return RepoContextCommandsSchema.parse(commands);
}
