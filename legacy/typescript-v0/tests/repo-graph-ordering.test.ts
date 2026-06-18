import { describe, expect, it } from "vitest";

import { getArchitectureOrder } from "../src/core/repo-graph/traversal/get-architecture-order";
import { getDependencyOrder } from "../src/core/repo-graph/traversal/get-dependency-order";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "../src/core/repo-graph/models/repo-graph";

const EXPECTED_FILES = [
  "README.md",
  "package.json",
  "src/index.ts",
  "src/app.ts",
  "src/features/billing/billing-feature.ts",
  "src/components/BillingCard.tsx",
  "src/services/billing-service.ts",
  "src/lib/db.ts",
  "src/utils/format.ts",
  "src/routes/api.ts",
  "tests/billing.test.ts",
  "src/unused.ts",
];

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

function createOrderingGraph(): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot: "/tmp/example",
    nodes: [
      directoryNode("src"),
      fileNode("README.md", ["root", "docs"]),
      fileNode("package.json", ["root", "config"]),
      fileNode("src/index.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/app.ts", ["source"]),
      fileNode("src/features/billing/billing-feature.ts", ["source"]),
      fileNode("src/components/BillingCard.tsx", ["source", "component"]),
      fileNode("src/services/billing-service.ts", ["source", "service"]),
      fileNode("src/lib/db.ts", ["source"]),
      fileNode("src/utils/format.ts", ["source", "utility"]),
      fileNode("src/routes/api.ts", ["source", "route"]),
      fileNode("tests/billing.test.ts", ["source", "test"]),
      fileNode("src/unused.ts", ["source"]),
    ],
    edges: [
      importEdge("src/index.ts", "src/app.ts"),
      importEdge("src/app.ts", "src/features/billing/billing-feature.ts"),
      importEdge(
        "src/features/billing/billing-feature.ts",
        "src/services/billing-service.ts",
      ),
      importEdge("src/services/billing-service.ts", "src/lib/db.ts"),
      importEdge("src/components/BillingCard.tsx", "src/utils/format.ts"),
      importEdge("tests/billing.test.ts", "src/features/billing/billing-feature.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: EXPECTED_FILES.length,
      directoryCount: 1,
      containsEdgeCount: 0,
      importEdgeCount: 6,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 12,
    },
  };
}

function getExtension(path: string): string | null {
  const fileName = path.split("/").at(-1) ?? path;
  const lastDotIndex = fileName.lastIndexOf(".");

  return lastDotIndex >= 0 ? fileName.slice(lastDotIndex) : null;
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

function indexOf(order: string[], path: string): number {
  const index = order.indexOf(path);

  expect(index).toBeGreaterThanOrEqual(0);

  return index;
}

function expectNoDuplicates(order: string[]): void {
  expect(new Set(order).size).toBe(order.length);
}

function expectIncludesAllFiles(order: string[]): void {
  expect(order).toHaveLength(EXPECTED_FILES.length);
  expect(order).toEqual(expect.arrayContaining(EXPECTED_FILES));
}

describe("repo graph ordering", () => {
  it("returns architecture-first order with every file once", () => {
    const order = getArchitectureOrder(createOrderingGraph());

    expectNoDuplicates(order);
    expectIncludesAllFiles(order);
    expect(order).not.toContain("src");
  });

  it("prioritizes docs and config before entrypoints in architecture-first order", () => {
    const order = getArchitectureOrder(createOrderingGraph());

    expect(indexOf(order, "README.md")).toBeLessThan(
      indexOf(order, "src/index.ts"),
    );
    expect(indexOf(order, "package.json")).toBeLessThan(
      indexOf(order, "src/index.ts"),
    );
  });

  it("places entrypoints before direct dependencies in architecture-first order", () => {
    const order = getArchitectureOrder(createOrderingGraph());

    expect(indexOf(order, "src/index.ts")).toBeLessThan(
      indexOf(order, "src/app.ts"),
    );
  });

  it("places direct dependencies before deeper feature and service files in architecture-first order", () => {
    const order = getArchitectureOrder(createOrderingGraph());

    expect(indexOf(order, "src/app.ts")).toBeLessThan(
      indexOf(order, "src/features/billing/billing-feature.ts"),
    );
    expect(indexOf(order, "src/features/billing/billing-feature.ts")).toBeLessThan(
      indexOf(order, "src/services/billing-service.ts"),
    );
  });

  it("places tests after main source buckets in architecture-first order", () => {
    const order = getArchitectureOrder(createOrderingGraph());

    expect(indexOf(order, "tests/billing.test.ts")).toBeGreaterThan(
      indexOf(order, "src/services/billing-service.ts"),
    );
  });

  it("returns dependency-first order with every file once", () => {
    const order = getDependencyOrder(createOrderingGraph());

    expectNoDuplicates(order);
    expectIncludesAllFiles(order);
    expect(order).not.toContain("src");
  });

  it("prioritizes foundational files before features and entrypoints in dependency-first order", () => {
    const order = getDependencyOrder(createOrderingGraph());

    expect(indexOf(order, "src/lib/db.ts")).toBeLessThan(
      indexOf(order, "src/services/billing-service.ts"),
    );
    expect(indexOf(order, "src/services/billing-service.ts")).toBeLessThan(
      indexOf(order, "src/features/billing/billing-feature.ts"),
    );
    expect(indexOf(order, "src/features/billing/billing-feature.ts")).toBeLessThan(
      indexOf(order, "src/index.ts"),
    );
  });

  it("places tests in the test bucket in dependency-first order", () => {
    const order = getDependencyOrder(createOrderingGraph());

    expect(indexOf(order, "tests/billing.test.ts")).toBeGreaterThan(
      indexOf(order, "src/index.ts"),
    );
  });

  it("returns stable order across calls", () => {
    const graph = createOrderingGraph();

    expect(getArchitectureOrder(graph)).toEqual(getArchitectureOrder(graph));
    expect(getDependencyOrder(graph)).toEqual(getDependencyOrder(graph));
  });
});
