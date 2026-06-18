import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import type { FileIndex } from "../src/core/models/file-index";
import { RepoRelativePathSchema } from "../src/core/models/path";
import { buildRepoGraph } from "../src/core/repo-graph/build-repo-graph";
import { RepoGraphSchema } from "../src/core/repo-graph/models/repo-graph";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("buildRepoGraph", () => {
  it("builds a full validated graph from a fixture file index", async () => {
    const repoRoot = await createFixtureRepo();
    tempDir = repoRoot;

    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex: createFixtureFileIndex(),
    });

    expect(RepoGraphSchema.safeParse(graph).success).toBe(true);
    expect(graph.graphVersion).toBe(1);
    expect(graph.repoRoot).toBe(repoRoot);

    expect(
      graph.nodes
        .filter((node) => node.kind === "file")
        .map((node) => node.path),
    ).toEqual([
      "package.json",
      "src/app.ts",
      "src/features/users/index.ts",
      "src/index.ts",
    ]);

    expect(
      graph.nodes
        .filter((node) => node.kind === "directory")
        .map((node) => node.path),
    ).toEqual(["src", "src/features", "src/features/users"]);

    expect(
      graph.edges
        .filter((edge) => edge.type === "imports")
        .map((edge) => `${edge.from} -> ${edge.to}`),
    ).toEqual([
      "src/index.ts -> src/app.ts",
      "src/index.ts -> src/features/users/index.ts",
    ]);

    expect(graph.diagnostics).toEqual([
      {
        level: "warning",
        code: "unresolved-import",
        file: "src/index.ts",
        message: 'Could not resolve local import "./missing" from src/index.ts.',
      },
    ]);
  });

  it("computes the correct graph stats", async () => {
    const repoRoot = await createFixtureRepo();
    tempDir = repoRoot;

    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex: createFixtureFileIndex(),
    });

    expect(graph.stats).toEqual({
      fileCount: 4,
      directoryCount: 3,
      containsEdgeCount: 5,
      importEdgeCount: 2,
      unresolvedImportCount: 1,
      supportedLanguageFileCount: 3,
    });
  });

  it("returns stable graph output across runs apart from generatedAt", async () => {
    const repoRoot = await createFixtureRepo();
    tempDir = repoRoot;

    const input = {
      repoRoot,
      fileIndex: createFixtureFileIndex(),
    };

    const first = await buildRepoGraph(input);
    const second = await buildRepoGraph(input);

    expect({
      nodes: first.nodes,
      edges: first.edges,
      diagnostics: first.diagnostics,
      stats: first.stats,
    }).toEqual({
      nodes: second.nodes,
      edges: second.edges,
      diagnostics: second.diagnostics,
      stats: second.stats,
    });
  });

  it("sorts nodes, edges, and diagnostics deterministically", async () => {
    const repoRoot = await createFixtureRepo();
    tempDir = repoRoot;

    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex: createFixtureFileIndex(),
    });

    const nodePaths = graph.nodes.map((node) => node.path);
    expect(nodePaths).toEqual([...nodePaths].sort());

    expect(graph.edges.map((edge) => `${edge.from} -> ${edge.to} (${edge.type})`)).toEqual([
      "src -> src/app.ts (contains)",
      "src -> src/features (contains)",
      "src -> src/index.ts (contains)",
      "src/features -> src/features/users (contains)",
      "src/features/users -> src/features/users/index.ts (contains)",
      "src/index.ts -> src/app.ts (imports)",
      "src/index.ts -> src/features/users/index.ts (imports)",
    ]);

    expect(graph.diagnostics).toEqual([
      {
        level: "warning",
        code: "unresolved-import",
        file: "src/index.ts",
        message: 'Could not resolve local import "./missing" from src/index.ts.',
      },
    ]);
  });

  it("returns a graph that validates against RepoGraphSchema", async () => {
    const repoRoot = await createFixtureRepo();
    tempDir = repoRoot;

    const graph = await buildRepoGraph({
      repoRoot,
      fileIndex: createFixtureFileIndex(),
    });

    expect(RepoGraphSchema.safeParse(graph).success).toBe(true);
  });
});

async function createFixtureRepo(): Promise<string> {
  const repoRoot = await createTempRepo();

  await writeRepoFile(
    repoRoot,
    "package.json",
    '{\n  "name": "fixture"\n}\n',
  );
  await writeRepoFile(
    repoRoot,
    "src/index.ts",
    [
      'import app from "./app";',
      'import users from "./features/users";',
      'import missing from "./missing";',
      'import React from "react";',
      "",
    ].join("\n"),
  );
  await writeRepoFile(repoRoot, "src/app.ts", "export default {};\n");
  await writeRepoFile(
    repoRoot,
    "src/features/users/index.ts",
    "export default {};\n",
  );

  return repoRoot;
}

async function createTempRepo(): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), "bridger-graph-"));
}

async function writeRepoFile(
  repoRoot: string,
  filePath: string,
  content: string,
): Promise<void> {
  const absolutePath = path.join(repoRoot, filePath);
  await mkdir(path.dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, content, "utf8");
}

function createFixtureFileIndex(): FileIndex {
  return createFileIndex([
    { path: "package.json", sizeBytes: 24 },
    { path: "src/index.ts", sizeBytes: 112 },
    { path: "src/app.ts", sizeBytes: 18 },
    { path: "src/features/users/index.ts", sizeBytes: 18 },
  ]);
}

function createFileIndex(
  files: Array<{ path: string; sizeBytes: number }>,
): FileIndex {
  return {
    generatedAt: new Date().toISOString(),
    files: files.map((file) => {
      const entry: FileIndex["files"][number] = {
        path: RepoRelativePathSchema.parse(file.path),
        sizeBytes: file.sizeBytes,
        tags: [],
      };

      const extension = getExtension(file.path);

      if (extension !== null) {
        entry.extension = extension;
      }

      return entry;
    }),
  };
}

function getExtension(filePath: string): string | null {
  const fileName = filePath.split("/").at(-1) ?? filePath;
  const dotIndex = fileName.lastIndexOf(".");

  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return null;
  }

  return fileName.slice(dotIndex);
}
