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

vi.mock("../../src/core/repo-graph/build-graph-summary", () => ({
  buildGraphSummary: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-repo-graph", () => ({
  buildRepoGraph: vi.fn(),
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
import { buildRepoContextArtifacts } from "../../src/core/context-builder/build-repo-context";
import { buildGraphSummary } from "../../src/core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../src/core/repo-graph/build-repo-graph";
import { buildFileIndex } from "../../src/core/repo-scanner/build-file-index";
import { resolveRepoRoot } from "../../src/core/utils/paths";
import { logger } from "../../src/shared/logger";

const mockedBuildRepoContextArtifacts = vi.mocked(buildRepoContextArtifacts);
const mockedBuildGraphSummary = vi.mocked(buildGraphSummary);
const mockedBuildRepoGraph = vi.mocked(buildRepoGraph);
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
      agentRulesPath: ".bridger/memory/agent-rules.md",
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

beforeEach(() => {
  mockedBuildRepoContextArtifacts.mockReset();
  mockedBuildGraphSummary.mockReset();
  mockedBuildRepoGraph.mockReset();
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
    expect(mockedLogger.info).toHaveBeenCalledTimes(1);
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Repo graph");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Files: 3");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Import edges: 2");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Architecture-first order preview");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("1. README.md");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Clusters");
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
