import path from "node:path";

import { normalizeRepoPath } from "../utils/normalize-path";

export type PythonResolvedImport = {
  status: "resolved";
  resolvedPath: string;
  confidence: "high" | "medium";
};

export type PythonUnresolvedImport = {
  status: "unresolved";
  reason: "local-import-not-found";
};

export type PythonIgnoredImport = {
  status: "ignored";
  reason: "external-package";
};

export type PythonImportResolutionResult =
  | PythonResolvedImport
  | PythonUnresolvedImport
  | PythonIgnoredImport;

export function resolvePythonImport(input: {
  importerPath: string;
  specifier: string;
  repoFiles: ReadonlySet<string> | readonly string[];
}): PythonImportResolutionResult {
  const specifier = input.specifier.trim();

  if (specifier === "") {
    return {
      status: "ignored",
      reason: "external-package",
    };
  }

  const repoFileSet = toNormalizedRepoFileSet(input.repoFiles);
  const importerPath = normalizeRepoPath(input.importerPath);

  if (specifier.startsWith(".")) {
    const resolvedPath = resolveRelativePythonImport({
      importerPath,
      specifier,
      repoFileSet,
    });

    if (resolvedPath) {
      return {
        status: "resolved",
        resolvedPath,
        confidence: "high",
      };
    }

    return {
      status: "unresolved",
      reason: "local-import-not-found",
    };
  }

  const resolvedPath = resolveAbsolutePythonImport({
    specifier,
    repoFileSet,
  });

  if (resolvedPath) {
    return {
      status: "resolved",
      resolvedPath,
      confidence: "medium",
    };
  }

  return {
    status: "ignored",
    reason: "external-package",
  };
}

function resolveAbsolutePythonImport(input: {
  specifier: string;
  repoFileSet: ReadonlySet<string>;
}): string | null {
  const modulePath = moduleSpecifierToPath(input.specifier);

  for (const candidate of getAbsoluteCandidates(modulePath)) {
    if (input.repoFileSet.has(candidate)) {
      return candidate;
    }
  }

  return null;
}

function resolveRelativePythonImport(input: {
  importerPath: string;
  specifier: string;
  repoFileSet: ReadonlySet<string>;
}): string | null {
  const parsed = parseRelativeSpecifier(input.specifier);

  if (!parsed) {
    return null;
  }

  const importerDirectory = path.posix.dirname(input.importerPath);
  const baseDirectory = ascendDirectory(importerDirectory, parsed.level - 1);
  const modulePath = parsed.modulePath
    ? path.posix.join(baseDirectory, parsed.modulePath)
    : baseDirectory;
  const normalizedModulePath = normalizeRepoPath(
    path.posix.normalize(modulePath),
  );

  for (const candidate of getPythonModuleCandidates(normalizedModulePath)) {
    if (input.repoFileSet.has(candidate)) {
      return candidate;
    }
  }

  return null;
}

function parseRelativeSpecifier(
  specifier: string,
): { level: number; modulePath: string } | null {
  const match = specifier.match(/^(\.+)(.*)$/);

  if (!match?.[1]) {
    return null;
  }

  return {
    level: match[1].length,
    modulePath: moduleSpecifierToPath(match[2] ?? ""),
  };
}

function moduleSpecifierToPath(specifier: string): string {
  return specifier.split(".").filter(Boolean).join("/");
}

function getAbsoluteCandidates(modulePath: string): string[] {
  return [
    ...getPythonModuleCandidates(modulePath),
    ...getPythonModuleCandidates(`src/${modulePath}`),
  ];
}

function getPythonModuleCandidates(modulePath: string): string[] {
  const parts = modulePath.split("/").filter(Boolean);
  const candidates: string[] = [];

  for (let length = parts.length; length >= 1; length -= 1) {
    const candidateBase = parts.slice(0, length).join("/");
    candidates.push(`${candidateBase}.py`, `${candidateBase}/__init__.py`);
  }

  return candidates;
}

function ascendDirectory(directoryPath: string, levels: number): string {
  let current = directoryPath;

  for (let index = 0; index < levels; index += 1) {
    const next = path.posix.dirname(current);

    if (next === current || next === ".") {
      return ".";
    }

    current = next;
  }

  return current;
}

function toNormalizedRepoFileSet(
  repoFiles: ReadonlySet<string> | readonly string[],
): ReadonlySet<string> {
  const values = Array.isArray(repoFiles) ? repoFiles : Array.from(repoFiles);

  return new Set(values.map(normalizeRepoPath));
}
