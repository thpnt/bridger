import { describe, expect, it } from "vitest";

import { buildAffectedTraversal } from "../src/core/affected-traversal/build-affected-traversal";
import type { CodebaseMap } from "../src/core/codebase-map/models/codebase-map";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
} from "../src/core/repo-graph/models/repo-graph";

describe("buildAffectedTraversal", () => {
  it("returns dependencies, consumers, tests, same-cluster files, and stable metadata", () => {
    const result = buildAffectedTraversal({
      seedFiles: ["src/feature.ts"],
      repoGraph: createRepoGraph(),
      codebaseMap: createCodebaseMap(),
    });

    expect(result.seedFiles).toEqual(["src/feature.ts"]);
    expect(result.relatedFiles.map((file) => file.path)).toEqual([
      "src/helper.ts",
      "src/consumer.ts",
      "src/deep.ts",
      "tests/feature.test.ts",
      "src/index.ts",
      "src/cluster-peer.ts",
      "src/feature-util.ts",
    ]);
    expect(result.relatedFiles).toEqual([
      {
        path: "src/helper.ts",
        relation: "dependency",
        distance: 1,
        score: 90,
        reasons: ["Seed file imports this file through RepoGraph import edges."],
        confidence: "observed",
      },
      {
        path: "src/consumer.ts",
        relation: "consumer",
        distance: 1,
        score: 85,
        reasons: ["This file imports the seed file through RepoGraph import edges."],
        confidence: "observed",
      },
      {
        path: "src/deep.ts",
        relation: "dependency",
        distance: 2,
        score: 85,
        reasons: ["Seed file imports this file through RepoGraph import edges."],
        confidence: "observed",
      },
      {
        path: "tests/feature.test.ts",
        relation: "test",
        distance: 1,
        score: 80,
        reasons: [
          "Test imports the seed file through RepoGraph import edges.",
          "Test is listed in the same CodebaseMap cluster tests.",
        ],
        confidence: "observed",
      },
      {
        path: "src/index.ts",
        relation: "entrypoint-consumer",
        distance: 1,
        score: 75,
        reasons: [
          "Entrypoint imports the seed file through a direct RepoGraph edge.",
        ],
        confidence: "observed",
      },
      {
        path: "src/cluster-peer.ts",
        relation: "same-cluster",
        score: 65,
        reasons: ["Same CodebaseMap cluster as seed file (src-feature)."],
        confidence: "inferred",
      },
      {
        path: "src/feature-util.ts",
        relation: "same-cluster",
        score: 45,
        reasons: ["Same CodebaseMap cluster as seed file (src-feature)."],
        confidence: "inferred",
      },
    ]);
    expect(result.diagnostics).toEqual([]);
  });

  it("uses cluster evidence for related tests when no import edge exists", () => {
    const repoGraph = createRepoGraph();
    const result = buildAffectedTraversal({
      seedFiles: ["src/feature.ts"],
      repoGraph: {
        ...repoGraph,
        edges: repoGraph.edges.filter(
          (edge) => edge.from !== "tests/feature.test.ts",
        ),
      },
      codebaseMap: createCodebaseMap(),
      maxRelatedFiles: 10,
    });

    expect(result.relatedFiles).toEqual(
      expect.arrayContaining([
        {
          path: "tests/feature.test.ts",
          relation: "test",
          score: 80,
          reasons: ["Test is listed in the same CodebaseMap cluster tests."],
          confidence: "inferred",
        },
      ]),
    );
  });

  it("respects maxDistance and excludes seed files from related files", () => {
    const result = buildAffectedTraversal({
      seedFiles: ["src/feature.ts"],
      repoGraph: createRepoGraph(),
      codebaseMap: createCodebaseMap(),
      maxDistance: 1,
      maxRelatedFiles: 20,
    });

    expect(result.relatedFiles.map((file) => file.path)).not.toContain(
      "src/feature.ts",
    );
    expect(result.relatedFiles.map((file) => file.path)).not.toContain(
      "src/deep.ts",
    );
  });

  it("respects maxRelatedFiles and reports the limit", () => {
    const result = buildAffectedTraversal({
      seedFiles: ["src/feature.ts"],
      repoGraph: createRepoGraph(),
      codebaseMap: createCodebaseMap(),
      maxRelatedFiles: 3,
    });

    expect(result.relatedFiles).toHaveLength(3);
    expect(result.diagnostics).toEqual([
      {
        code: "max-related-files-reached",
        message: "Affected traversal was limited to 3 related files.",
        severity: "info",
      },
    ]);
  });

  it("reports missing seed files deterministically", () => {
    const result = buildAffectedTraversal({
      seedFiles: ["src/missing.ts"],
      repoGraph: createRepoGraph(),
      codebaseMap: createCodebaseMap(),
    });

    expect(result.relatedFiles).toEqual([]);
    expect(result.diagnostics).toEqual([
      {
        code: "no-related-files-found",
        message: "No related files were found for the provided seed files.",
        severity: "info",
      },
      {
        code: "seed-file-not-found",
        message: "Seed file is not present in RepoGraph: src/missing.ts",
        path: "src/missing.ts",
        severity: "warning",
      },
      {
        code: "seed-file-not-in-codebase-map",
        message: "Seed file is not present in CodebaseMap: src/missing.ts",
        path: "src/missing.ts",
        severity: "warning",
      },
    ]);
  });
});

function createRepoGraph(): RepoGraph {
  return {
    generatedAt: "2026-06-17T00:00:00.000Z",
    graphVersion: 1,
    repoRoot: "/tmp/affected",
    nodes: [
      fileNode("src/index.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/feature.ts"),
      fileNode("src/helper.ts"),
      fileNode("src/deep.ts"),
      fileNode("src/consumer.ts"),
      fileNode("src/cluster-peer.ts"),
      fileNode("src/feature-util.ts"),
      fileNode("tests/feature.test.ts", ["test"]),
    ],
    edges: [
      importEdge("src/index.ts", "src/feature.ts"),
      importEdge("src/feature.ts", "src/helper.ts"),
      importEdge("src/helper.ts", "src/deep.ts"),
      importEdge("src/consumer.ts", "src/feature.ts"),
      importEdge("tests/feature.test.ts", "src/feature.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: 8,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: 5,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 8,
    },
  };
}

function createCodebaseMap(): CodebaseMap {
  return {
    schemaVersion: 1,
    generatedAt: "2026-06-17T00:00:00.000Z",
    repo: {
      name: "affected",
      packageManager: "pnpm",
      detectedStack: ["TypeScript"],
    },
    stats: {
      fileCount: 8,
      sourceFileCount: 7,
      testFileCount: 1,
      fixtureFileCount: 0,
      docsFileCount: 0,
      configFileCount: 0,
      clusterCount: 2,
      entrypointCount: 1,
      centralFileCount: 1,
      unresolvedImportCount: 0,
    },
    entrypoints: [
      {
        path: "src/index.ts",
        kind: "cli-command",
        confidence: "observed",
        reasons: ["Fixture entrypoint."],
      },
    ],
    clusters: [
      {
        id: "src-feature",
        title: "Feature",
        rootPath: "src",
        kind: "source",
        files: [
          "src/cluster-peer.ts",
          "src/feature.ts",
          "src/feature-util.ts",
        ],
        roles: { source: 3 },
        entrypoints: ["src/index.ts"],
        centralFiles: [
          {
            path: "src/cluster-peer.ts",
            fanIn: 4,
            fanOut: 1,
            reasons: ["Central file."],
          },
        ],
        tests: ["tests/feature.test.ts"],
        fixtures: [],
        dependencies: [],
        consumers: [],
        confidence: "inferred",
        reasons: ["Fixture cluster."],
        warnings: [],
      },
      {
        id: "tests",
        title: "Tests",
        rootPath: "tests",
        kind: "test",
        files: ["tests/feature.test.ts"],
        roles: { test: 1 },
        entrypoints: [],
        centralFiles: [],
        tests: ["tests/feature.test.ts"],
        fixtures: [],
        dependencies: [],
        consumers: [],
        confidence: "inferred",
        reasons: ["Fixture cluster."],
        warnings: [],
      },
    ],
    files: [
      codebaseFile("src/index.ts", {
        isEntrypoint: true,
      }),
      codebaseFile("src/feature.ts", {
        clusterId: "src-feature",
      }),
      codebaseFile("src/helper.ts"),
      codebaseFile("src/deep.ts"),
      codebaseFile("src/consumer.ts"),
      codebaseFile("src/cluster-peer.ts", {
        clusterId: "src-feature",
        isCentral: true,
        fanIn: 4,
        fanOut: 1,
      }),
      codebaseFile("src/feature-util.ts", {
        clusterId: "src-feature",
        roles: ["source", "utility"],
      }),
      codebaseFile("tests/feature.test.ts", {
        clusterId: "tests",
        roles: ["source", "test"],
        isTest: true,
      }),
    ],
    signals: {
      frameworks: {},
      schemas: {},
      validation: {},
      cli: {},
      testing: {},
      database: {},
    },
    unresolvedImports: {
      count: 0,
      byFile: [],
    },
    warnings: [],
  };
}

function codebaseFile(
  filePath: string,
  overrides: Partial<CodebaseMap["files"][number]> = {},
): CodebaseMap["files"][number] {
  return {
    path: filePath,
    language: "typescript",
    roles: ["source", "service"],
    signals: [],
    fanIn: 0,
    fanOut: 0,
    isCentral: false,
    isEntrypoint: false,
    isTest: false,
    isFixture: false,
    ...overrides,
  };
}

function fileNode(
  filePath: string,
  tags: RepoGraphNode["tags"] = ["source"],
): RepoGraphNode {
  return {
    id: filePath,
    path: filePath,
    kind: "file",
    extension: ".ts",
    language: "typescript",
    sizeBytes: 100,
    tags,
  };
}

function importEdge(from: string, to: string): RepoGraphEdge {
  return {
    from,
    to,
    type: "imports",
    confidence: "high",
    source: "typescript-js-imports",
    importSpecifier: "./fixture",
  };
}
