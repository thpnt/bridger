import { describe, expect, it } from "vitest";

import { formatGraphInspectOutput } from "../src/cli/commands/inspect";
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

describe("formatGraphInspectOutput", () => {
  it("renders the expected graph inspection sections", () => {
    const output = formatGraphInspectOutput({
      graph: createGraph(),
      summary: createSummary(),
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
    });

    expect(output).toContain("Entrypoint candidates\n- None");
    expect(output).toContain("Top high fan-in files\n- None");
    expect(output).toContain("Top high fan-out files\n- None");
    expect(output).toContain("Architecture-first order preview\n- None");
  });
});
