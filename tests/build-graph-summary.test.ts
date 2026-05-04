import { describe, expect, it } from "vitest";

import { buildGraphSummary } from "../src/core/repo-graph/build-graph-summary";
import { GraphSummarySchema } from "../src/core/repo-graph/models/graph-summary";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "../src/core/repo-graph/models/repo-graph";
import { getArchitectureOrder } from "../src/core/repo-graph/traversal/get-architecture-order";
import { getDependencyOrder } from "../src/core/repo-graph/traversal/get-dependency-order";

function fileNode(
  path: string,
  tags: RepoGraphNodeTag[] = ["source"],
): RepoGraphNode {
  return {
    id: path,
    path,
    kind: "file",
    extension: getExtension(path),
    language: getLanguageFromPath(path),
    sizeBytes: 100,
    tags,
  };
}

function getExtension(path: string): string | null {
  if (!path.includes(".")) {
    return null;
  }

  return path.slice(path.lastIndexOf("."));
}

function getLanguageFromPath(path: string): RepoGraphNode["language"] {
  if (path.endsWith(".ts") || path.endsWith(".tsx")) {
    return "typescript";
  }

  if (path.endsWith(".js") || path.endsWith(".jsx")) {
    return "javascript";
  }

  if (path.endsWith(".py")) {
    return "python";
  }

  if (path.endsWith(".md")) {
    return "markdown";
  }

  if (path.endsWith(".json")) {
    return "json";
  }

  return "unknown";
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

function createSummaryGraph(): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot: "/tmp/example",
    nodes: [
      fileNode("README.md", ["root", "docs"]),
      fileNode("package.json", ["root", "config"]),
      fileNode("src/index.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/app.ts", ["source"]),
      fileNode("src/features/billing.ts", ["source"]),
      fileNode("src/services/billing-service.ts", ["source", "service"]),
      fileNode("src/lib/db.ts", ["source"]),
      fileNode("src/utils/format.ts", ["source", "utility"]),
      fileNode("src/unused.ts", ["source"]),
      fileNode("tests/billing.test.ts", ["source", "test"]),
    ],
    edges: [
      importEdge("src/index.ts", "src/app.ts"),
      importEdge("src/app.ts", "src/features/billing.ts"),
      importEdge("src/features/billing.ts", "src/services/billing-service.ts"),
      importEdge("src/services/billing-service.ts", "src/lib/db.ts"),
      importEdge("src/index.ts", "src/utils/format.ts"),
      importEdge("tests/billing.test.ts", "src/features/billing.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: 10,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: 6,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 10,
    },
  };
}

function expectNoDuplicates(paths: string[]): void {
  expect(new Set(paths).size).toBe(paths.length);
}

function expectSorted(paths: string[]): void {
  expect(paths).toEqual([...paths].sort((left, right) => left.localeCompare(right)));
}

describe("buildGraphSummary", () => {
  it("builds a valid graph summary", () => {
    const summary = buildGraphSummary(createSummaryGraph());

    expect(GraphSummarySchema.safeParse(summary).success).toBe(true);
  });

  it("includes core file classifications", () => {
    const summary = buildGraphSummary(createSummaryGraph());

    expect(summary.entrypoints).toContain("src/index.ts");
    expect(summary.rootFiles).toEqual(
      expect.arrayContaining(["README.md", "package.json"]),
    );
    expect(summary.configFiles).toContain("package.json");
    expect(summary.docsFiles).toContain("README.md");
  });

  it("includes high fan-in and high fan-out files", () => {
    const summary = buildGraphSummary(createSummaryGraph());

    expect(summary.highFanInFiles[0]).toMatchObject({
      path: "src/features/billing.ts",
      count: 2,
    });
    expect(summary.highFanOutFiles[0]).toMatchObject({
      path: "src/index.ts",
      count: 2,
    });
  });

  it("includes leaf and isolated files", () => {
    const summary = buildGraphSummary(createSummaryGraph());

    expect(summary.leafFiles).toEqual(
      expect.arrayContaining([
        "src/lib/db.ts",
        "src/utils/format.ts",
        "src/unused.ts",
      ]),
    );
    expect(summary.isolatedFiles).toContain("src/unused.ts");
  });

  it("includes architecture-first and dependency-first orders", () => {
    const graph = createSummaryGraph();
    const summary = buildGraphSummary(graph);

    expect(summary.architectureFirstOrder).toEqual(getArchitectureOrder(graph));
    expect(summary.dependencyFirstOrder).toEqual(getDependencyOrder(graph));
    expectNoDuplicates(summary.architectureFirstOrder);
    expectNoDuplicates(summary.dependencyFirstOrder);
  });

  it("copies graph stats", () => {
    const graph = createSummaryGraph();
    const summary = buildGraphSummary(graph);

    expect(summary.stats).toEqual(graph.stats);
  });

  it("returns stable output except generatedAt", () => {
    const graph = createSummaryGraph();
    const first = buildGraphSummary(graph);
    const second = buildGraphSummary(graph);

    const { generatedAt: firstGeneratedAt, ...stableFirst } = first;
    const { generatedAt: secondGeneratedAt, ...stableSecond } = second;

    expect(firstGeneratedAt).toBeTruthy();
    expect(secondGeneratedAt).toBeTruthy();
    expect(stableFirst).toEqual(stableSecond);
  });

  it("sorts normal classification arrays", () => {
    const summary = buildGraphSummary(createSummaryGraph());

    expectSorted(summary.entrypoints);
    expectSorted(summary.rootFiles);
    expectSorted(summary.configFiles);
    expectSorted(summary.docsFiles);
    expectSorted(summary.leafFiles);
    expectSorted(summary.isolatedFiles);
  });
});
