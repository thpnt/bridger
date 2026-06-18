import { readFile } from "node:fs/promises";
import path from "node:path";

import type { GraphSummary } from "./models/graph-summary";
import type {
  RepoGraph,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "./models/repo-graph";
import { normalizeRepoPath } from "./utils/normalize-path";

export type GraphOrderedFileReadMode =
  | "architecture-first"
  | "dependency-first";

export type GraphOrderedFileContextEntry = {
  path: string;
  reason: string;
  order: number;
  content: string;
};

export type GraphOrderedFileReadDiagnostic = {
  level: "info" | "warning";
  code:
    | "skipped-large-file"
    | "skipped-total-byte-limit"
    | "skipped-binary-file"
    | "read-error";
  file: string;
  message: string;
};

export type GraphOrderedFileReadResult = {
  files: GraphOrderedFileContextEntry[];
  diagnostics: GraphOrderedFileReadDiagnostic[];
  totalBytes: number;
};

interface SummarySets {
  entrypoints: Set<string>;
  configFiles: Set<string>;
  docsFiles: Set<string>;
  leafFiles: Set<string>;
}

export async function readGraphOrderedFiles(input: {
  repoRoot: string;
  graph: RepoGraph;
  summary: GraphSummary;
  mode: GraphOrderedFileReadMode;
  maxFiles: number;
  maxSingleFileBytes: number;
  maxTotalBytes: number;
  includeTags?: RepoGraphNodeTag[];
  excludeTags?: RepoGraphNodeTag[];
}): Promise<GraphOrderedFileReadResult> {
  const maxFiles = Math.max(0, Math.floor(input.maxFiles));
  const maxSingleFileBytes = Math.max(0, Math.floor(input.maxSingleFileBytes));
  const maxTotalBytes = Math.max(0, Math.floor(input.maxTotalBytes));

  if (maxFiles === 0 || maxSingleFileBytes === 0 || maxTotalBytes === 0) {
    return {
      files: [],
      diagnostics: [],
      totalBytes: 0,
    };
  }

  const nodeByPath = getFileNodeByPath(input.graph);
  const summarySets = getSummarySets(input.summary);
  const entrypointDependencyPaths = getEntrypointDependencyPaths({
    graph: input.graph,
    summary: input.summary,
  });
  const orderedPaths = getOrderedPathsForMode({
    summary: input.summary,
    mode: input.mode,
  });

  const files: GraphOrderedFileContextEntry[] = [];
  const diagnostics: GraphOrderedFileReadDiagnostic[] = [];
  let totalBytes = 0;

  for (const filePath of orderedPaths) {
    if (files.length >= maxFiles) {
      break;
    }

    const node = nodeByPath.get(filePath);

    if (node === undefined) {
      continue;
    }

    if (!matchesTagFilters(node, input.includeTags, input.excludeTags)) {
      continue;
    }

    if (node.sizeBytes > maxSingleFileBytes) {
      diagnostics.push(createLargeFileDiagnostic(filePath, maxSingleFileBytes));
      continue;
    }

    let content: string;

    try {
      content = await readFile(path.join(input.repoRoot, filePath), "utf8");
    } catch {
      diagnostics.push({
        level: "warning",
        code: "read-error",
        file: filePath,
        message: `Could not read ${filePath}.`,
      });
      continue;
    }

    if (looksBinary(content)) {
      diagnostics.push({
        level: "info",
        code: "skipped-binary-file",
        file: filePath,
        message: `Skipped ${filePath} because it appears to be binary.`,
      });
      continue;
    }

    const contentBytes = Buffer.byteLength(content, "utf8");

    if (contentBytes > maxSingleFileBytes) {
      diagnostics.push(createLargeFileDiagnostic(filePath, maxSingleFileBytes));
      continue;
    }

    if (totalBytes + contentBytes > maxTotalBytes) {
      diagnostics.push({
        level: "info",
        code: "skipped-total-byte-limit",
        file: filePath,
        message: `Stopped before reading ${filePath} because maxTotalBytes would be exceeded.`,
      });
      break;
    }

    files.push({
      path: filePath,
      reason: getFileReason({
        path: filePath,
        node,
        summarySets,
        entrypointDependencyPaths,
      }),
      order: files.length + 1,
      content,
    });

    totalBytes += contentBytes;
  }

  return {
    files,
    diagnostics,
    totalBytes,
  };
}

function getOrderedPathsForMode(input: {
  summary: GraphSummary;
  mode: GraphOrderedFileReadMode;
}): string[] {
  const orderedPaths =
    input.mode === "architecture-first"
      ? input.summary.architectureFirstOrder
      : input.summary.dependencyFirstOrder;

  return uniqueStableOrder(orderedPaths.map(normalizeRepoPath));
}

function getFileNodeByPath(graph: RepoGraph): Map<string, RepoGraphNode> {
  const nodeByPath = new Map<string, RepoGraphNode>();

  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }

    nodeByPath.set(normalizeRepoPath(node.path), node);
  }

  return nodeByPath;
}

function matchesTagFilters(
  node: RepoGraphNode,
  includeTags: RepoGraphNodeTag[] | undefined,
  excludeTags: RepoGraphNodeTag[] | undefined,
): boolean {
  if (includeTags && includeTags.length > 0) {
    const hasIncludedTag = includeTags.some((tag) => node.tags.includes(tag));

    if (!hasIncludedTag) {
      return false;
    }
  }

  if (excludeTags && excludeTags.length > 0) {
    const hasExcludedTag = excludeTags.some((tag) => node.tags.includes(tag));

    if (hasExcludedTag) {
      return false;
    }
  }

  return true;
}

function getEntrypointDependencyPaths(input: {
  graph: RepoGraph;
  summary: GraphSummary;
}): Set<string> {
  const entrypoints = new Set(input.summary.entrypoints.map(normalizeRepoPath));
  const dependencies = new Set<string>();

  for (const edge of input.graph.edges) {
    if (edge.type !== "imports") {
      continue;
    }

    const from = normalizeRepoPath(edge.from);

    if (!entrypoints.has(from)) {
      continue;
    }

    dependencies.add(normalizeRepoPath(edge.to));
  }

  return dependencies;
}

function getFileReason(input: {
  path: string;
  node: RepoGraphNode;
  summarySets: SummarySets;
  entrypointDependencyPaths: ReadonlySet<string>;
}): string {
  const filePath = normalizeRepoPath(input.path);

  if (input.summarySets.docsFiles.has(filePath) && isRootPath(filePath)) {
    return "Root documentation file";
  }

  if (input.summarySets.configFiles.has(filePath)) {
    return "Project config file";
  }

  if (input.summarySets.entrypoints.has(filePath)) {
    return "Entrypoint candidate";
  }

  if (input.entrypointDependencyPaths.has(filePath)) {
    return "Dependency of entrypoint";
  }

  if (input.node.tags.includes("test")) {
    return "Test file";
  }

  if (
    input.node.tags.includes("utility") ||
    input.summarySets.leafFiles.has(filePath)
  ) {
    return "Shared utility or leaf file";
  }

  return "Included by graph order";
}

function getSummarySets(summary: GraphSummary): SummarySets {
  return {
    entrypoints: new Set(summary.entrypoints.map(normalizeRepoPath)),
    configFiles: new Set(summary.configFiles.map(normalizeRepoPath)),
    docsFiles: new Set(summary.docsFiles.map(normalizeRepoPath)),
    leafFiles: new Set(summary.leafFiles.map(normalizeRepoPath)),
  };
}

function isRootPath(filePath: string): boolean {
  return !filePath.includes("/");
}

function looksBinary(content: string): boolean {
  return content.includes("\u0000");
}

function uniqueStableOrder(paths: Iterable<string>): string[] {
  const seen = new Set<string>();
  const orderedPaths: string[] = [];

  for (const currentPath of paths) {
    if (seen.has(currentPath)) {
      continue;
    }

    seen.add(currentPath);
    orderedPaths.push(currentPath);
  }

  return orderedPaths;
}

function createLargeFileDiagnostic(
  filePath: string,
  maxSingleFileBytes: number,
): GraphOrderedFileReadDiagnostic {
  return {
    level: "info",
    code: "skipped-large-file",
    file: filePath,
    message: `Skipped ${filePath} because it exceeds ${maxSingleFileBytes} bytes.`,
  };
}
