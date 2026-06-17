import fs from "fs-extra";
import path from "node:path";

import type { FileSignal } from "../models/file-index";
import { pythonImportExtractor } from "../repo-graph/extractors/python-import-extractor";
import { typescriptJsImportExtractor } from "../repo-graph/extractors/typescript-js-import-extractor";

const MAX_SIGNAL_SCAN_FILE_BYTES = 250_000;

const SIGNALS_BY_PACKAGE: Record<
  string,
  Array<Pick<FileSignal, "kind" | "value" | "reason">>
> = {
  zod: [
    { kind: "schema", value: "zod", reason: "Imports zod schema tooling." },
    {
      kind: "validation",
      value: "zod",
      reason: "Imports zod validation tooling.",
    },
  ],
  pydantic: [
    {
      kind: "schema",
      value: "pydantic",
      reason: "Imports Pydantic schema tooling.",
    },
    {
      kind: "model",
      value: "pydantic",
      reason: "Imports Pydantic model tooling.",
    },
    {
      kind: "validation",
      value: "pydantic",
      reason: "Imports Pydantic validation tooling.",
    },
  ],
  fastapi: [
    {
      kind: "framework",
      value: "fastapi",
      reason: "Imports FastAPI framework APIs.",
    },
  ],
  django: [
    {
      kind: "framework",
      value: "django",
      reason: "Imports Django framework APIs.",
    },
  ],
  react: [
    {
      kind: "frontend",
      value: "react",
      reason: "Imports React frontend APIs.",
    },
    {
      kind: "framework",
      value: "react",
      reason: "Imports React framework APIs.",
    },
  ],
  next: [
    {
      kind: "framework",
      value: "next",
      reason: "Imports Next.js framework APIs.",
    },
  ],
  commander: [
    {
      kind: "cli",
      value: "commander",
      reason: "Imports Commander CLI APIs.",
    },
  ],
  cac: [{ kind: "cli", value: "cac", reason: "Imports CAC CLI APIs." }],
  click: [{ kind: "cli", value: "click", reason: "Imports Click CLI APIs." }],
  typer: [{ kind: "cli", value: "typer", reason: "Imports Typer CLI APIs." }],
  prisma: [
    {
      kind: "database",
      value: "prisma",
      reason: "Imports Prisma database APIs.",
    },
    {
      kind: "schema",
      value: "prisma",
      reason: "Imports Prisma schema APIs.",
    },
  ],
  drizzle: [
    {
      kind: "database",
      value: "drizzle",
      reason: "Imports Drizzle database APIs.",
    },
    {
      kind: "schema",
      value: "drizzle",
      reason: "Imports Drizzle schema APIs.",
    },
  ],
  vitest: [
    {
      kind: "testing",
      value: "vitest",
      reason: "Imports Vitest testing APIs.",
    },
  ],
  jest: [{ kind: "testing", value: "jest", reason: "Imports Jest testing APIs." }],
  playwright: [
    {
      kind: "testing",
      value: "playwright",
      reason: "Imports Playwright testing APIs.",
    },
  ],
  cypress: [
    {
      kind: "testing",
      value: "cypress",
      reason: "Imports Cypress testing APIs.",
    },
  ],
};

export async function getFileSignals(input: {
  repoRoot: string;
  relativePath: string;
  sizeBytes: number;
  packageBinPaths: ReadonlySet<string>;
}): Promise<FileSignal[]> {
  const signals: FileSignal[] = [];

  addPathSignals({
    relativePath: input.relativePath,
    packageBinPaths: input.packageBinPaths,
    signals,
  });

  if (input.sizeBytes > MAX_SIGNAL_SCAN_FILE_BYTES) {
    return sortSignals(signals);
  }

  const extractor = getImportExtractor(input.relativePath);

  if (!extractor) {
    return sortSignals(signals);
  }

  let content: string;

  try {
    content = await fs.readFile(
      path.join(input.repoRoot, input.relativePath),
      "utf8",
    );
  } catch {
    return sortSignals(signals);
  }

  for (const extractedImport of extractor.extractImports({
    filePath: input.relativePath,
    content,
  })) {
    if (isLocalImport(extractedImport.specifier)) {
      continue;
    }

    addPackageSignals({
      packageName: getPackageName(extractedImport.specifier),
      signals,
    });
  }

  return sortSignals(signals);
}

export async function readPackageBinPaths(repoRoot: string): Promise<Set<string>> {
  const packageJsonPath = path.join(repoRoot, "package.json");
  const result = new Set<string>();

  if (!(await fs.pathExists(packageJsonPath))) {
    return result;
  }

  try {
    const packageJson = (await fs.readJson(packageJsonPath)) as {
      bin?: string | Record<string, string>;
    };

    if (typeof packageJson.bin === "string") {
      result.add(normalizeBinPath(packageJson.bin));
    }

    if (packageJson.bin && typeof packageJson.bin === "object") {
      for (const binPath of Object.values(packageJson.bin)) {
        result.add(normalizeBinPath(binPath));
      }
    }
  } catch {
    return result;
  }

  return result;
}

export function isEntrypointCandidatePath(relativePath: string): boolean {
  const lowerPath = relativePath.toLowerCase();

  return (
    lowerPath === "index.ts" ||
    lowerPath === "index.js" ||
    lowerPath === "main.ts" ||
    lowerPath === "main.tsx" ||
    lowerPath === "main.js" ||
    lowerPath === "main.jsx" ||
    lowerPath === "src/index.ts" ||
    lowerPath === "src/index.js" ||
    lowerPath === "src/main.ts" ||
    lowerPath === "src/main.tsx" ||
    lowerPath === "src/main.js" ||
    lowerPath === "src/main.jsx" ||
    lowerPath === "src/cli/index.ts" ||
    lowerPath === "src/cli/index.js" ||
    lowerPath === "src/cli/cli.ts" ||
    lowerPath === "src/cli/cli.js" ||
    lowerPath === "main.py" ||
    lowerPath === "app.py" ||
    lowerPath === "manage.py" ||
    lowerPath === "asgi.py" ||
    lowerPath === "wsgi.py" ||
    lowerPath === "src/main.py" ||
    lowerPath === "src/app.py" ||
    lowerPath.endsWith("/main.py") ||
    lowerPath.endsWith("/app.py") ||
    lowerPath.endsWith("/manage.py") ||
    lowerPath.endsWith("/urls.py") ||
    lowerPath.endsWith("/asgi.py") ||
    lowerPath.endsWith("/wsgi.py") ||
    lowerPath.endsWith("/page.tsx") ||
    lowerPath.endsWith("/page.jsx") ||
    lowerPath.endsWith("/route.ts") ||
    lowerPath.endsWith("/route.js") ||
    lowerPath.startsWith("bin/") ||
    lowerPath.startsWith("scripts/") ||
    lowerPath.includes("/jobs/")
  );
}

function getImportExtractor(relativePath: string) {
  const extension = path.posix.extname(relativePath).toLowerCase();

  if (typescriptJsImportExtractor.extensions.includes(extension)) {
    return typescriptJsImportExtractor;
  }

  if (pythonImportExtractor.extensions.includes(extension)) {
    return pythonImportExtractor;
  }

  return null;
}

function addPathSignals(input: {
  relativePath: string;
  packageBinPaths: ReadonlySet<string>;
  signals: FileSignal[];
}): void {
  const lowerPath = input.relativePath.toLowerCase();

  if (input.packageBinPaths.has(input.relativePath)) {
    input.signals.push({
      kind: "entrypoint",
      source: "package-json",
      value: "package-bin",
      confidence: "observed",
      reason: "Referenced by package.json bin.",
    });
  }

  if (isEntrypointCandidatePath(input.relativePath)) {
    input.signals.push({
      kind: "entrypoint",
      source: "path",
      value: lowerPath,
      confidence: "inferred",
      reason: "Path matches a common entrypoint convention.",
    });
  }

  if (lowerPath.endsWith("route.ts") || lowerPath.endsWith("route.js")) {
    input.signals.push({
      kind: "framework",
      source: "path",
      value: "next-route",
      confidence: "inferred",
      reason: "Path matches a Next.js route convention.",
    });
  }
}

function addPackageSignals(input: {
  packageName: string;
  signals: FileSignal[];
}): void {
  const packageSignals = SIGNALS_BY_PACKAGE[input.packageName];

  if (!packageSignals) {
    return;
  }

  for (const signal of packageSignals) {
    input.signals.push({
      ...signal,
      source: "import",
      confidence: "observed",
    });
  }
}

function sortSignals(signals: FileSignal[]): FileSignal[] {
  const byKey = new Map<string, FileSignal>();

  for (const signal of signals) {
    byKey.set(
      `${signal.kind}\0${signal.source}\0${signal.value}\0${signal.reason}`,
      signal,
    );
  }

  return [...byKey.values()].sort(
    (left, right) =>
      left.kind.localeCompare(right.kind) ||
      left.source.localeCompare(right.source) ||
      left.value.localeCompare(right.value) ||
      left.reason.localeCompare(right.reason),
  );
}

function normalizeBinPath(value: string): string {
  return value.replace(/^\.\//, "").replaceAll("\\", "/");
}

function isLocalImport(specifier: string): boolean {
  return specifier.startsWith(".") || specifier.startsWith("/");
}

function getPackageName(specifier: string): string {
  if (specifier.startsWith("@")) {
    return specifier.split("/").slice(0, 2).join("/");
  }

  const rootSpecifier = specifier.split("/")[0] ?? specifier;

  return rootSpecifier.split(".")[0] ?? rootSpecifier;
}
