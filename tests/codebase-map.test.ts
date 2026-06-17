import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { buildCodebaseMap } from "../src/core/codebase-map/build-codebase-map";
import { CodebaseMapSchema } from "../src/core/codebase-map/models/codebase-map";
import { writeCodebaseMapArtifact } from "../src/core/codebase-map/write-codebase-map";
import type { FileIndex } from "../src/core/models/file-index";
import type { RepoContext } from "../src/core/models/repo-context";
import { buildGraphSummary } from "../src/core/repo-graph/build-graph-summary";
import type { RepoGraph } from "../src/core/repo-graph/models/repo-graph";
import { getCodebaseMapPath } from "../src/core/project/bridger-paths";

let tempDir = "";

afterEach(async () => {
  if (tempDir) await rm(tempDir, { recursive: true, force: true });
  tempDir = "";
});

describe("CodebaseMap", () => {
  it("builds a validated interpreted map with stable path-first clusters", () => {
    const input = createInput("/tmp/example");
    const first = buildCodebaseMap(input);
    const second = buildCodebaseMap(input);

    expect(CodebaseMapSchema.safeParse(first).success).toBe(true);
    expect(first.clusters.map((cluster) => cluster.id)).toEqual([
      "config",
      "docs",
      "scripts",
      "src-cli",
      "src-core-bar",
      "src-core-foo",
      "tests",
    ]);
    expect(first.clusters.map((cluster) => cluster.id)).toEqual(
      second.clusters.map((cluster) => cluster.id),
    );

    const foo = first.clusters.find((cluster) => cluster.id === "src-core-foo")!;
    const bar = first.clusters.find((cluster) => cluster.id === "src-core-bar")!;
    const tests = first.clusters.find((cluster) => cluster.id === "tests")!;

    expect(foo.files).toEqual([
      "src/core/foo/schema.ts",
      "src/core/foo/service.ts",
    ]);
    expect(foo.files).not.toContain("tests/foo.test.ts");
    expect(tests.tests).toEqual(["tests/foo.test.ts"]);
    expect(tests.fixtures).toEqual(["tests/fixtures/user.json"]);
    expect(bar.dependencies).toEqual([
      expect.objectContaining({ clusterId: "src-core-foo", fileCount: 1 }),
    ]);
    expect(foo.consumers).toEqual(expect.arrayContaining([
      expect.objectContaining({ clusterId: "src-core-bar", fileCount: 1 }),
    ]));
    expect(foo.centralFiles.map((file) => file.path)).toContain(
      "src/core/foo/service.ts",
    );
    expect(first.files.find((file) => file.path === "src/core/foo/service.ts")).toEqual(
      expect.objectContaining({
        roles: ["service", "source"],
        fanIn: 3,
        fanOut: 1,
        clusterId: "src-core-foo",
        isCentral: true,
      }),
    );
    expect(first.entrypoints).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          path: "src/cli/cli.ts",
          kind: "package-bin",
          confidence: "observed",
        }),
      ]),
    );
    expect(first.signals).toEqual(
      expect.objectContaining({
        frameworks: { react: 1 },
        schemas: { zod: 1 },
        validation: { zod: 1 },
        cli: { commander: 1 },
      }),
    );
    expect(first.unresolvedImports).toEqual({
      count: 1,
      byFile: [{ path: "src/core/bar/consumer.ts", count: 1 }],
    });
    expect(first.warnings).toContain("1 unresolved import detected.");
    expect(input.graphSummary).not.toHaveProperty("clusters");
  });

  it("falls back to GraphSummary entrypoints when rich signals are unavailable", () => {
    const input = createInput("/tmp/example");
    const cli = input.fileIndex.files.find((file) => file.path === "src/cli/cli.ts")!;
    cli.roles = ["source"];
    cli.signals = [];

    const result = buildCodebaseMap(input);

    expect(result.entrypoints).toEqual(expect.arrayContaining([
      expect.objectContaining({
        path: "src/cli/cli.ts",
        reasons: ["Listed in graph summary entrypoint candidates."],
      }),
    ]));
  });

  it("writes validated codebase-map.json to the canonical artifact path", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-codebase-map-"));
    const input = createInput(tempDir);
    const codebaseMap = buildCodebaseMap(input);

    const outputPath = await writeCodebaseMapArtifact({ repoRoot: tempDir, codebaseMap });

    expect(outputPath).toBe(getCodebaseMapPath(tempDir));
    const written = JSON.parse(await readFile(outputPath, "utf8"));
    expect(CodebaseMapSchema.safeParse(written).success).toBe(true);
  });
});

function createInput(repoRoot: string) {
  const fileIndex = {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      file("src/cli/cli.ts", ["source", "command", "entrypoint-candidate"], [
        signal("entrypoint", "package-bin", "package-json", "Referenced by package.json bin."),
        signal("cli", "commander"),
      ]),
      file("src/core/foo/service.ts", ["source", "service"], [signal("framework", "react")]),
      file("src/core/foo/schema.ts", ["source", "schema"], [
        signal("schema", "zod"),
        signal("validation", "zod"),
      ]),
      file("src/core/bar/consumer.ts", ["source"], []),
      file("tests/foo.test.ts", ["source", "test"], [signal("testing", "vitest")]),
      file("tests/fixtures/user.json", ["fixture"], []),
      file("docs/overview.md", ["docs"], []),
      file("scripts/release.ts", ["source", "script", "entrypoint-candidate"], []),
      file("package.json", ["config", "project-config"], []),
    ],
  } as unknown as FileIndex;
  const repoGraph = createGraph(repoRoot);
  const graphSummary = buildGraphSummary(repoGraph);

  return {
    repoRoot,
    fileIndex,
    repoContext: createRepoContext(repoRoot),
    repoGraph,
    graphSummary,
  };
}

function file(filePath: string, roles: string[], signals: unknown[]) {
  return {
    path: filePath,
    sizeBytes: 100,
    language: getLanguage(filePath),
    roles,
    confidence: "inferred",
    includeReason: "source",
    signals,
    tags: [],
  };
}

function signal(kind: string, value: string, source = "import", reason = `Imports ${value}.`) {
  return { kind, value, source, confidence: "observed", reason };
}

function getLanguage(filePath: string): "markdown" | "json" | "typescript" {
  if (filePath.endsWith(".md")) return "markdown";
  if (filePath.endsWith(".json")) return "json";
  return "typescript";
}

function createRepoContext(repoRoot: string): RepoContext {
  return {
    repoRoot,
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "React",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: [],
      validation: ["Zod"],
      database: [],
      testFramework: ["Vitest"],
    },
    commands: {},
    importantFiles: [],
    generatedDocs: {
      repoAnalysisPath: ".bridger/memory/repo-analysis.md",
      architecturePath: ".bridger/memory/architecture.md",
      businessLogicPath: ".bridger/memory/business-logic.md",
      conventionsPath: ".bridger/memory/conventions.md",
      testingPath: ".bridger/memory/testing.md",
      agentRulesPath: ".bridger/memory/agent-rules.md",
      ticketTemplatePath: ".bridger/templates/ticket-template.md",
    },
  } as unknown as RepoContext;
}

function createGraph(repoRoot: string): RepoGraph {
  const paths = [
    "src/cli/cli.ts",
    "src/core/foo/service.ts",
    "src/core/foo/schema.ts",
    "src/core/bar/consumer.ts",
    "tests/foo.test.ts",
    "tests/fixtures/user.json",
    "docs/overview.md",
    "scripts/release.ts",
    "package.json",
  ];
  const edges = [
    ["src/cli/cli.ts", "src/core/foo/service.ts"],
    ["src/core/foo/service.ts", "src/core/foo/schema.ts"],
    ["src/core/bar/consumer.ts", "src/core/foo/service.ts"],
    ["tests/foo.test.ts", "src/core/foo/service.ts"],
  ];

  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1,
    repoRoot,
    nodes: paths.map((filePath) => ({
      id: filePath,
      path: filePath,
      kind: "file",
      extension: path.extname(filePath),
      language: getLanguage(filePath),
      sizeBytes: 100,
      tags: filePath === "src/cli/cli.ts" ? ["source", "entrypoint-candidate"] : ["source"],
    })),
    edges: edges.map(([from, to]) => ({
      from: from!,
      to: to!,
      type: "imports",
      confidence: "high",
      source: "typescript-js-imports",
      importSpecifier: `./${path.basename(to!)}`,
    })),
    diagnostics: [
      {
        level: "warning",
        code: "unresolved-import",
        file: "src/core/bar/consumer.ts",
        message: "Could not resolve local import.",
      },
    ],
    stats: {
      fileCount: paths.length,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: edges.length,
      unresolvedImportCount: 1,
      supportedLanguageFileCount: paths.length,
    },
  } as RepoGraph;
}
