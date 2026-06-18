import { readFile } from "node:fs/promises";
import path from "node:path";

import type { FileIndex } from "../models/file-index";
import type { FilesystemGraphBuildResult } from "./build-filesystem-graph";
import {
  RepoGraphDiagnosticSchema,
  RepoGraphEdgeSchema,
  type RepoGraphDiagnostic,
  type RepoGraphEdge,
} from "./models/repo-graph";
import {
  type DependencyExtractor,
  type ExtractedImport,
} from "./extractors/dependency-extractor";
import { pythonImportExtractor } from "./extractors/python-import-extractor";
import { typescriptJsImportExtractor } from "./extractors/typescript-js-import-extractor";
import { resolvePythonImport } from "./resolution/resolve-python-import";
import { resolveTypeScriptJsImport } from "./resolution/resolve-typescript-js-import";
import { normalizeRepoPath } from "./utils/normalize-path";

const DEFAULT_MAX_IMPORT_SCAN_FILE_BYTES = 250_000;

const IMPORT_EXTRACTORS = [
  typescriptJsImportExtractor,
  pythonImportExtractor,
] as const;

export type ImportEdgesBuildResult = {
  edges: RepoGraphEdge[];
  diagnostics: RepoGraphDiagnostic[];
};

export async function buildImportEdges(input: {
  repoRoot: string;
  filesystemGraph: FilesystemGraphBuildResult;
  fileIndex: FileIndex;
  maxFileBytes?: number;
}): Promise<ImportEdgesBuildResult> {
  const maxFileBytes =
    input.maxFileBytes ?? DEFAULT_MAX_IMPORT_SCAN_FILE_BYTES;

  const repoFiles = new Set(
    input.fileIndex.files.map((file) => normalizeRepoPath(file.path)),
  );

  const importEdgesByKey = new Map<string, RepoGraphEdge>();
  const diagnosticsByKey = new Map<string, RepoGraphDiagnostic>();

  for (const file of input.fileIndex.files) {
    const filePath = normalizeRepoPath(file.path);
    const extractor = getExtractorForFile(filePath);

    if (!extractor) {
      continue;
    }

    if (file.sizeBytes > maxFileBytes) {
      addDiagnostic({
        diagnosticsByKey,
        diagnostic: {
          level: "info",
          code: "skipped-large-file",
          file: filePath,
          message: `Skipped import extraction for ${filePath} because it exceeds ${maxFileBytes} bytes.`,
        },
      });
      continue;
    }

    let content: string;

    try {
      content = await readFile(path.join(input.repoRoot, filePath), "utf8");
    } catch {
      addDiagnostic({
        diagnosticsByKey,
        diagnostic: {
          level: "warning",
          code: "read-error",
          file: filePath,
          message: `Could not read ${filePath} for import extraction.`,
        },
      });
      continue;
    }

    const extractedImports = extractor.extractImports({
      filePath,
      content,
    });

    for (const extractedImport of extractedImports) {
      processExtractedImport({
        filePath,
        extractedImport,
        extractor,
        repoFiles,
        importEdgesByKey,
        diagnosticsByKey,
      });
    }
  }

  return {
    edges: Array.from(importEdgesByKey.values()).sort(compareEdges),
    diagnostics: Array.from(diagnosticsByKey.values()).sort(compareDiagnostics),
  };
}

function processExtractedImport(input: {
  filePath: string;
  extractedImport: ExtractedImport;
  extractor: DependencyExtractor;
  repoFiles: ReadonlySet<string>;
  importEdgesByKey: Map<string, RepoGraphEdge>;
  diagnosticsByKey: Map<string, RepoGraphDiagnostic>;
}): void {
  const resolution = resolveImport({
    filePath: input.filePath,
    extractedImport: input.extractedImport,
    extractor: input.extractor,
    repoFiles: input.repoFiles,
  });

  if (resolution.status === "ignored") {
    return;
  }

  if (resolution.status === "unresolved") {
    addDiagnostic({
      diagnosticsByKey: input.diagnosticsByKey,
      diagnostic: {
        level: "warning",
        code: "unresolved-import",
        file: input.filePath,
        message: `Could not resolve local import "${input.extractedImport.specifier}" from ${input.filePath}.`,
      },
    });
    return;
  }

  addImportEdge({
    importEdgesByKey: input.importEdgesByKey,
    edge: {
      from: input.filePath,
      to: resolution.resolvedPath,
      type: "imports",
      confidence: resolution.confidence,
      source: input.extractedImport.source,
      importSpecifier: input.extractedImport.specifier,
    },
  });
}

type ImportResolutionResult =
  | {
      status: "resolved";
      resolvedPath: string;
      confidence: "high" | "medium";
    }
  | {
      status: "unresolved";
      reason: string;
    }
  | {
      status: "ignored";
      reason: string;
    };

function resolveImport(input: {
  filePath: string;
  extractedImport: ExtractedImport;
  extractor: DependencyExtractor;
  repoFiles: ReadonlySet<string>;
}): ImportResolutionResult {
  if (input.extractor.source === "typescript-js-imports") {
    return resolveTypeScriptJsImport({
      importerPath: input.filePath,
      specifier: input.extractedImport.specifier,
      repoFiles: input.repoFiles,
    });
  }

  if (input.extractor.source === "python-imports") {
    return resolvePythonImport({
      importerPath: input.filePath,
      specifier: input.extractedImport.specifier,
      repoFiles: input.repoFiles,
    });
  }

  return {
    status: "ignored",
    reason: "external-package",
  };
}

function addImportEdge(input: {
  importEdgesByKey: Map<string, RepoGraphEdge>;
  edge: RepoGraphEdge;
}): void {
  const key = getImportEdgeKey(input.edge);

  if (input.importEdgesByKey.has(key)) {
    return;
  }

  input.importEdgesByKey.set(key, RepoGraphEdgeSchema.parse(input.edge));
}

function getImportEdgeKey(edge: RepoGraphEdge): string {
  return `${edge.from}\0${edge.to}\0${edge.type}`;
}

function addDiagnostic(input: {
  diagnosticsByKey: Map<string, RepoGraphDiagnostic>;
  diagnostic: RepoGraphDiagnostic;
}): void {
  const key = getDiagnosticKey(input.diagnostic);

  if (input.diagnosticsByKey.has(key)) {
    return;
  }

  input.diagnosticsByKey.set(
    key,
    RepoGraphDiagnosticSchema.parse(input.diagnostic),
  );
}

function getDiagnosticKey(diagnostic: RepoGraphDiagnostic): string {
  return `${diagnostic.file ?? ""}\0${diagnostic.code}\0${diagnostic.message}`;
}

function getExtractorForFile(filePath: string): DependencyExtractor | null {
  const extension = getLowerExtension(filePath);

  if (!extension) {
    return null;
  }

  return (
    IMPORT_EXTRACTORS.find((extractor) =>
      extractor.extensions.includes(extension),
    ) ?? null
  );
}

function getLowerExtension(filePath: string): string | null {
  const fileName = filePath.split("/").at(-1) ?? filePath;
  const dotIndex = fileName.lastIndexOf(".");

  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return null;
  }

  return fileName.slice(dotIndex).toLowerCase();
}

function compareEdges(a: RepoGraphEdge, b: RepoGraphEdge): number {
  return (
    a.from.localeCompare(b.from) ||
    a.to.localeCompare(b.to) ||
    a.type.localeCompare(b.type) ||
    a.source.localeCompare(b.source) ||
    (a.importSpecifier ?? "").localeCompare(b.importSpecifier ?? "")
  );
}

function compareDiagnostics(
  a: RepoGraphDiagnostic,
  b: RepoGraphDiagnostic,
): number {
  return (
    (a.file ?? "").localeCompare(b.file ?? "") ||
    a.code.localeCompare(b.code) ||
    a.message.localeCompare(b.message)
  );
}
