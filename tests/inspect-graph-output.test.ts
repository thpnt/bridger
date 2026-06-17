import { describe, expect, it } from "vitest";

import { formatGraphInspectOutput } from "../src/cli/commands/inspect";
import type { CodebaseMap } from "../src/core/codebase-map/models/codebase-map";
import type { GraphSummary } from "../src/core/repo-graph/models/graph-summary";
import type { RepoGraph } from "../src/core/repo-graph/models/repo-graph";

function createGraph(): RepoGraph {
  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1,
    repoRoot: "/tmp/example",
    nodes: [],
    edges: [],
    diagnostics: [],
    stats: {
      fileCount: 3,
      directoryCount: 1,
      containsEdgeCount: 2,
      importEdgeCount: 2,
      unresolvedImportCount: 1,
      supportedLanguageFileCount: 2,
    },
  };
}

function createSummary(): GraphSummary {
  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1,
    entrypoints: ["src/index.ts"],
    rootFiles: ["README.md"],
    configFiles: ["package.json"],
    docsFiles: ["README.md"],
    highFanInFiles: [
      {
        path: "src/lib/utils.ts",
        count: 3,
        reason: "Imported by 3 files.",
      },
    ],
    highFanOutFiles: [
      {
        path: "src/index.ts",
        count: 2,
        reason: "Imports 2 files.",
      },
    ],
    leafFiles: ["src/lib/utils.ts"],
    isolatedFiles: [],
    architectureFirstOrder: [
      "README.md",
      "package.json",
      "src/index.ts",
      "src/lib/utils.ts",
    ],
    dependencyFirstOrder: [
      "src/lib/utils.ts",
      "src/index.ts",
      "README.md",
      "package.json",
    ],
    stats: createGraph().stats,
  };
}

function createCodebaseMap(): CodebaseMap {
  return {
    schemaVersion: 1,
    generatedAt: "2026-05-01T00:00:00.000Z",
    repo: { name: "example", detectedStack: ["TypeScript"] },
    stats: {
      fileCount: 1,
      sourceFileCount: 1,
      testFileCount: 0,
      fixtureFileCount: 0,
      docsFileCount: 0,
      configFileCount: 0,
      clusterCount: 1,
      entrypointCount: 1,
      centralFileCount: 1,
      unresolvedImportCount: 0,
    },
    entrypoints: [],
    clusters: [
      {
        id: "src",
        title: "Src",
        rootPath: "src",
        kind: "source",
        files: ["src/index.ts"],
        roles: { source: 1 },
        entrypoints: ["src/index.ts"],
        centralFiles: [
          {
            path: "src/index.ts",
            fanIn: 0,
            fanOut: 2,
            reasons: ["Entrypoint candidate."],
          },
        ],
        tests: [],
        fixtures: [],
        dependencies: [],
        consumers: [],
        confidence: "inferred",
        reasons: ["Grouped by path prefix src."],
        warnings: [],
      },
    ],
    files: [],
    signals: {
      frameworks: {},
      schemas: {},
      validation: {},
      cli: {},
      testing: {},
      database: {},
    },
    unresolvedImports: { count: 0, byFile: [] },
    warnings: [],
  };
}

describe("formatGraphInspectOutput", () => {
  it("renders the expected graph inspection sections", () => {
    const output = formatGraphInspectOutput({
      graph: createGraph(),
      summary: createSummary(),
      codebaseMap: createCodebaseMap(),
    });

    expect(output).toContain("Repo graph");
    expect(output).toContain("Files: 3");
    expect(output).toContain("Directories: 1");
    expect(output).toContain("Import edges: 2");
    expect(output).toContain("Unresolved imports: 1");
    expect(output).toContain("Entrypoint candidates");
    expect(output).toContain("src/index.ts");
    expect(output).toContain("Top high fan-in files");
    expect(output).toContain("src/lib/utils.ts");
    expect(output).toContain("Top high fan-out files");
    expect(output).toContain("Architecture-first order preview");
    expect(output).toContain("1. README.md");
    expect(output).toContain("Clusters");
    expect(output).toContain("src: 1 files, source, central: src/index.ts");
  });

  it("renders empty graph sections as none", () => {
    const graph = createGraph();
    const output = formatGraphInspectOutput({
      graph,
      summary: {
        generatedAt: graph.generatedAt,
        graphVersion: 1,
        entrypoints: [],
        rootFiles: [],
        configFiles: [],
        docsFiles: [],
        highFanInFiles: [],
        highFanOutFiles: [],
        leafFiles: [],
        isolatedFiles: [],
        architectureFirstOrder: [],
        dependencyFirstOrder: [],
        stats: graph.stats,
      },
      codebaseMap: { ...createCodebaseMap(), clusters: [] },
    });

    expect(output).toContain("Entrypoint candidates\n- None");
    expect(output).toContain("Top high fan-in files\n- None");
    expect(output).toContain("Top high fan-out files\n- None");
    expect(output).toContain("Architecture-first order preview\n- None");
    expect(output).toContain("Clusters\n- None");
  });
});
