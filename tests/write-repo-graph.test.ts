import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  getGraphSummaryPath,
  getRepoGraphPath,
} from "../src/core/utils/paths";
import {
  GraphSummarySchema,
  type GraphSummary,
} from "../src/core/repo-graph/models/graph-summary";
import {
  RepoGraphSchema,
  type RepoGraph,
} from "../src/core/repo-graph/models/repo-graph";
import {
  writeGraphSummary,
  writeRepoGraph,
  writeRepoGraphArtifacts,
} from "../src/core/repo-graph/write-repo-graph";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("writeRepoGraphArtifacts", () => {
  it("builds graph artifact paths", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    expect(getRepoGraphPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "repo-graph.json"),
    );
    expect(getGraphSummaryPath(repoRoot)).toBe(
      path.join(repoRoot, ".bridger", "artifacts", "graph-summary.json"),
    );
  });

  it("writes both graph artifacts", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await writeRepoGraphArtifacts({
      repoRoot,
      graph,
      summary,
    });

    expect(result.repoGraphPath).toBe(getRepoGraphPath(repoRoot));
    expect(result.graphSummaryPath).toBe(getGraphSummaryPath(repoRoot));

    expect(
      (await stat(path.join(repoRoot, ".bridger", "artifacts"))).isDirectory(),
    ).toBe(true);

    const graphRaw = await readFile(result.repoGraphPath, "utf8");
    const summaryRaw = await readFile(result.graphSummaryPath, "utf8");

    expect(graphRaw).toContain("\n  ");
    expect(summaryRaw).toContain("\n  ");

    const graphJson = JSON.parse(graphRaw);
    const summaryJson = JSON.parse(summaryRaw);

    expect(RepoGraphSchema.safeParse(graphJson).success).toBe(true);
    expect(GraphSummarySchema.safeParse(summaryJson).success).toBe(true);
  });

  it("writes individual graph artifacts", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const repoGraphPath = await writeRepoGraph({ repoRoot, graph });
    const graphSummaryPath = await writeGraphSummary({ repoRoot, summary });

    expect(repoGraphPath).toBe(getRepoGraphPath(repoRoot));
    expect(graphSummaryPath).toBe(getGraphSummaryPath(repoRoot));

    const graphJson = JSON.parse(await readFile(repoGraphPath, "utf8"));
    const summaryJson = JSON.parse(await readFile(graphSummaryPath, "utf8"));

    expect(RepoGraphSchema.safeParse(graphJson).success).toBe(true);
    expect(GraphSummarySchema.safeParse(summaryJson).success).toBe(true);
  });

  it("rejects invalid repo graph input", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await expect(
      writeRepoGraph({
        repoRoot,
        graph: {
          generatedAt: new Date().toISOString(),
          graphVersion: 1,
          repoRoot,
        } as RepoGraph,
      }),
    ).rejects.toThrow();
  });
});

async function createTempRepo(): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), "bridger-graph-write-"));
}

function createGraph(repoRoot: string): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot,
    nodes: [
      {
        id: "src/index.ts",
        path: "src/index.ts",
        kind: "file",
        extension: ".ts",
        language: "typescript",
        sizeBytes: 100,
        tags: ["source", "entrypoint-candidate"],
      },
    ],
    edges: [],
    diagnostics: [],
    stats: {
      fileCount: 1,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: 0,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 1,
    },
  };
}

function createSummary(graph: RepoGraph): GraphSummary {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    entrypoints: ["src/index.ts"],
    rootFiles: [],
    configFiles: [],
    docsFiles: [],
    highFanInFiles: [],
    highFanOutFiles: [],
    leafFiles: ["src/index.ts"],
    isolatedFiles: ["src/index.ts"],
    architectureFirstOrder: ["src/index.ts"],
    dependencyFirstOrder: ["src/index.ts"],
    stats: graph.stats,
  };
}
