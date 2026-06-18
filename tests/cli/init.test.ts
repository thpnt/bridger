import { beforeEach, describe, expect, it, vi } from "vitest";

import { RepoRelativePathSchema } from "../../src/core/models/path";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
} from "../../src/core/project/bridger-paths";

const logEntries = vi.hoisted(() => [] as string[]);

vi.mock("../../src/core/codebase-map/build-codebase-map", () => ({
  buildCodebaseMap: vi.fn(),
}));

vi.mock("../../src/core/codebase-map/write-codebase-map", () => ({
  writeCodebaseMapArtifact: vi.fn(),
}));

vi.mock("../../src/core/context-builder/build-repo-context", () => ({
  buildRepoContextArtifacts: vi.fn(),
}));

vi.mock("../../src/core/output/ensure-output-dirs", () => ({
  ensureOutputDirs: vi.fn(),
}));

vi.mock("../../src/core/output/write-json", () => ({
  writeJson: vi.fn(),
}));

vi.mock("../../src/core/project/write-bridger-config", () => ({
  writeBridgerConfig: vi.fn(),
}));

vi.mock("../../src/core/reading-plans/build-reading-plans", () => ({
  buildReadingPlans: vi.fn(),
}));

vi.mock("../../src/core/reading-plans/write-reading-plans", () => ({
  writeReadingPlansArtifact: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-graph-summary", () => ({
  buildGraphSummary: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-repo-graph", () => ({
  buildRepoGraph: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/write-repo-graph", () => ({
  writeRepoGraphArtifacts: vi.fn(),
}));

vi.mock("../../src/core/utils/paths", async () => {
  const actual = await vi.importActual<typeof import("../../src/core/utils/paths")>(
    "../../src/core/utils/paths",
  );

  return {
    ...actual,
    resolveRepoRoot: vi.fn(),
  };
});

vi.mock("../../src/shared/logger", () => ({
  logger: {
    info: vi.fn((message: string) => {
      logEntries.push(`info:${message}`);
    }),
    warn: vi.fn(),
    debug: vi.fn((message: string) => {
      logEntries.push(`debug:${message}`);
    }),
    error: vi.fn(),
  },
}));

import { runInitCommand } from "../../src/cli/commands/init";
import { buildCodebaseMap } from "../../src/core/codebase-map/build-codebase-map";
import { writeCodebaseMapArtifact } from "../../src/core/codebase-map/write-codebase-map";
import { buildRepoContextArtifacts } from "../../src/core/context-builder/build-repo-context";
import { ensureOutputDirs } from "../../src/core/output/ensure-output-dirs";
import { writeJson } from "../../src/core/output/write-json";
import { writeBridgerConfig } from "../../src/core/project/write-bridger-config";
import { buildReadingPlans } from "../../src/core/reading-plans/build-reading-plans";
import { writeReadingPlansArtifact } from "../../src/core/reading-plans/write-reading-plans";
import { buildGraphSummary } from "../../src/core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../src/core/repo-graph/build-repo-graph";
import { writeRepoGraphArtifacts } from "../../src/core/repo-graph/write-repo-graph";
import { resolveRepoRoot } from "../../src/core/utils/paths";

const mockedBuildCodebaseMap = vi.mocked(buildCodebaseMap);
const mockedWriteCodebaseMapArtifact = vi.mocked(writeCodebaseMapArtifact);
const mockedBuildRepoContextArtifacts = vi.mocked(buildRepoContextArtifacts);
const mockedEnsureOutputDirs = vi.mocked(ensureOutputDirs);
const mockedWriteJson = vi.mocked(writeJson);
const mockedWriteBridgerConfig = vi.mocked(writeBridgerConfig);
const mockedBuildReadingPlans = vi.mocked(buildReadingPlans);
const mockedWriteReadingPlansArtifact = vi.mocked(writeReadingPlansArtifact);
const mockedBuildGraphSummary = vi.mocked(buildGraphSummary);
const mockedBuildRepoGraph = vi.mocked(buildRepoGraph);
const mockedWriteRepoGraphArtifacts = vi.mocked(writeRepoGraphArtifacts);
const mockedResolveRepoRoot = vi.mocked(resolveRepoRoot);

const repoContext = {
  repoRoot: "/repo",
  generatedAt: "2026-05-01T00:00:00.000Z",
  stack: {
    framework: "Next.js",
    language: "TypeScript",
    packageManager: "pnpm",
    styling: ["Tailwind"],
    validation: ["Zod"],
    database: [],
    testFramework: ["Vitest"],
  },
  commands: {
    install: "pnpm install",
    test: "pnpm test",
  },
  importantFiles: [
    {
      path: "README.md",
      reason: "Project README",
    },
  ],
  generatedDocs: {
    ...buildGeneratedDocPaths(),
    ticketTemplatePath: getTicketTemplateRelativePath(),
  },
};

const fileIndex = {
  schemaVersion: 2 as const,
  generatedAt: "2026-05-01T00:00:00.000Z",
  files: [
    {
      path: RepoRelativePathSchema.parse("README.md"),
      extension: ".md",
      sizeBytes: 100,
      language: "markdown" as const,
      roles: ["docs" as const],
      confidence: "inferred" as const,
      includeReason: "documentation" as const,
      signals: [],
      tags: ["readme"],
    },
  ],
  skippedFiles: [],
  warnings: [],
  stats: {
    totalFilesDiscovered: 1,
    includedFileCount: 1,
    skippedFileCount: 0,
    totalIncludedBytes: 100,
    byLanguage: { markdown: 1 },
    byRole: { docs: 1 },
    bySkipReason: {},
  },
};

const graph = {
  generatedAt: "2026-05-01T00:00:00.000Z",
  graphVersion: 1 as const,
  repoRoot: "/repo",
  nodes: [],
  edges: [],
  diagnostics: [],
  stats: {
    fileCount: 1,
    directoryCount: 0,
    containsEdgeCount: 0,
    importEdgeCount: 0,
    unresolvedImportCount: 0,
    supportedLanguageFileCount: 0,
  },
};

const graphSummary = {
  generatedAt: "2026-05-01T00:00:00.000Z",
  graphVersion: 1 as const,
  entrypoints: [],
  rootFiles: ["README.md"],
  configFiles: [],
  docsFiles: ["README.md"],
  highFanInFiles: [],
  highFanOutFiles: [],
  leafFiles: ["README.md"],
  isolatedFiles: [],
  architectureFirstOrder: ["README.md"],
  dependencyFirstOrder: ["README.md"],
  stats: graph.stats,
};

const codebaseMap = { schemaVersion: 1 };
const readingPlans = { schemaVersion: 1, plans: [] };

beforeEach(() => {
  logEntries.length = 0;
  process.exitCode = undefined;
  vi.clearAllMocks();

  mockedResolveRepoRoot.mockReturnValue("/repo");
  mockedEnsureOutputDirs.mockResolvedValue(undefined);
  mockedBuildRepoContextArtifacts.mockResolvedValue({
    repoContext,
    fileIndex,
    importantFiles: [
      {
        path: "README.md",
        reason: "Project README",
        content: "# README\n",
      },
    ],
  });
  mockedWriteBridgerConfig.mockResolvedValue(undefined);
  mockedBuildRepoGraph.mockResolvedValue(graph);
  mockedBuildGraphSummary.mockReturnValue(graphSummary);
  mockedBuildCodebaseMap.mockReturnValue(codebaseMap as never);
  mockedBuildReadingPlans.mockReturnValue(readingPlans as never);
  mockedWriteJson.mockResolvedValue(undefined);
  mockedWriteRepoGraphArtifacts.mockResolvedValue({
    repoGraphPath: "/repo/.bridger/artifacts/repo-graph.json",
    graphSummaryPath: "/repo/.bridger/artifacts/graph-summary.json",
  });
  mockedWriteCodebaseMapArtifact.mockResolvedValue(
    "/repo/.bridger/artifacts/codebase-map.json",
  );
  mockedWriteReadingPlansArtifact.mockResolvedValue(
    "/repo/.bridger/artifacts/reading-plans.json",
  );
});

describe("runInitCommand", () => {
  it("writes deterministic artifacts and succeeds without an API key", async () => {
    await runInitCommand({ repo: "." });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedEnsureOutputDirs).toHaveBeenCalledWith("/repo");
    expect(mockedBuildRepoContextArtifacts).toHaveBeenCalledWith("/repo");
    expect(mockedBuildRepoGraph).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex,
    });
    expect(mockedBuildGraphSummary).toHaveBeenCalledWith(graph);
    expect(mockedBuildCodebaseMap).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary,
    });
    expect(mockedBuildReadingPlans).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex,
      repoContext,
      repoGraph: graph,
      graphSummary,
      codebaseMap,
    });
    expect(mockedWriteJson).toHaveBeenCalledWith(
      "/repo/.bridger/artifacts/repo-context.json",
      repoContext,
    );
    expect(mockedWriteJson).toHaveBeenCalledWith(
      "/repo/.bridger/artifacts/file-index.json",
      fileIndex,
    );
    expect(mockedWriteRepoGraphArtifacts).toHaveBeenCalledTimes(1);
    expect(mockedWriteCodebaseMapArtifact).toHaveBeenCalledTimes(1);
    expect(mockedWriteReadingPlansArtifact).toHaveBeenCalledTimes(1);
    expect(logEntries).toContain(
      "debug:bridger init: deterministic artifacts written",
    );
    expect(logEntries.at(-1)).toContain("SUCCESS: bridger init complete");
    expect(logEntries.at(-1)).not.toContain(".bridger/memory/");
    expect(logEntries.at(-1)).not.toContain("AGENTS.generated.md");
    expect(process.exitCode).toBeUndefined();
  });

  it("reports deterministic pipeline failures clearly", async () => {
    mockedBuildRepoGraph.mockRejectedValueOnce(new Error("graph failed"));
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    try {
      await runInitCommand({ repo: "." });

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "bridger init failed: graph failed",
      );
      expect(mockedWriteJson).not.toHaveBeenCalled();
      expect(process.exitCode).toBe(1);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
