import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { buildCodebaseMap } from "../src/core/codebase-map/build-codebase-map";
import type { CodebaseMap } from "../src/core/codebase-map/models/codebase-map";
import type {
  FileIndex,
  FileIndexEntry,
  FileRole,
  FileSignal,
} from "../src/core/models/file-index";
import { RepoRelativePathSchema } from "../src/core/models/path";
import type { RepoContext } from "../src/core/models/repo-context";
import {
  buildGeneratedDocPaths,
  getReadingPlansPath,
  getTicketTemplateRelativePath,
} from "../src/core/project/bridger-paths";
import { buildReadingPlans } from "../src/core/reading-plans/build-reading-plans";
import {
  ReadingBatchSchema,
  ReadingPlanFileSchema,
  ReadingPlanSchema,
  ReadingPlansSchema,
  type ReadingPlan,
  type ReadingPlans,
} from "../src/core/reading-plans/models/reading-plans";
import { writeReadingPlansArtifact } from "../src/core/reading-plans/write-reading-plans";
import { buildGraphSummary } from "../src/core/repo-graph/build-graph-summary";
import type { GraphSummary } from "../src/core/repo-graph/models/graph-summary";
import type { RepoGraph } from "../src/core/repo-graph/models/repo-graph";

const PLAN_KINDS = [
  "repo-analysis",
  "architecture",
  "business-logic",
  "conventions",
  "testing",
] as const;

const TARGET_MEMORY_FILES = [
  ".bridger/memory/repo-analysis.md",
  ".bridger/memory/architecture.md",
  ".bridger/memory/business-logic.md",
  ".bridger/memory/conventions.md",
  ".bridger/memory/testing.md",
];

let tempDir = "";

afterEach(async () => {
  if (tempDir) await rm(tempDir, { recursive: true, force: true });
  tempDir = "";
});

describe("ReadingPlans schemas", () => {
  it("validates a representative ReadingPlans artifact", () => {
    const readingPlans = representativeReadingPlans();

    expect(ReadingPlansSchema.parse(readingPlans)).toEqual(readingPlans);
  });

  it.each(PLAN_KINDS)("validates the %s plan kind", (kind) => {
    expect(
      ReadingPlanSchema.safeParse(representativePlan(kind)).success,
    ).toBe(true);
  });

  it("validates batch metadata and file references", () => {
    const batch = representativePlan("architecture").batches[0];

    expect(ReadingBatchSchema.safeParse(batch).success).toBe(true);
    expect(
      ReadingBatchSchema.safeParse({ ...batch, order: -1 }).success,
    ).toBe(false);
  });

  it("validates file role, evidence, confidence, and estimated bytes", () => {
    const file = representativePlan("architecture").batches[0]!.files[0]!;

    expect(ReadingPlanFileSchema.safeParse(file).success).toBe(true);
    expect(
      ReadingPlanFileSchema.safeParse({
        ...file,
        roleInBatch: "invented-role",
      }).success,
    ).toBe(false);
    expect(
      ReadingPlanFileSchema.safeParse({
        ...file,
        evidence: [{ source: "source-code", detail: "Parsed source." }],
      }).success,
    ).toBe(false);
    expect(
      ReadingPlanFileSchema.safeParse({ ...file, estimatedBytes: -1 }).success,
    ).toBe(false);
  });
});

describe("buildReadingPlans", () => {
  it("builds exactly one plan for each current memory target", () => {
    const result = buildFixturePlans();

    expect(ReadingPlansSchema.safeParse(result).success).toBe(true);
    expect(result.plans.map((plan) => plan.kind)).toEqual(PLAN_KINDS);
    expect(result.plans.map((plan) => plan.targetMemoryFile)).toEqual(
      TARGET_MEMORY_FILES,
    );
  });

  it("allows evidence files to repeat across plans and batches", () => {
    const result = buildFixturePlans();
    const allPaths = result.plans.flatMap((plan) =>
      plan.batches.flatMap((batch) => batch.files.map((file) => file.path)),
    );

    expect(new Set(allPaths).size).toBeLessThan(allPaths.length);
    expect(result.stats.repeatedFileReferences).toBeGreaterThan(0);
  });

  it("builds meaningfully different architecture and testing plans", () => {
    const result = buildFixturePlans();
    const architecture = getPlan(result, "architecture");
    const testing = getPlan(result, "testing");
    const architecturePaths = getPlanPaths(architecture);
    const testingPaths = getPlanPaths(testing);

    expect(architecture.batches.map((batch) => batch.id)).not.toEqual(
      testing.batches.map((batch) => batch.id),
    );
    expect(architecturePaths).toContain("src/cli/cli.ts");
    expect(testingPaths).toContain("tests/orders.test.ts");
    expect(testingPaths).toContain("tests/fixtures/order.json");
  });

  it("prioritizes entrypoints, central source files, and contracts for architecture", () => {
    const architecture = getPlan(buildFixturePlans(), "architecture");
    const paths = getPlanPaths(architecture);
    const testOrFixtureCount = paths.filter(
      (filePath) =>
        filePath.startsWith("tests/") || filePath.includes("/fixtures/"),
    ).length;

    expect(paths).toEqual(
      expect.arrayContaining([
        "src/cli/cli.ts",
        "src/core/orders/service.ts",
        "src/core/orders/schema.ts",
      ]),
    );
    expect(testOrFixtureCount).toBeLessThan(paths.length / 2);
  });

  it("selects implemented workflow roles for business logic", () => {
    const input = createFixtureInput("/tmp/reading-plans-business");
    const businessLogic = getPlan(
      buildReadingPlans(input),
      "business-logic",
    );
    const files = businessLogic.batches.flatMap((batch) => batch.files);
    const implementedPaths = new Set(
      input.codebaseMap.files.map((file) => file.path),
    );

    expect(getPlanPaths(businessLogic)).toEqual(
      expect.arrayContaining([
        "src/cli/cli.ts",
        "src/core/orders/builder.ts",
        "src/core/orders/service.ts",
        "src/core/orders/writer.ts",
      ]),
    );
    expect(files.every((file) => implementedPaths.has(file.path))).toBe(true);
  });

  it("selects representative implemented roles for conventions", () => {
    const conventions = getPlan(buildFixturePlans(), "conventions");

    expect(getPlanPaths(conventions)).toEqual(
      expect.arrayContaining([
        "src/core/orders/builder.ts",
        "src/core/orders/schema.ts",
        "src/core/shared/format.ts",
        "tests/orders.test.ts",
      ]),
    );
  });

  it("adds warnings for missing selection categories", () => {
    const input = createFixtureInput("/tmp/reading-plans-missing");
    const codebaseMap: CodebaseMap = {
      ...input.codebaseMap,
      files: input.codebaseMap.files.filter(
        (file) => !file.isTest && !file.isFixture,
      ),
      clusters: input.codebaseMap.clusters.map((cluster) => ({
        ...cluster,
        tests: [],
        fixtures: [],
      })),
      warnings: ["No tests detected."],
    };

    const result = buildReadingPlans({ ...input, codebaseMap });
    const testing = getPlan(result, "testing");

    expect(testing.warnings.length).toBeGreaterThan(0);
    expect(
      testing.warnings.some((warning) =>
        warning.message.toLowerCase().includes("test"),
      ),
    ).toBe(true);
  });

  it("truncates oversized candidate sets deterministically and warns", () => {
    const input = createFixtureInput("/tmp/reading-plans-budget");
    const extraFiles = Array.from({ length: 120 }, (_, index) =>
      file(
        `src/core/bulk/service-${String(index).padStart(3, "0")}.ts`,
        ["source", "service"],
        [],
        20_000,
      ),
    );
    const fileIndex: FileIndex = {
      ...input.fileIndex,
      files: [...input.fileIndex.files, ...extraFiles],
    };
    const graph = createGraph(
      "/tmp/reading-plans-budget",
      fileIndex.files.map((entry) => entry.path),
    );
    const graphSummary = buildGraphSummary(graph);
    const codebaseMap = buildCodebaseMap({
      repoRoot: "/tmp/reading-plans-budget",
      fileIndex,
      repoContext: input.repoContext,
      repoGraph: graph,
      graphSummary,
    });
    const buildInput = {
      repoRoot: "/tmp/reading-plans-budget",
      fileIndex,
      repoContext: input.repoContext,
      repoGraph: graph,
      graphSummary,
      codebaseMap,
    };

    const first = buildReadingPlans(buildInput);
    const second = buildReadingPlans(buildInput);

    expect(
      first.plans.some(
        (plan) =>
          plan.budget.truncated ||
          plan.batches.some((batch) => batch.budget.truncated),
      ),
    ).toBe(true);
    expect(
      first.warnings.some((warning) =>
        warning.code.toLowerCase().includes("truncat"),
      ) ||
        first.plans.some((plan) =>
          plan.warnings.some((warning) =>
            warning.code.toLowerCase().includes("truncat"),
          ),
        ),
    ).toBe(true);
    expect(planFileOrdering(first)).toEqual(planFileOrdering(second));
  });

  it("returns stable plan, batch, file, warning, and evidence ordering", () => {
    const input = createFixtureInput("/tmp/reading-plans-stable");
    const first = buildReadingPlans(input);
    const second = buildReadingPlans(input);

    expect(normalizeGeneratedAt(first)).toEqual(normalizeGeneratedAt(second));
  });
});

describe("writeReadingPlansArtifact", () => {
  it("writes a validated artifact to the canonical path", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-reading-plans-"));
    const readingPlans = buildFixturePlans(tempDir);

    const outputPath = await writeReadingPlansArtifact({
      repoRoot: tempDir,
      readingPlans,
    });

    expect(outputPath).toBe(getReadingPlansPath(tempDir));
    const written = JSON.parse(await readFile(outputPath, "utf8"));
    expect(ReadingPlansSchema.safeParse(written).success).toBe(true);
  });

  it("validates before writing", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-reading-plans-"));
    const readingPlans = {
      ...buildFixturePlans(tempDir),
      schemaVersion: 2,
    } as unknown as ReadingPlans;

    await expect(
      writeReadingPlansArtifact({ repoRoot: tempDir, readingPlans }),
    ).rejects.toThrow();
  });
});

function representativeReadingPlans(): ReadingPlans {
  const plans = PLAN_KINDS.map(representativePlan);
  return {
    schemaVersion: 1,
    generatedAt: "2026-06-17T00:00:00.000Z",
    sourceArtifacts: {
      fileIndexSchemaVersion: 2,
      repoGraphVersion: 1,
      graphSummaryVersion: 1,
      codebaseMapSchemaVersion: 1,
    },
    plans,
    stats: {
      planCount: plans.length,
      batchCount: plans.length,
      uniqueFileCount: 1,
      repeatedFileReferences: plans.length - 1,
      estimatedTotalBytes: 100,
    },
    warnings: [],
  };
}

function representativePlan(kind: (typeof PLAN_KINDS)[number]): ReadingPlan {
  const target = TARGET_MEMORY_FILES[PLAN_KINDS.indexOf(kind)]!;
  return {
    kind,
    targetMemoryFile: target,
    title: `${kind} plan`,
    purpose: `Build deterministic evidence for ${kind}.`,
    inputStrategy: {
      agentFocus: `Understand ${kind}.`,
      shouldAnswer: ["What is supported by deterministic evidence?"],
      shouldAvoid: ["Unsupported claims."],
    },
    batches: [
      {
        id: "orientation",
        title: "Orientation",
        purpose: "Read a representative entrypoint.",
        order: 1,
        selectionRule: "Select an existing entrypoint.",
        files: [
          {
            path: "src/index.ts",
            roleInBatch: "entrypoint",
            reason: "The codebase map marks this file as an entrypoint.",
            evidence: [
              {
                source: "codebase-map",
                detail: "isEntrypoint is true.",
              },
            ],
            confidence: "observed",
            estimatedBytes: 100,
          },
        ],
        budget: { maxFiles: 8, estimatedBytes: 100, truncated: false },
      },
    ],
    budget: { maxFiles: 40, estimatedBytes: 100, truncated: false },
    warnings: [],
  };
}

function buildFixturePlans(repoRoot = "/tmp/reading-plans-fixture"): ReadingPlans {
  return buildReadingPlans(createFixtureInput(repoRoot));
}

function createFixtureInput(repoRoot: string) {
  const fileIndex: FileIndex = {
    schemaVersion: 2,
    generatedAt: "2026-06-17T00:00:00.000Z",
    files: [
      file("README.md", ["docs"], []),
      file("package.json", ["config", "project-config"], []),
      file("vitest.config.ts", ["config", "project-config"], [
        signal("testing", "vitest"),
      ]),
      file(
        "src/cli/cli.ts",
        ["source", "command", "entrypoint-candidate"],
        [
          signal("entrypoint", "package-bin", "package-json"),
          signal("cli", "commander"),
        ],
      ),
      file("src/core/orders/builder.ts", ["source", "builder"], []),
      file("src/core/orders/schema.ts", ["source", "schema", "type"], [
        signal("schema", "zod"),
        signal("validation", "zod"),
      ]),
      file("src/core/orders/service.ts", ["source", "service"], []),
      file("src/core/orders/writer.ts", ["source", "writer"], []),
      file("src/core/payments/service.ts", ["source", "service"], []),
      file("src/core/shared/format.ts", ["source", "utility"], []),
      file("tests/orders.test.ts", ["source", "test"], [
        signal("testing", "vitest"),
      ]),
      file("tests/payments.test.ts", ["source", "test"], [
        signal("testing", "vitest"),
      ]),
      file("tests/fixtures/order.json", ["fixture"], []),
    ],
    skippedFiles: [],
    warnings: [],
    stats: {
      totalFilesDiscovered: 13,
      includedFileCount: 13,
      skippedFileCount: 0,
      totalIncludedBytes: 1_300,
      byLanguage: {},
      byRole: {},
      bySkipReason: {},
    },
  };
  const graph = createGraph(
    repoRoot,
    fileIndex.files.map((entry) => entry.path),
  );
  const graphSummary = buildGraphSummary(graph);
  const repoContext = createRepoContext(repoRoot);
  const codebaseMap = buildCodebaseMap({
    repoRoot,
    fileIndex,
    repoContext,
    repoGraph: graph,
    graphSummary,
  });

  return {
    repoRoot,
    fileIndex,
    repoContext,
    repoGraph: graph,
    graphSummary,
    codebaseMap,
  };
}

function file(
  filePath: string,
  roles: FileRole[],
  signals: FileSignal[],
  sizeBytes = 100,
): FileIndexEntry {
  return {
    path: RepoRelativePathSchema.parse(filePath),
    extension: path.extname(filePath),
    sizeBytes,
    language: getLanguage(filePath),
    roles,
    confidence: "observed",
    includeReason: roles.includes("test")
      ? "test"
      : roles.includes("fixture")
        ? "fixture"
        : roles.includes("docs")
          ? "documentation"
          : roles.includes("project-config")
            ? "project-metadata"
            : "source",
    signals,
    tags: [],
  };
}

function signal(
  kind: FileSignal["kind"],
  value: string,
  source: FileSignal["source"] = "import",
): FileSignal {
  return {
    kind,
    value,
    source,
    confidence: "observed",
    reason: `Detected ${value}.`,
  };
}

function createRepoContext(repoRoot: string): RepoContext {
  return {
    repoRoot,
    generatedAt: "2026-06-17T00:00:00.000Z",
    stack: {
      framework: "",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: [],
      validation: ["Zod"],
      database: [],
      testFramework: ["Vitest"],
    },
    commands: {
      test: "pnpm test",
      typecheck: "pnpm typecheck",
    },
    importantFiles: [
      { path: "package.json", reason: "Project metadata and commands." },
    ],
    generatedDocs: {
      ...buildGeneratedDocPaths(),
      ticketTemplatePath: getTicketTemplateRelativePath(),
    },
  };
}

function createGraph(repoRoot: string, paths: string[]): RepoGraph {
  const candidateEdges: Array<[string, string]> = [
    ["src/cli/cli.ts", "src/core/orders/service.ts"],
    ["src/core/orders/service.ts", "src/core/orders/schema.ts"],
    ["src/core/orders/service.ts", "src/core/shared/format.ts"],
    ["src/core/orders/builder.ts", "src/core/orders/schema.ts"],
    ["src/core/orders/writer.ts", "src/core/orders/schema.ts"],
    ["src/core/payments/service.ts", "src/core/orders/service.ts"],
    ["tests/orders.test.ts", "src/core/orders/service.ts"],
    ["tests/payments.test.ts", "src/core/payments/service.ts"],
  ];
  const edges = candidateEdges.filter(
    ([from, to]) => paths.includes(from) && paths.includes(to),
  );

  return {
    generatedAt: "2026-06-17T00:00:00.000Z",
    graphVersion: 1,
    repoRoot,
    nodes: paths.map((filePath) => ({
      id: filePath,
      path: filePath,
      kind: "file",
      extension: path.extname(filePath),
      language: getGraphLanguage(filePath),
      sizeBytes: 100,
      tags: graphTags(filePath),
    })),
    edges: edges.map(([from, to]) => ({
      from,
      to,
      type: "imports",
      confidence: "high",
      source: "typescript-js-imports",
      importSpecifier: to,
    })),
    diagnostics: paths.includes("src/core/orders/writer.ts")
      ? [
          {
            level: "warning",
            code: "unresolved-import",
            file: "src/core/orders/writer.ts",
            message: "Could not resolve local import.",
          },
        ]
      : [],
    stats: {
      fileCount: paths.length,
      directoryCount: 0,
      containsEdgeCount: 0,
      importEdgeCount: edges.length,
      unresolvedImportCount: paths.includes("src/core/orders/writer.ts") ? 1 : 0,
      supportedLanguageFileCount: paths.length,
    },
  };
}

function getLanguage(filePath: string): NonNullable<FileIndexEntry["language"]> {
  if (filePath.endsWith(".md")) return "markdown";
  if (filePath.endsWith(".json")) return "json";
  return "typescript";
}

function getGraphLanguage(
  filePath: string,
): RepoGraph["nodes"][number]["language"] {
  const language = getLanguage(filePath);
  return language === "json" || language === "markdown"
    ? language
    : "typescript";
}

function graphTags(
  filePath: string,
): RepoGraph["nodes"][number]["tags"] {
  if (filePath === "src/cli/cli.ts") return ["source", "entrypoint-candidate"];
  if (filePath.startsWith("tests/")) return ["test"];
  if (filePath === "src/core/orders/service.ts") return ["source", "service"];
  if (filePath === "src/core/shared/format.ts") return ["source", "utility"];
  return ["source"];
}

function getPlan(
  readingPlans: ReadingPlans,
  kind: (typeof PLAN_KINDS)[number],
): ReadingPlan {
  return readingPlans.plans.find((plan) => plan.kind === kind)!;
}

function getPlanPaths(plan: ReadingPlan): string[] {
  return plan.batches.flatMap((batch) =>
    batch.files.map((file) => file.path),
  );
}

function planFileOrdering(readingPlans: ReadingPlans): string[][][] {
  return readingPlans.plans.map((plan) =>
    plan.batches.map((batch) => batch.files.map((file) => file.path)),
  );
}

function normalizeGeneratedAt(readingPlans: ReadingPlans): ReadingPlans {
  return { ...readingPlans, generatedAt: "stable" };
}
