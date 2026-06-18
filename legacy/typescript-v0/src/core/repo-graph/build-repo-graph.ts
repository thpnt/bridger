import type { FileIndex } from "../models/file-index";
import { buildFilesystemGraph } from "./build-filesystem-graph";
import { buildImportEdges } from "./build-import-edges";
import {
  RepoGraphSchema,
  type RepoGraph,
  type RepoGraphDiagnostic,
  type RepoGraphEdge,
  type RepoGraphNode,
  type RepoGraphStats,
} from "./models/repo-graph";

export async function buildRepoGraph(input: {
  repoRoot: string;
  fileIndex: FileIndex;
}): Promise<RepoGraph> {
  const filesystemGraph = buildFilesystemGraph({
    repoRoot: input.repoRoot,
    fileIndex: input.fileIndex,
  });

  const importGraph = await buildImportEdges({
    repoRoot: input.repoRoot,
    filesystemGraph,
    fileIndex: input.fileIndex,
  });

  const nodes = sortNodes(dedupeNodes(filesystemGraph.nodes));
  const edges = sortEdges(
    dedupeEdges([...filesystemGraph.edges, ...importGraph.edges]),
  );
  const diagnostics = sortDiagnostics(
    dedupeDiagnostics(importGraph.diagnostics),
  );

  const graph = {
    generatedAt: new Date().toISOString(),
    graphVersion: 1 as const,
    repoRoot: input.repoRoot,
    nodes,
    edges,
    diagnostics,
    stats: computeRepoGraphStats({
      nodes,
      edges,
      diagnostics,
    }),
  };

  return RepoGraphSchema.parse(graph);
}

function computeRepoGraphStats(input: {
  nodes: RepoGraphNode[];
  edges: RepoGraphEdge[];
  diagnostics: RepoGraphDiagnostic[];
}): RepoGraphStats {
  return {
    fileCount: input.nodes.filter((node) => node.kind === "file").length,
    directoryCount: input.nodes.filter((node) => node.kind === "directory")
      .length,
    containsEdgeCount: input.edges.filter((edge) => edge.type === "contains")
      .length,
    importEdgeCount: input.edges.filter((edge) => edge.type === "imports")
      .length,
    unresolvedImportCount: input.diagnostics.filter(
      (diagnostic) => diagnostic.code === "unresolved-import",
    ).length,
    supportedLanguageFileCount: input.nodes.filter(
      (node) =>
        node.kind === "file" && isSupportedImportLanguage(node.language),
    ).length,
  };
}

function dedupeNodes(nodes: RepoGraphNode[]): RepoGraphNode[] {
  const nodesById = new Map<string, RepoGraphNode>();

  for (const node of nodes) {
    if (!nodesById.has(node.id)) {
      nodesById.set(node.id, node);
    }
  }

  return Array.from(nodesById.values());
}

function dedupeEdges(edges: RepoGraphEdge[]): RepoGraphEdge[] {
  const edgesByKey = new Map<string, RepoGraphEdge>();

  for (const edge of edges) {
    const key = `${edge.from}\0${edge.to}\0${edge.type}`;

    if (!edgesByKey.has(key)) {
      edgesByKey.set(key, edge);
    }
  }

  return Array.from(edgesByKey.values());
}

function dedupeDiagnostics(
  diagnostics: RepoGraphDiagnostic[],
): RepoGraphDiagnostic[] {
  const diagnosticsByKey = new Map<string, RepoGraphDiagnostic>();

  for (const diagnostic of diagnostics) {
    const key = `${diagnostic.file ?? ""}\0${diagnostic.code}\0${diagnostic.message}`;

    if (!diagnosticsByKey.has(key)) {
      diagnosticsByKey.set(key, diagnostic);
    }
  }

  return Array.from(diagnosticsByKey.values());
}

function sortNodes(nodes: RepoGraphNode[]): RepoGraphNode[] {
  return [...nodes].sort((a, b) => a.path.localeCompare(b.path));
}

function sortEdges(edges: RepoGraphEdge[]): RepoGraphEdge[] {
  return [...edges].sort(compareEdges);
}

function sortDiagnostics(
  diagnostics: RepoGraphDiagnostic[],
): RepoGraphDiagnostic[] {
  return [...diagnostics].sort(compareDiagnostics);
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

function isSupportedImportLanguage(language: string): boolean {
  return (
    language === "typescript" ||
    language === "javascript" ||
    language === "python"
  );
}
