import { describe, expect, it } from "vitest";

import { buildAdjacencyMap } from "../src/core/repo-graph/traversal/build-adjacency-map";
import { getConsumers } from "../src/core/repo-graph/traversal/get-consumers";
import { getDependencies } from "../src/core/repo-graph/traversal/get-dependencies";
import { getNeighborhood } from "../src/core/repo-graph/traversal/get-neighborhood";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
} from "../src/core/repo-graph/models/repo-graph";

function fileNode(path: string): RepoGraphNode {
  return {
    id: path,
    path,
    kind: "file",
    extension: ".ts",
    language: "typescript",
    sizeBytes: 100,
    tags: ["source"],
  };
}

function directoryNode(path: string): RepoGraphNode {
  return {
    id: path,
    path,
    kind: "directory",
    extension: null,
    language: "unknown",
    sizeBytes: 0,
    tags: ["source"],
  };
}

function importEdge(from: string, to: string): RepoGraphEdge {
  return {
    from,
    to,
    type: "imports",
    confidence: "high",
    source: "typescript-js-imports",
    importSpecifier: "./x",
  };
}

function containsEdge(from: string, to: string): RepoGraphEdge {
  return {
    from,
    to,
    type: "contains",
    confidence: "high",
    source: "filesystem",
  };
}

function createTraversalGraph(): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot: "/tmp/example",
    nodes: [
      directoryNode("src"),
      fileNode("src/index.ts"),
      fileNode("src/app.ts"),
      fileNode("src/service.ts"),
      fileNode("src/utils.ts"),
      fileNode("src/unused.ts"),
    ],
    edges: [
      containsEdge("src", "src/index.ts"),
      importEdge("src/index.ts", "src/app.ts"),
      importEdge("src/app.ts", "src/service.ts"),
      importEdge("src/service.ts", "src/utils.ts"),
      importEdge("src/utils.ts", "src/app.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: 5,
      directoryCount: 1,
      containsEdgeCount: 1,
      importEdgeCount: 4,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 5,
    },
  };
}

describe("repo graph traversal", () => {
  it("builds outgoing and incoming adjacency maps", () => {
    const graph = createTraversalGraph();
    const adjacencyMap = buildAdjacencyMap(graph);

    expect(adjacencyMap.dependenciesByFile.get("src/index.ts")).toEqual([
      "src/app.ts",
    ]);
    expect(adjacencyMap.consumersByFile.get("src/app.ts")).toEqual([
      "src/index.ts",
      "src/utils.ts",
    ]);
    expect(adjacencyMap.dependenciesByFile.get("src/unused.ts")).toEqual([]);
    expect(adjacencyMap.consumersByFile.get("src/index.ts")).toEqual([]);
  });

  it("returns direct dependencies", () => {
    expect(getDependencies(createTraversalGraph(), "src/index.ts")).toEqual([
      "src/app.ts",
    ]);
  });

  it("returns dependencies up to the requested depth", () => {
    expect(getDependencies(createTraversalGraph(), "src/index.ts", 2)).toEqual([
      "src/app.ts",
      "src/service.ts",
    ]);
  });

  it("handles dependency cycles without returning the start file", () => {
    expect(getDependencies(createTraversalGraph(), "src/app.ts", 10)).toEqual([
      "src/service.ts",
      "src/utils.ts",
    ]);
  });

  it("returns direct consumers", () => {
    expect(getConsumers(createTraversalGraph(), "src/app.ts")).toEqual([
      "src/index.ts",
      "src/utils.ts",
    ]);
  });

  it("returns consumers up to the requested depth", () => {
    expect(getConsumers(createTraversalGraph(), "src/service.ts", 2)).toEqual([
      "src/app.ts",
      "src/index.ts",
      "src/utils.ts",
    ]);
  });

  it("returns a neighborhood with dependencies and consumers", () => {
    expect(getNeighborhood(createTraversalGraph(), "src/app.ts", 1)).toEqual([
      "src/index.ts",
      "src/service.ts",
      "src/utils.ts",
    ]);
  });

  it("returns empty arrays for zero or negative depth", () => {
    const graph = createTraversalGraph();

    expect(getDependencies(graph, "src/index.ts", 0)).toEqual([]);
    expect(getConsumers(graph, "src/app.ts", 0)).toEqual([]);
    expect(getNeighborhood(graph, "src/app.ts", 0)).toEqual([]);
    expect(getDependencies(graph, "src/index.ts", -1)).toEqual([]);
  });

  it("returns an empty array for missing files", () => {
    expect(getDependencies(createTraversalGraph(), "missing.ts")).toEqual([]);
  });

  it("normalizes Windows-style input paths", () => {
    expect(getDependencies(createTraversalGraph(), "src\\index.ts")).toEqual([
      "src/app.ts",
    ]);
  });
});
