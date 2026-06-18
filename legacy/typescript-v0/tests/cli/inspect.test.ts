import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RepoRelativePathSchema } from "../../src/core/models/path";
import { createBridgerConfig } from "../../src/core/project/create-bridger-config";
import { ensureBridgerLayout } from "../../src/core/project/ensure-bridger-layout";
import {
  getAgentsGeneratedExportPath,
  getFileIndexPath,
  getGraphSummaryPath,
  getRepoContextPath,
  getRepoGraphPath,
} from "../../src/core/project/bridger-paths";
import { writeBridgerConfig } from "../../src/core/project/write-bridger-config";

vi.mock("../../src/core/context-builder/build-repo-context", () => ({
  buildRepoContextArtifacts: vi.fn(),
}));

vi.mock("../../src/core/codebase-map/build-codebase-map", () => ({
  buildCodebaseMap: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-graph-summary", () => ({
  buildGraphSummary: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-repo-graph", () => ({
  buildRepoGraph: vi.fn(),
}));

vi.mock("../../src/core/reading-plans/build-reading-plans", () => ({
  buildReadingPlans: vi.fn(),
}));

vi.mock("../../src/core/repo-scanner/build-file-index", () => ({
  buildFileIndex: vi.fn(),
}));

vi.mock("../../src/core/utils/paths", async () => {
  const actual = await vi.importActual("../../src/core/utils/paths");

  return {
    ...actual,
    resolveRepoRoot: vi.fn(),
  };
});

vi.mock("../../src/shared/logger", () => ({
  logger: {
    info: vi.fn(),
    error: vi.fn(),
  },
}));

import {
  buildInspectResult,
  formatBytes,
  formatInspectSummary,
  runInspectCommand,
} from "../../src/cli/commands/inspect";
import { buildCodebaseMap } from "../../src/core/codebase-map/build-codebase-map";
import { buildRepoContextArtifacts } from "../../src/core/context-builder/build-repo-context";
import { buildGraphSummary } from "../../src/core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../src/core/repo-graph/build-repo-graph";
import { buildReadingPlans } from "../../src/core/reading-plans/build-reading-plans";
import { buildFileIndex } from "../../src/core/repo-scanner/build-file-index";
import { resolveRepoRoot } from "../../src/core/utils/paths";
import { logger } from "../../src/shared/logger";

import type { CodebaseMap } from "../../src/core/codebase-map/models/codebase-map";
import type {
  ReadingBatch,
  ReadingPlan,
  ReadingPlanFile,
  ReadingPlans,
  ReadingPlanWarning,
} from "../../src/core/reading-plans/models/reading-plans";

const mockedBuildRepoContextArtifacts = vi.mocked(buildRepoContextArtifacts);
const mockedBuildCodebaseMap = vi.mocked(buildCodebaseMap);
const mockedBuildGraphSummary = vi.mocked(buildGraphSummary);
const mockedBuildRepoGraph = vi.mocked(buildRepoGraph);
const mockedBuildReadingPlans = vi.mocked(buildReadingPlans);
const mockedBuildFileIndex = vi.mocked(buildFileIndex);
const mockedResolveRepoRoot = vi.mocked(resolveRepoRoot);
const mockedLogger = vi.mocked(logger);
let tempDir = "";

const artifacts = {
  repoContext: {
    repoRoot: "/repo",
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: ["Tailwind"],
      validation: ["Zod"],
      database: ["Supabase"],
      testFramework: ["Vitest"],
    },
    commands: {
      install: "pnpm install",
      dev: "pnpm dev",
      build: "pnpm build",
      lint: "pnpm lint",
      typecheck: "pnpm typecheck",
      test: "pnpm test",
      format: "pnpm format",
    },
    importantFiles: [
      {
        path: "README.md",
        reason: "Project README",
      },
      {
        path: "package.json",
        reason: "Package manifest and scripts/dependencies source",
      },
    ],
    generatedDocs: {
      repoAnalysisPath: ".bridger/memory/repo-analysis.md",
      architecturePath: ".bridger/memory/architecture.md",
      conventionsPath: ".bridger/memory/conventions.md",
      businessLogicPath: ".bridger/memory/business-logic.md",
      testingPath: ".bridger/memory/testing.md",
      ticketTemplatePath: ".bridger/templates/ticket-template.md",
    },
  },
  fileIndex: {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      {
        path: RepoRelativePathSchema.parse("README.md"),
        extension: ".md",
        sizeBytes: 1024,
        tags: ["readme", "documentation", "important"],
        reason: "Project README",
      },
      {
        path: RepoRelativePathSchema.parse("package.json"),
        extension: ".json",
        sizeBytes: 2048,
        tags: ["package", "config", "important"],
        reason: "Package manifest and scripts/dependencies source",
      },
    ],
    skippedFiles: [
      {
        path: RepoRelativePathSchema.parse("dist/bundle.js"),
        reason: "ignored",
      },
      {
        path: RepoRelativePathSchema.parse(".env.local"),
        reason: "sensitive",
      },
      {
        path: RepoRelativePathSchema.parse("assets/logo.png"),
        reason: "binary",
      },
    ],
    warnings: [
      {
        code: "ignored-file",
        message: "Ignored file skipped during inventory.",
        severity: "warning",
      },
      {
        code: "sensitive-file-skipped",
        message: "Skipped sensitive file .env.local.",
        filePath: RepoRelativePathSchema.parse(".env.local"),
        severity: "warning",
      },
    ],
    stats: {
      totalFilesDiscovered: 5,
      includedFileCount: 2,
      skippedFileCount: 3,
      totalIncludedBytes: 3072,
      byLanguage: {
        markdown: 1,
        json: 1,
      },
      byRole: {
        docs: 1,
        config: 1,
      },
      bySkipReason: {
        ignored: 1,
        sensitive: 1,
        binary: 1,
      },
    },
  },
};

const graphArtifacts = {
  graph: {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1,
    repoRoot: "/repo",
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
  },
  summary: {
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
    stats: {
      fileCount: 3,
      directoryCount: 1,
      containsEdgeCount: 2,
      importEdgeCount: 2,
      unresolvedImportCount: 1,
      supportedLanguageFileCount: 2,
    },
  },
};

const codebaseMapArtifact: CodebaseMap = {
  schemaVersion: 1,
  generatedAt: "2026-05-01T00:00:00.000Z",
  repo: {
    name: "repo",
    packageManager: "pnpm",
    detectedStack: ["Next.js", "TypeScript"],
  },
  stats: {
    fileCount: 2,
    sourceFileCount: 1,
    testFileCount: 0,
    fixtureFileCount: 0,
    docsFileCount: 1,
    configFileCount: 1,
    clusterCount: 1,
    entrypointCount: 1,
    centralFileCount: 1,
    unresolvedImportCount: 0,
  },
  entrypoints: [
    {
      path: "src/cli/cli.ts",
      kind: "node-cli",
      confidence: "observed",
      reasons: ["CLI entrypoint"],
    },
  ],
  clusters: [
    {
      id: "src-core-foo",
      title: "src/core/foo",
      rootPath: "src/core/foo",
      kind: "source",
      files: ["src/core/foo/service.ts"],
      roles: {
        source: 1,
      },
      entrypoints: [],
      centralFiles: [
        {
          path: "src/core/foo/service.ts",
          fanIn: 2,
          fanOut: 1,
          reasons: ["High fan-in and centrality"],
        },
      ],
      tests: [],
      fixtures: [],
      dependencies: [],
      consumers: [],
      confidence: "observed",
      reasons: ["Source cluster"],
      warnings: [],
    },
  ],
  files: [
    {
      path: "README.md",
      language: "markdown",
      roles: ["docs"],
      signals: [],
      clusterId: "docs",
      fanIn: 0,
      fanOut: 0,
      isCentral: false,
      isEntrypoint: false,
      isTest: false,
      isFixture: false,
    },
    {
      path: "package.json",
      language: "json",
      roles: ["config"],
      signals: [],
      clusterId: "config",
      fanIn: 0,
      fanOut: 0,
      isCentral: false,
      isEntrypoint: false,
      isTest: false,
      isFixture: false,
    },
  ],
  signals: {
    frameworks: {},
    schemas: {},
    validation: {},
    cli: {},
    testing: {},
    database: {},
  },
  unresolvedImports: {
    count: 0,
    byFile: [],
  },
  warnings: ["No tests detected."],
};

const readingPlansArtifact = createReadingPlansArtifact();

function createReadingPlansArtifact(): ReadingPlans {
  const plans = [
    makeReadingPlan(
      "repo-analysis",
      ".bridger/memory/repo-analysis.md",
      "Repository analysis reading plan",
      "Provide broad repository orientation.",
      [
        makeReadingBatch(1, "Project metadata and root orientation", [
          "README.md",
          "package.json",
        ]),
        makeReadingBatch(2, "Main entrypoints", ["src/cli/cli.ts"]),
      ],
      [],
      false,
    ),
    makeReadingPlan(
      "architecture",
      ".bridger/memory/architecture.md",
      "Architecture reading plan",
      "Explain entrypoints, subsystems, dependency flow, central files, and contract boundaries.",
      [
        makeReadingBatch(1, "Entrypoints and command surfaces", [
          "src/cli/cli.ts",
          "src/cli/commands/init.ts",
        ]),
        makeReadingBatch(2, "Source clusters and central files", [
          "src/core/repo-graph/build-repo-graph.ts",
          "src/core/codebase-map/build-codebase-map.ts",
        ]),
        makeReadingBatch(3, "Contracts, schemas, and types", [
          "src/core/models/file-index.ts",
        ]),
      ],
      [
        {
          code: "batch-truncated",
          message: "Batch source-clusters was truncated from 3 to 2 files.",
          planKind: "architecture",
          batchId: "source-clusters",
          severity: "warning",
        },
      ],
      false,
    ),
    makeReadingPlan(
      "business-logic",
      ".bridger/memory/business-logic.md",
      "Business logic reading plan",
      "Extract visible product workflows, user-facing behavior, and durable artifact contracts.",
      [
        makeReadingBatch(1, "User-facing workflow entrypoints", [
          "src/cli/cli.ts",
        ]),
        makeReadingBatch(2, "Workflow implementation files", [
          "src/core/context-builder/build-repo-context.ts",
        ]),
      ],
      [],
      false,
    ),
    makeReadingPlan(
      "conventions",
      ".bridger/memory/conventions.md",
      "Conventions reading plan",
      "Explain implementation style, organization, naming, typing, and recurring code patterns.",
      [
        makeReadingBatch(1, "Representative source files by role", [
          "src/core/models/file-index.ts",
        ]),
        makeReadingBatch(2, "Representative test style", [
          "tests/cli/inspect.test.ts",
        ]),
      ],
      [],
      false,
    ),
    makeReadingPlan(
      "testing",
      ".bridger/memory/testing.md",
      "Testing reading plan",
      "Explain test tooling, test patterns, fixtures, source relationships, and verification behavior.",
      [
        makeReadingBatch(1, "Test setup and commands", [
          "package.json",
          "vitest.config.ts",
        ]),
        makeReadingBatch(2, "Representative tests", [
          "tests/repo-scanner.test.ts",
          "tests/codebase-map.test.ts",
        ]),
        makeReadingBatch(3, "Fixtures and test data", [
          "tests/fixtures/sample.json",
        ]),
      ],
      [],
      false,
    ),
  ];

  const warnings: ReadingPlanWarning[] = [
    {
      code: "codebase-map-warning",
      message: "No tests detected.",
      severity: "warning",
    },
    {
      code: "file-index-warning",
      message: "Ignored file skipped during inventory.",
      severity: "warning",
    },
    {
      code: "batch-truncated",
      message: "Batch source-clusters was truncated from 3 to 2 files.",
      planKind: "architecture",
      batchId: "source-clusters",
      severity: "warning",
    },
  ];

  return {
    schemaVersion: 1,
    generatedAt: "2026-05-01T00:00:00.000Z",
    sourceArtifacts: {
      fileIndexSchemaVersion: 2,
      repoGraphVersion: 1,
      graphSummaryVersion: 1,
      codebaseMapSchemaVersion: 1,
    },
    plans,
    stats: {
      planCount: plans.length,
      batchCount: plans.reduce((total, plan) => total + plan.batches.length, 0),
      uniqueFileCount: new Set(
        plans.flatMap((plan) =>
          plan.batches.flatMap((batch) => batch.files.map((file) => file.path)),
        ),
      ).size,
      repeatedFileReferences: plans
        .flatMap((plan) => plan.batches.flatMap((batch) => batch.files))
        .length -
        new Set(
          plans.flatMap((plan) =>
            plan.batches.flatMap((batch) => batch.files.map((file) => file.path)),
          ),
        ).size,
      estimatedTotalBytes: plans
        .flatMap((plan) => plan.batches.flatMap((batch) => batch.files))
        .reduce((total, file) => total + file.estimatedBytes, 0),
    },
    warnings,
  };
}

function makeReadingPlan(
  kind: ReadingPlan["kind"],
  targetMemoryFile: string,
  title: string,
  purpose: string,
  batches: ReadingBatch[],
  warnings: ReadingPlanWarning[],
  truncated: boolean,
): ReadingPlan {
  const files = batches.flatMap((batch) => batch.files);

  return {
    kind,
    targetMemoryFile,
    title,
    purpose,
    inputStrategy: {
      agentFocus: `Focus on ${kind}.`,
      shouldAnswer: [`What does ${kind} cover?`],
      shouldAvoid: ["Full source dumps."],
    },
    batches: batches.map((batch, index) => ({
      ...batch,
      order: index + 1,
    })),
    budget: {
      maxFiles: 12,
      estimatedBytes: files.reduce((total, file) => total + file.estimatedBytes, 0),
      truncated,
    },
    warnings,
  };
}

function makeReadingBatch(
  order: number,
  title: string,
  paths: string[],
): ReadingBatch {
  const files = paths.map((path) => makeReadingPlanFile(path));

  return {
    id: title.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
    title,
    purpose: `Read ${title.toLowerCase()}.`,
    order,
    selectionRule: `Selected for ${title.toLowerCase()}.`,
    files,
    budget: {
      maxFiles: 3,
      estimatedBytes: files.reduce((total, file) => total + file.estimatedBytes, 0),
      truncated: false,
    },
  };
}

function makeReadingPlanFile(path: string): ReadingPlanFile {
  return {
    path,
    roleInBatch: "supporting-context",
    reason: `Relevant to ${path}.`,
    evidence: [
      {
        source: "codebase-map",
        detail: `Selected ${path} for preview diagnostics.`,
      },
    ],
    confidence: "observed",
    estimatedBytes: 128,
  };
}

beforeEach(() => {
  mockedBuildRepoContextArtifacts.mockReset();
  mockedBuildCodebaseMap.mockReset();
  mockedBuildGraphSummary.mockReset();
  mockedBuildRepoGraph.mockReset();
  mockedBuildReadingPlans.mockReset();
  mockedBuildFileIndex.mockReset();
  mockedResolveRepoRoot.mockReset();
  mockedLogger.info.mockReset();
  mockedLogger.error.mockReset();
  process.exitCode = undefined;
});

afterEach(async () => {
  if (tempDir.length > 0) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

function getMockedBuildResult() {
  mockedBuildRepoContextArtifacts.mockResolvedValue(artifacts as never);
  mockedBuildCodebaseMap.mockReturnValue(codebaseMapArtifact as never);
  mockedBuildReadingPlans.mockReturnValue(readingPlansArtifact as never);
}

describe("formatInspectSummary", () => {
  it("renders lists and commands in a stable readable format", () => {
    const summary = formatInspectSummary({
      repoRoot: "/repo",
      stack: {
        framework: "Next.js",
        language: "TypeScript",
        packageManager: "pnpm",
        styling: ["Tailwind", "shadcn/ui"],
        validation: ["Zod"],
        database: ["Supabase"],
        testFramework: ["Vitest", "Playwright"],
      },
      commands: {
        install: "pnpm install",
        dev: "pnpm dev",
        build: "pnpm build",
        lint: "pnpm lint",
        typecheck: "pnpm typecheck",
        test: "pnpm test",
        format: "pnpm format",
      },
      indexedFileCount: 183,
    });

    expect(summary).toContain("bridger Inspect");
    expect(summary).toContain("Repo: /repo");
    expect(summary).toContain("Styling: Tailwind, shadcn/ui");
    expect(summary).toContain("Validation: Zod");
    expect(summary).toContain("Database: Supabase");
    expect(summary).toContain("Testing: Vitest, Playwright");
    expect(summary).toContain("- install: pnpm install");
    expect(summary).toContain("- dev: pnpm dev");
    expect(summary).toContain("- build: pnpm build");
    expect(summary).toContain("- lint: pnpm lint");
    expect(summary).toContain("- typecheck: pnpm typecheck");
    expect(summary).toContain("- test: pnpm test");
    expect(summary).toContain("- format: pnpm format");
    expect(summary).toContain("Indexed files: 183");
  });

  it("renders empty collections and missing commands as none", () => {
    const summary = formatInspectSummary({
      repoRoot: "/repo",
      stack: {
        framework: "unknown",
        language: "unknown",
        packageManager: "unknown",
        styling: [],
        validation: [],
        database: [],
        testFramework: [],
      },
      commands: {},
      indexedFileCount: 0,
    });

    expect(summary).toContain("Framework: unknown");
    expect(summary).toContain("Styling: none");
    expect(summary).toContain("Validation: none");
    expect(summary).toContain("Database: none");
    expect(summary).toContain("Testing: none");
    expect(summary).toContain("Commands:\n- none");
  });
});

describe("formatBytes", () => {
  it("renders byte counts with simple readable units", () => {
    expect(formatBytes(undefined)).toBe("unknown");
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
  });
});

describe("buildInspectResult", () => {
  it("joins important file metadata from the file index", async () => {
    getMockedBuildResult();

    const result = await buildInspectResult("/repo");

    expect(result.repoContext).toEqual(artifacts.repoContext);
    expect(result.fileIndex).toEqual(artifacts.fileIndex);
    expect(result.projectState).toEqual(
      expect.objectContaining({
        status: "uninitialized",
        reason: "missing-bridger-dir",
        configPath: "/repo/.bridger/config.json",
        artifactsDir: "/repo/.bridger/artifacts",
        memoryDir: "/repo/.bridger/memory",
        skillsDir: "/repo/.bridger/skills",
        templatesDir: "/repo/.bridger/templates",
        exportsDir: "/repo/.bridger/exports",
      }),
    );
    expect(result.inspection.indexedFileCount).toBe(2);
    expect(result.inspection.importantFileCount).toBe(2);
    expect(result.inspection.estimatedImportantFilesSizeBytes).toBe(3072);
    expect(result.inspection.importantFiles).toEqual([
      {
        path: "README.md",
        reason: "Project README",
        sizeBytes: 1024,
        tags: ["readme", "documentation", "important"],
      },
      {
        path: "package.json",
        reason: "Package manifest and scripts/dependencies source",
        sizeBytes: 2048,
        tags: ["package", "config", "important"],
      },
    ]);
  });
});

describe("runInspectCommand", () => {
  it("uses deterministic scanner pieces and logs the summary without requiring the LLM", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    getMockedBuildResult();

    await runInspectCommand({ repo: "." });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedBuildRepoContextArtifacts).toHaveBeenCalledWith("/repo");
    expect(mockedLogger.info).toHaveBeenCalledTimes(1);
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Repo: /repo");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Framework: Next.js");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Indexed files: 2");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Project state:");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Status: uninitialized");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Skills dir:");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Templates dir:");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Canonical artifact files:");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("- file-index.json: missing");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Canonical memory files:");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("- repo-analysis.md: missing");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain(
      "Canonical skills/templates/exports:",
    );
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain(
      "- ticket-template.md: missing",
    );
    expect(process.exitCode).toBeUndefined();
  });

  it("prints initialized project state with canonical directories and files", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-inspect-"));
    await ensureBridgerLayout(tempDir);
    await writeBridgerConfig(
      tempDir,
      createBridgerConfig({
        repoRoot: tempDir,
        mode: "existing",
        projectName: "demo",
        detectedStack: ["Next.js", "TypeScript"],
        packageManager: "pnpm",
        now: new Date("2026-05-01T00:00:00.000Z"),
      }),
    );
    await fs.writeFile(getFileIndexPath(tempDir), "{}\n", "utf8");
    await fs.writeFile(getRepoContextPath(tempDir), "{}\n", "utf8");
    await fs.writeFile(getRepoGraphPath(tempDir), "{}\n", "utf8");
    await fs.writeFile(getGraphSummaryPath(tempDir), "{}\n", "utf8");
    await fs.writeFile(getAgentsGeneratedExportPath(tempDir), "# Agents\n", "utf8");

    mockedResolveRepoRoot.mockReturnValue(tempDir);
    getMockedBuildResult();

    await runInspectCommand({ repo: "." });

    const output = String(mockedLogger.info.mock.calls[0]?.[0]);
    expect(output).toContain("Status: initialized");
    expect(output).toContain("- Project name: demo");
    expect(output).toContain("- Project mode: existing");
    expect(output).toContain("- Config detected stack: Next.js, TypeScript");
    expect(output).toContain("- Config package manager: pnpm");
    expect(output).toContain(`- Config: ${path.join(tempDir, ".bridger", "config.json")} (exists)`);
    expect(output).toContain(`- Artifacts dir: ${path.join(tempDir, ".bridger", "artifacts")} (exists)`);
    expect(output).toContain(`- Memory dir: ${path.join(tempDir, ".bridger", "memory")} (exists)`);
    expect(output).toContain(`- Skills dir: ${path.join(tempDir, ".bridger", "skills")} (exists)`);
    expect(output).toContain(`- Templates dir: ${path.join(tempDir, ".bridger", "templates")} (exists)`);
    expect(output).toContain(`- Exports dir: ${path.join(tempDir, ".bridger", "exports")} (exists)`);
    expect(output).toContain("- file-index.json: exists");
    expect(output).toContain("- repo-context.json: exists");
    expect(output).toContain("- repo-graph.json: exists");
    expect(output).toContain("- graph-summary.json: exists");
    expect(output).toContain("- codebase-map.json: missing");
    expect(output).toContain("- reading-plans.json: missing");
    expect(output).toContain("- ticket-template.md: exists");
    expect(output).toContain("- AGENTS.generated.md: exists");
    expect(output).toContain("- CLAUDE.generated.md: missing");
    expect(output).toContain("- root AGENTS.md: missing");
    expect(process.exitCode).toBeUndefined();
  });

  it("prints invalid config state as a clear diagnostic", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-inspect-"));
    await fs.mkdir(path.join(tempDir, ".bridger"), { recursive: true });
    await fs.writeFile(path.join(tempDir, ".bridger", "config.json"), "{", "utf8");

    mockedResolveRepoRoot.mockReturnValue(tempDir);
    getMockedBuildResult();

    await runInspectCommand({ repo: "." });

    const output = String(mockedLogger.info.mock.calls[0]?.[0]);
    expect(output).toContain("Status: invalid");
    expect(output).toContain("Reason: invalid-config");
    expect(output).toContain("Message:");
    expect(process.exitCode).toBeUndefined();
  });

  it("prints a live graph and cluster inspection report without persisted artifacts", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    getMockedBuildResult();
    mockedBuildRepoGraph.mockResolvedValue(graphArtifacts.graph as never);
    mockedBuildGraphSummary.mockReturnValue(graphArtifacts.summary as never);

    await runInspectCommand({ repo: ".", graph: true });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedBuildRepoContextArtifacts).toHaveBeenCalledWith("/repo");
    expect(mockedBuildFileIndex).not.toHaveBeenCalled();
    expect(mockedBuildRepoGraph).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex: artifacts.fileIndex,
    });
    expect(mockedBuildGraphSummary).toHaveBeenCalledWith(graphArtifacts.graph);
    expect(mockedBuildCodebaseMap).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex: artifacts.fileIndex,
      repoContext: artifacts.repoContext,
      repoGraph: graphArtifacts.graph,
      graphSummary: graphArtifacts.summary,
    });
    expect(mockedBuildReadingPlans).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex: artifacts.fileIndex,
      repoContext: artifacts.repoContext,
      repoGraph: graphArtifacts.graph,
      graphSummary: graphArtifacts.summary,
      codebaseMap: codebaseMapArtifact,
    });
    expect(mockedLogger.info).toHaveBeenCalledTimes(1);
    const output = String(mockedLogger.info.mock.calls[0]?.[0]);
    expect(output).toContain("Repo graph");
    expect(output).toContain("Repository Inventory");
    expect(output).toContain("Included files: 2");
    expect(output).toContain("Skipped files: 3");
    expect(output).toContain("Warnings: 2");
    expect(output).toContain("Top skip reasons:");
    expect(output).toContain("Top roles:");
    expect(output).toContain("Languages:");
    expect(output).toContain("Diagnostics");
    expect(output).toContain("FileIndex warnings: 2");
    expect(output).toContain("CodebaseMap warnings: 1");
    expect(output).toContain("ReadingPlans warnings: 3");
    expect(output).toContain("- Plan warnings:");
    expect(output).toContain("  - architecture: 1");
    expect(output).toContain("Reading Plans");
    expect(output).toContain(
      "- repo-analysis: 2 batches, 3 file references, 3 unique files, 0 warnings, truncated: no",
    );
    expect(output).toContain(
      "- architecture: 3 batches, 5 file references, 5 unique files, 1 warning, truncated: no",
    );
    expect(output).toContain(
      "- business-logic: 2 batches, 2 file references, 2 unique files, 0 warnings, truncated: no",
    );
    expect(output).toContain(
      "- conventions: 2 batches, 2 file references, 2 unique files, 0 warnings, truncated: no",
    );
    expect(output).toContain(
      "- testing: 3 batches, 5 file references, 5 unique files, 0 warnings, truncated: no",
    );
    expect(output).toContain("Reading Plan Preview");
    expect(output).toContain("architecture\n- Entrypoints and command surfaces");
    expect(output).toContain("testing\n- Test setup and commands");
    expect(output).toContain("Files: 3");
    expect(output).toContain("Import edges: 2");
    expect(output).toContain("Architecture-first order preview");
    expect(output).toContain("1. README.md");
    expect(output).toContain("Clusters");
    expect(output).toContain("src-core-foo");
    expect(output).not.toContain("<<<FILE_CONTENT_START");
    expect(output).not.toContain("\"schemaVersion\"");
    expect(process.exitCode).toBeUndefined();
  });

  it("prints a deterministic important-files preview when requested", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    getMockedBuildResult();

    await runInspectCommand({ repo: ".", importantFiles: true });

    expect(mockedLogger.info).toHaveBeenCalledTimes(2);
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("bridger Inspect");
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain("Important files: 2");
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain("- README.md");
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain(
      "Size: 1.0 KB",
    );
  });

  it("prints a context preview when requested", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    getMockedBuildResult();

    await runInspectCommand({ repo: ".", context: true });

    expect(mockedLogger.info).toHaveBeenCalledTimes(2);
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain("Context preview");
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain(
      "Estimated selected context size: 3.0 KB",
    );
    expect(mockedLogger.info.mock.calls[1]?.[0]).toContain("Important files: 2");
  });

  it("prints JSON only when requested", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    try {
      mockedResolveRepoRoot.mockReturnValue("/repo");
      getMockedBuildResult();

      await runInspectCommand({ repo: ".", json: true, context: true, importantFiles: true });

      expect(mockedLogger.info).not.toHaveBeenCalled();
      expect(logSpy).toHaveBeenCalledTimes(1);

      const rawJson = String(logSpy.mock.calls[0]?.[0]);
      const parsed = JSON.parse(rawJson) as {
        repoContext: typeof artifacts.repoContext;
        fileIndex: typeof artifacts.fileIndex;
        inspection: {
          indexedFileCount: number;
          importantFileCount: number;
          estimatedImportantFilesSizeBytes?: number;
          importantFiles: Array<{
            path: string;
            reason: string;
            sizeBytes?: number;
            tags?: string[];
          }>;
        };
      };

      expect(parsed.repoContext).toEqual(artifacts.repoContext);
      expect(parsed.fileIndex).toEqual(artifacts.fileIndex);
      expect(parsed.inspection.indexedFileCount).toBe(2);
      expect(parsed.inspection.importantFileCount).toBe(2);
      expect(parsed.inspection.estimatedImportantFilesSizeBytes).toBe(3072);
    } finally {
      logSpy.mockRestore();
    }
  });

  it("sets a non-zero exit code only on real errors", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    mockedBuildRepoContextArtifacts.mockRejectedValue(new Error("bad repo"));
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    try {
      await runInspectCommand({ repo: "." });

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "bridger inspect failed: bad repo",
      );
      expect(process.exitCode).toBe(1);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
