import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import type { GraphSummary } from "../src/core/repo-graph/models/graph-summary";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "../src/core/repo-graph/models/repo-graph";
import {
  readGraphOrderedFiles,
  type GraphOrderedFileReadResult,
} from "../src/core/repo-graph/read-graph-ordered-files";

const LARGE_FILE_CONTENT = "x".repeat(10_000);

let repoRootsToClean: string[] = [];

async function createTempRepo(): Promise<string> {
  const repoRoot = await mkdtemp(path.join(os.tmpdir(), "bridger-graph-read-"));
  repoRootsToClean.push(repoRoot);
  return repoRoot;
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

function fileNode(
  filePath: string,
  tags: RepoGraphNodeTag[],
  sizeBytes = 100,
): RepoGraphNode {
  return {
    id: filePath,
    path: filePath,
    kind: "file",
    extension: getExtension(filePath),
    language: getLanguageFromPath(filePath),
    sizeBytes,
    tags,
  };
}

function getExtension(filePath: string): string | null {
  const fileName = filePath.split("/").at(-1) ?? filePath;
  const lastDotIndex = fileName.lastIndexOf(".");

  return lastDotIndex >= 0 ? fileName.slice(lastDotIndex) : null;
}

function getLanguageFromPath(filePath: string): RepoGraphNode["language"] {
  if (filePath.endsWith(".ts") || filePath.endsWith(".tsx")) {
    return "typescript";
  }

  if (filePath.endsWith(".js") || filePath.endsWith(".jsx")) {
    return "javascript";
  }

  if (filePath.endsWith(".py")) {
    return "python";
  }

  if (filePath.endsWith(".md")) {
    return "markdown";
  }

  if (filePath.endsWith(".json")) {
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

function createGraph(repoRoot: string): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot,
    nodes: [
      fileNode("README.md", ["root", "docs"], 9),
      fileNode("package.json", ["root", "config"], 18),
      fileNode("src/index.ts", ["source", "entrypoint-candidate"], 24),
      fileNode("src/app.ts", ["source"], 38),
      fileNode("src/lib/utils.ts", ["source", "utility"], 27),
      fileNode("src/large.ts", ["source"], 10_001),
      fileNode("tests/app.test.ts", ["source", "test"], 24),
      fileNode("src/binary.ts", ["source"], 7),
      fileNode("src/missing.ts", ["source"], 10),
    ],
    edges: [
      importEdge("src/index.ts", "src/app.ts"),
      importEdge("src/app.ts", "src/lib/utils.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: 9,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: 2,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 9,
    },
  };
}

function createSummary(graph: RepoGraph): GraphSummary {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    entrypoints: ["src/index.ts"],
    rootFiles: ["README.md", "package.json"],
    configFiles: ["package.json"],
    docsFiles: ["README.md"],
    highFanInFiles: [],
    highFanOutFiles: [],
    leafFiles: [
      "README.md",
      "package.json",
      "src/lib/utils.ts",
      "tests/app.test.ts",
    ],
    isolatedFiles: [],
    architectureFirstOrder: [
      "README.md",
      "package.json",
      "src/index.ts",
      "src/app.ts",
      "src/lib/utils.ts",
      "src/large.ts",
      "tests/app.test.ts",
      "src/binary.ts",
      "src/missing.ts",
    ],
    dependencyFirstOrder: [
      "src/lib/utils.ts",
      "src/app.ts",
      "src/index.ts",
      "README.md",
      "package.json",
      "tests/app.test.ts",
      "src/large.ts",
      "src/binary.ts",
      "src/missing.ts",
    ],
    stats: graph.stats,
  };
}

async function writeFixtureFiles(repoRoot: string): Promise<void> {
  await writeRepoFile(repoRoot, "README.md", "# Project");
  await writeRepoFile(repoRoot, "package.json", '{"name":"example"}');
  await writeRepoFile(repoRoot, "src/index.ts", 'import app from "./app";');
  await writeRepoFile(
    repoRoot,
    "src/app.ts",
    'import { format } from "./lib/utils";',
  );
  await writeRepoFile(
    repoRoot,
    "src/lib/utils.ts",
    "export function format() {}",
  );
  await writeRepoFile(repoRoot, "src/large.ts", LARGE_FILE_CONTENT);
  await writeRepoFile(repoRoot, "tests/app.test.ts", 'test("works", () => {});');
  await writeRepoFile(repoRoot, "src/binary.ts", "abc\u0000def");
}

function paths(result: GraphOrderedFileReadResult): string[] {
  return result.files.map((file) => file.path);
}

function reasonByPath(result: GraphOrderedFileReadResult): Map<string, string> {
  return new Map(result.files.map((file) => [file.path, file.reason]));
}

afterEach(async () => {
  await Promise.all(
    repoRootsToClean.map(async (repoRoot) => {
      await rm(repoRoot, { recursive: true, force: true });
    }),
  );
  repoRootsToClean = [];
});

describe("readGraphOrderedFiles", () => {
  it("reads files in architecture-first order", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    expect(paths(result).slice(0, 5)).toEqual([
      "README.md",
      "package.json",
      "src/index.ts",
      "src/app.ts",
      "src/lib/utils.ts",
    ]);
    expect(result.files.map((file) => file.order)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("reads files in dependency-first order", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "dependency-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    expect(paths(result).slice(0, 3)).toEqual([
      "src/lib/utils.ts",
      "src/app.ts",
      "src/index.ts",
    ]);
  });

  it("produces deterministic reasons", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    const reasons = reasonByPath(result);

    expect(reasons.get("README.md")).toBe("Root documentation file");
    expect(reasons.get("package.json")).toBe("Project config file");
    expect(reasons.get("src/index.ts")).toBe("Entrypoint candidate");
    expect(reasons.get("src/app.ts")).toBe("Dependency of entrypoint");
    expect(reasons.get("src/lib/utils.ts")).toBe("Shared utility or leaf file");
    expect(reasons.get("tests/app.test.ts")).toBe("Test file");
  });

  it("enforces maxFiles", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 3,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    expect(result.files).toHaveLength(3);
    expect(result.files.map((file) => file.order)).toEqual([1, 2, 3]);
  });

  it("skips files over maxSingleFileBytes", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 100,
      maxTotalBytes: 100_000,
    });

    expect(paths(result)).not.toContain("src/large.ts");
    expect(result.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "skipped-large-file",
          file: "src/large.ts",
        }),
      ]),
    );
  });

  it("stops before maxTotalBytes would be exceeded", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 10,
    });

    expect(result.files).toHaveLength(1);
    expect(result.files[0]?.path).toBe("README.md");
    expect(result.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "skipped-total-byte-limit",
          file: "package.json",
        }),
      ]),
    );
    expect(paths(result)).not.toContain("src/index.ts");
  });

  it("supports excludeTags", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
      excludeTags: ["test"],
    });

    expect(paths(result)).not.toContain("tests/app.test.ts");
  });

  it("supports includeTags", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
      includeTags: ["config"],
    });

    expect(paths(result)).toEqual(["package.json"]);
  });

  it("skips unreadable files with a diagnostic", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 20,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    expect(paths(result)).not.toContain("src/missing.ts");
    expect(result.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "read-error",
          file: "src/missing.ts",
        }),
      ]),
    );
  });

  it("skips binary-looking files", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);

    const result = await readGraphOrderedFiles({
      repoRoot,
      graph,
      summary,
      mode: "architecture-first",
      maxFiles: 20,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    });

    expect(paths(result)).not.toContain("src/binary.ts");
    expect(result.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: "skipped-binary-file",
          file: "src/binary.ts",
        }),
      ]),
    );
  });

  it("returns stable output across runs", async () => {
    const repoRoot = await createTempRepo();
    await writeFixtureFiles(repoRoot);

    const graph = createGraph(repoRoot);
    const summary = createSummary(graph);
    const input = {
      repoRoot,
      graph,
      summary,
      mode: "architecture-first" as const,
      maxFiles: 10,
      maxSingleFileBytes: 10_000,
      maxTotalBytes: 100_000,
    };

    const first = await readGraphOrderedFiles(input);
    const second = await readGraphOrderedFiles(input);

    expect(first).toEqual(second);
  });
});
