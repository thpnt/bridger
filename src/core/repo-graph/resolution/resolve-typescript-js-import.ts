import path from "node:path";

import { normalizeRepoPath } from "../utils/normalize-path";

const TYPESCRIPT_JS_RESOLUTION_EXTENSIONS = [
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
] as const;

export type TypeScriptJsResolvedImport = {
  status: "resolved";
  resolvedPath: string;
  confidence: "high";
};

export type TypeScriptJsUnresolvedImport = {
  status: "unresolved";
  reason: "local-import-not-found";
};

export type TypeScriptJsIgnoredImport = {
  status: "ignored";
  reason: "external-package";
};

export type TypeScriptJsImportResolutionResult =
  | TypeScriptJsResolvedImport
  | TypeScriptJsUnresolvedImport
  | TypeScriptJsIgnoredImport;

export function resolveTypeScriptJsImport(input: {
  importerPath: string;
  specifier: string;
  repoFiles: ReadonlySet<string> | readonly string[];
}): TypeScriptJsImportResolutionResult {
  const specifier = input.specifier.trim();

  if (!isRelativeImportSpecifier(specifier)) {
    return {
      status: "ignored",
      reason: "external-package",
    };
  }

  const repoFileSet = toNormalizedRepoFileSet(input.repoFiles);
  const importerPath = normalizeRepoPath(input.importerPath);
  const importerDirectory = path.posix.dirname(importerPath);
  const basePath = normalizeRepoPath(
    path.posix.normalize(path.posix.join(importerDirectory, specifier)),
  );

  for (const candidate of getTypeScriptJsResolutionCandidates(basePath)) {
    if (repoFileSet.has(candidate)) {
      return {
        status: "resolved",
        resolvedPath: candidate,
        confidence: "high",
      };
    }
  }

  return {
    status: "unresolved",
    reason: "local-import-not-found",
  };
}

function isRelativeImportSpecifier(specifier: string): boolean {
  return specifier.startsWith("./") || specifier.startsWith("../");
}

function toNormalizedRepoFileSet(
  repoFiles: ReadonlySet<string> | readonly string[],
): ReadonlySet<string> {
  const values = Array.isArray(repoFiles) ? repoFiles : Array.from(repoFiles);

  return new Set(values.map(normalizeRepoPath));
}

function getTypeScriptJsResolutionCandidates(basePath: string): string[] {
  if (hasSupportedExtension(basePath)) {
    return [basePath];
  }

  return [
    ...TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.map(
      (extension) => `${basePath}${extension}`,
    ),
    ...TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.map(
      (extension) => `${basePath}/index${extension}`,
    ),
  ];
}

function hasSupportedExtension(pathValue: string): boolean {
  return TYPESCRIPT_JS_RESOLUTION_EXTENSIONS.some((extension) =>
    pathValue.endsWith(extension),
  );
}
