import path from "node:path";

import { describe, expect, it } from "vitest";

import type { FileIndex } from "../src/core/models/file-index";
import { buildGraphSummary } from "../src/core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../src/core/repo-graph/build-repo-graph";
import { GraphSummarySchema, type GraphSummary } from "../src/core/repo-graph/models/graph-summary";
import { RepoGraphSchema, type RepoGraph } from "../src/core/repo-graph/models/repo-graph";
import {
  readGraphOrderedFiles,
  type GraphOrderedFileReadResult,
} from "../src/core/repo-graph/read-graph-ordered-files";
import { buildFileIndex } from "../src/core/repo-scanner/build-file-index";

type FixtureBuildResult = {
  repoRoot: string;
  fileIndex: FileIndex;
  graph: RepoGraph;
  summary: GraphSummary;
};

function fixturePath(name: string): string {
  return path.join(process.cwd(), "tests", "fixtures", name);
}

async function buildGraphForFixture(name: string): Promise<FixtureBuildResult> {
  const repoRoot = fixturePath(name);
  const fileIndex = await buildFileIndex(repoRoot);
  const graph = await buildRepoGraph({
    repoRoot,
    fileIndex,
  });
  const summary = buildGraphSummary(graph);

  return {
    repoRoot,
    fileIndex,
    graph,
    summary,
  };
}

function expectImportEdge(graph: RepoGraph, from: string, to: string): void {
  expect(graph.edges).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        from,
        to,
        type: "imports",
      }),
    ]),
  );
}

function expectNode(
  graph: RepoGraph,
  nodePath: string,
  kind: "file" | "directory",
): void {
  expect(graph.nodes).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        path: nodePath,
        kind,
      }),
    ]),
  );
}

function expectDiagnosticContaining(
  graph: RepoGraph,
  code: string,
  text: string,
): void {
  expect(
    graph.diagnostics.some(
      (diagnostic) =>
        diagnostic.code === code && diagnostic.message.includes(text),
    ),
  ).toBe(true);
}

function expectNoDiagnosticContaining(graph: RepoGraph, text: string): void {
  expect(
    graph.diagnostics.some((diagnostic) => diagnostic.message.includes(text)),
  ).toBe(false);
}

function stableGraphSnapshot(graph: RepoGraph) {
  return {
    graphVersion: graph.graphVersion,
    nodes: graph.nodes,
    edges: graph.edges,
    diagnostics: graph.diagnostics,
    stats: graph.stats,
  };
}

function stableSummarySnapshot(summary: GraphSummary) {
  const { generatedAt: _generatedAt, ...stable } = summary;

  return stable;
}

function expectNoDuplicates(paths: string[]): void {
  expect(new Set(paths).size).toBe(paths.length);
}

function getFileNode(graph: RepoGraph, nodePath: string) {
  return graph.nodes.find(
    (node) => node.kind === "file" && node.path === nodePath,
  );
}

function expectReaderResultToContainCode(
  result: GraphOrderedFileReadResult,
  code: string,
): void {
  expect(result.diagnostics).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        code,
      }),
    ]),
  );
}

describe("repo graph fixtures", () => {
  it("builds a TypeScript repo graph and summary", async () => {
    const { graph, summary } = await buildGraphForFixture("graph-ts-basic");

    expect(RepoGraphSchema.safeParse(graph).success).toBe(true);
    expect(GraphSummarySchema.safeParse(summary).success).toBe(true);

    expectNode(graph, "src/index.ts", "file");
    expectNode(graph, "src/features/users", "directory");

    expectImportEdge(graph, "src/index.ts", "src/app.ts");
    expectImportEdge(graph, "src/index.ts", "src/features/users/index.ts");
    expectImportEdge(graph, "src/app.ts", "src/lib/format.ts");

    expectDiagnosticContaining(graph, "unresolved-import", "./missing");
    expectNoDiagnosticContaining(graph, "react");

    expect(summary.entrypoints).toContain("src/index.ts");
  });

  it("builds a Python repo graph and summary", async () => {
    const { graph, summary } = await buildGraphForFixture("graph-python-basic");

    expect(RepoGraphSchema.safeParse(graph).success).toBe(true);
    expect(GraphSummarySchema.safeParse(summary).success).toBe(true);

    expectImportEdge(graph, "main.py", "app/service.py");
    expectImportEdge(graph, "app/service.py", "app/domain/users.py");
    expectImportEdge(graph, "app/routes/user.py", "app/domain/users.py");

    expectDiagnosticContaining(graph, "unresolved-import", ".missing");
    expectNoDiagnosticContaining(graph, "requests");

    expect(summary.entrypoints).toContain("main.py");
  });

  it("builds a mixed repo graph and summary", async () => {
    const { graph, summary } = await buildGraphForFixture("graph-mixed-basic");

    expect(RepoGraphSchema.safeParse(graph).success).toBe(true);
    expect(GraphSummarySchema.safeParse(summary).success).toBe(true);

    expectNode(graph, "README.md", "file");
    expectNode(graph, "package.json", "file");
    expectNode(graph, "src/index.ts", "file");
    expectNode(graph, "scripts/main.py", "file");

    expectImportEdge(graph, "src/index.ts", "src/lib/utils.ts");

    expect(summary.docsFiles).toContain("README.md");
    expect(summary.configFiles).toContain("package.json");
    expect(
      summary.architectureFirstOrder.indexOf("README.md"),
    ).toBeLessThan(summary.architectureFirstOrder.indexOf("src/index.ts"));

    const filePaths = graph.nodes
      .filter((node) => node.kind === "file")
      .map((node) => node.path);

    expectNoDuplicates(summary.dependencyFirstOrder);
    expect(summary.dependencyFirstOrder).toHaveLength(filePaths.length);
    expect([...summary.dependencyFirstOrder].sort()).toEqual(
      [...filePaths].sort(),
    );
  });

  it("returns stable graph and summary output across repeated builds", async () => {
    const first = await buildGraphForFixture("graph-ts-basic");
    const second = await buildGraphForFixture("graph-ts-basic");

    expect(stableGraphSnapshot(first.graph)).toEqual(
      stableGraphSnapshot(second.graph),
    );
    expect(stableSummarySnapshot(first.summary)).toEqual(
      stableSummarySnapshot(second.summary),
    );
  });

  it("enforces graph reader limits", async () => {
    const { graph, repoRoot, summary } = await buildGraphForFixture(
      "graph-mixed-basic",
    );

    const maxFilesResult = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 1,
      maxSingleFileBytes: 100_000,
      maxTotalBytes: 100_000,
    });

    expect(maxFilesResult.files).toHaveLength(1);
    expect(maxFilesResult.files[0]?.order).toBe(1);

    const packageNode = getFileNode(graph, "package.json");

    expect(packageNode).toBeDefined();

    const totalBytesResult = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 100_000,
      maxTotalBytes: packageNode?.sizeBytes ?? 1,
    });

    expect(totalBytesResult.files).toHaveLength(1);
    expectReaderResultToContainCode(totalBytesResult, "skipped-total-byte-limit");

    const singleFileBytesResult = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 1,
      maxTotalBytes: 100_000,
    });

    expectReaderResultToContainCode(singleFileBytesResult, "skipped-large-file");
  });
});
