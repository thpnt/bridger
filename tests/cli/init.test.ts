import { beforeEach, describe, expect, it, vi } from "vitest";

import { RepoRelativePathSchema } from "../../src/core/models/path";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
} from "../../src/core/project/bridger-paths";

const logEntries = vi.hoisted(() => [] as string[]);
const knowledgeDocCalls = vi.hoisted(
  () =>
    [] as Array<{
      spec?: {
        key?: string;
      };
      generationInput?: unknown;
    }>,
);

vi.mock("../../src/core/context-builder/build-repo-context", () => ({
  buildRepoContextArtifacts: vi.fn(),
}));

vi.mock("../../src/core/doc-generator/generators/generate-knowledge-doc", () => ({
  generateKnowledgeDoc: vi.fn().mockImplementation(async (input) => {
    knowledgeDocCalls.push(input);
    return `generated:${input.spec.key}`;
  }),
}));

vi.mock("../../src/core/output/ensure-output-dirs", () => ({
  ensureOutputDirs: vi.fn(),
}));

vi.mock("../../src/core/project/write-bridger-config", () => ({
  writeBridgerConfig: vi.fn(),
}));

vi.mock("../../src/core/output/write-json", () => ({
  writeJson: vi.fn(),
}));

vi.mock("../../src/core/output/write-markdown", () => ({
  writeMarkdown: vi.fn(),
}));

vi.mock("../../src/core/output/upsert-generated-markdown-block", () => ({
  upsertGeneratedMarkdownBlock: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-graph-summary", () => ({
  buildGraphSummary: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/build-repo-graph", () => ({
  buildRepoGraph: vi.fn(),
}));

vi.mock("../../src/core/repo-graph/read-graph-ordered-files", () => ({
  readGraphOrderedFiles: vi.fn(),
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
    warn: vi.fn((message: string) => {
      logEntries.push(`warn:${message}`);
    }),
    debug: vi.fn((message: string) => {
      logEntries.push(`debug:${message}`);
    }),
    error: vi.fn((message: string) => {
      logEntries.push(`error:${message}`);
    }),
  },
}));

import { runInitCommand } from "../../src/cli/commands/init";
import { buildRepoContextArtifacts } from "../../src/core/context-builder/build-repo-context";
import { generateKnowledgeDoc } from "../../src/core/doc-generator/generators/generate-knowledge-doc";
import { ensureOutputDirs } from "../../src/core/output/ensure-output-dirs";
import { writeBridgerConfig } from "../../src/core/project/write-bridger-config";
import { upsertGeneratedMarkdownBlock } from "../../src/core/output/upsert-generated-markdown-block";
import { writeJson } from "../../src/core/output/write-json";
import { writeMarkdown } from "../../src/core/output/write-markdown";
import { buildGraphSummary } from "../../src/core/repo-graph/build-graph-summary";
import { buildRepoGraph } from "../../src/core/repo-graph/build-repo-graph";
import { readGraphOrderedFiles } from "../../src/core/repo-graph/read-graph-ordered-files";
import { writeRepoGraphArtifacts } from "../../src/core/repo-graph/write-repo-graph";
import { resolveRepoRoot } from "../../src/core/utils/paths";
import { logger } from "../../src/shared/logger";

const mockedBuildRepoContextArtifacts = vi.mocked(buildRepoContextArtifacts);
const mockedGenerateKnowledgeDoc = vi.mocked(generateKnowledgeDoc);
const mockedEnsureOutputDirs = vi.mocked(ensureOutputDirs);
const mockedWriteBridgerConfig = vi.mocked(writeBridgerConfig);
const mockedWriteJson = vi.mocked(writeJson);
const mockedWriteMarkdown = vi.mocked(writeMarkdown);
const mockedUpsertGeneratedMarkdownBlock = vi.mocked(upsertGeneratedMarkdownBlock);
const mockedBuildGraphSummary = vi.mocked(buildGraphSummary);
const mockedBuildRepoGraph = vi.mocked(buildRepoGraph);
const mockedReadGraphOrderedFiles = vi.mocked(readGraphOrderedFiles);
const mockedWriteRepoGraphArtifacts = vi.mocked(writeRepoGraphArtifacts);
const mockedResolveRepoRoot = vi.mocked(resolveRepoRoot);
const mockedLogger = vi.mocked(logger);

function readImportantFilesFromGenerationCall(input: {
  generationInput?: unknown;
}): Array<{
  path: string;
  reason: string;
  content: string;
}> | undefined {
  if (
    typeof input.generationInput !== "object" ||
    input.generationInput === null ||
    !("importantFiles" in input.generationInput)
  ) {
    return undefined;
  }

  const generationInput = input.generationInput as {
    importantFiles?: Array<{
      path: string;
      reason: string;
      content: string;
    }>;
  };

  return generationInput.importantFiles;
}

function createRepoContext() {
  return {
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
}

function createFileIndex() {
  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      {
        path: RepoRelativePathSchema.parse("README.md"),
        extension: ".md",
        sizeBytes: 100,
        tags: ["readme"],
      },
      {
        path: RepoRelativePathSchema.parse("src/app/page.tsx"),
        extension: ".tsx",
        sizeBytes: 200,
        tags: ["app", "route"],
      },
    ],
  };
}

function createRepoGraph() {
  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1 as const,
    repoRoot: "/repo",
    nodes: [],
    edges: [],
    diagnostics: [],
    stats: {
      fileCount: 2,
      directoryCount: 1,
      containsEdgeCount: 2,
      importEdgeCount: 1,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 1,
    },
  };
}

function createGraphSummary() {
  return {
    generatedAt: "2026-05-01T00:00:00.000Z",
    graphVersion: 1 as const,
    entrypoints: ["src/app/page.tsx"],
    rootFiles: ["README.md", "package.json"],
    configFiles: ["package.json"],
    docsFiles: ["README.md"],
    highFanInFiles: [],
    highFanOutFiles: [],
    leafFiles: ["README.md"],
    isolatedFiles: [],
    architectureFirstOrder: ["package.json", "README.md", "src/app/page.tsx"],
    dependencyFirstOrder: ["src/app/page.tsx", "package.json", "README.md"],
    stats: {
      fileCount: 2,
      directoryCount: 1,
      containsEdgeCount: 2,
      importEdgeCount: 1,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 1,
    },
  };
}

function createGraphOrderedFileContext() {
  return {
    files: [
      {
        path: "package.json",
        reason: "Project config file",
        order: 1,
        content: '{"name":"repo"}\n',
      },
      {
        path: "README.md",
        reason: "Root documentation file",
        order: 2,
        content: "# README\n",
      },
    ],
    diagnostics: [
      {
        level: "info" as const,
        code: "skipped-large-file" as const,
        file: "src/big.ts",
        message: "Skipped src/big.ts because it exceeds 20480 bytes.",
      },
    ],
    totalBytes: 25,
  };
}

beforeEach(() => {
  logEntries.length = 0;
  knowledgeDocCalls.length = 0;
  mockedBuildRepoContextArtifacts.mockReset();
  mockedGenerateKnowledgeDoc.mockReset();
  mockedEnsureOutputDirs.mockReset();
  mockedWriteBridgerConfig.mockReset();
  mockedWriteJson.mockReset();
  mockedWriteMarkdown.mockReset();
  mockedUpsertGeneratedMarkdownBlock.mockReset();
  mockedBuildGraphSummary.mockReset();
  mockedBuildRepoGraph.mockReset();
  mockedReadGraphOrderedFiles.mockReset();
  mockedWriteRepoGraphArtifacts.mockReset();
  mockedResolveRepoRoot.mockReset();
  mockedLogger.info.mockClear();
  mockedLogger.warn.mockClear();
  mockedLogger.debug.mockClear();
  mockedLogger.error.mockClear();
  mockedGenerateKnowledgeDoc.mockImplementation(async (input) => {
    knowledgeDocCalls.push(input);
    return `generated:${input.spec.key}`;
  });
  process.exitCode = undefined;
});

describe("runInitCommand", () => {
  it("builds graph artifacts and uses graph-ordered files for doc generation", async () => {
    const repoContext = createRepoContext();
    const fileIndex = createFileIndex();
    const repoGraph = createRepoGraph();
    const graphSummary = createGraphSummary();
    const graphOrderedFileContext = createGraphOrderedFileContext();

    mockedResolveRepoRoot.mockReturnValue("/repo");
    mockedEnsureOutputDirs.mockResolvedValue(undefined);
    mockedWriteBridgerConfig.mockResolvedValue(undefined);
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
    mockedBuildRepoGraph.mockResolvedValue(repoGraph);
    mockedBuildGraphSummary.mockReturnValue(graphSummary);
    mockedWriteRepoGraphArtifacts.mockResolvedValue({
      repoGraphPath: "/repo/.bridger/artifacts/repo-graph.json",
      graphSummaryPath: "/repo/.bridger/artifacts/graph-summary.json",
    });
    mockedReadGraphOrderedFiles.mockResolvedValue(graphOrderedFileContext);
    mockedWriteJson.mockResolvedValue(undefined);
    mockedWriteMarkdown.mockResolvedValue(undefined);

    await runInitCommand({ repo: "." });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedEnsureOutputDirs).toHaveBeenCalledWith("/repo");
    expect(mockedBuildRepoContextArtifacts).toHaveBeenCalledWith("/repo");
    expect(mockedBuildRepoGraph).toHaveBeenCalledWith({
      repoRoot: "/repo",
      fileIndex,
    });
    expect(mockedBuildGraphSummary).toHaveBeenCalledWith(repoGraph);
    expect(mockedWriteBridgerConfig).toHaveBeenCalledWith(
      "/repo",
      expect.objectContaining({
        schemaVersion: 1,
        project: {
          name: "repo",
          mode: "existing",
        },
        detected: expect.objectContaining({
          packageManager: "pnpm",
          stack: expect.arrayContaining(["Next.js", "TypeScript", "Tailwind"]),
        }),
      }),
    );
    expect(mockedWriteRepoGraphArtifacts).toHaveBeenCalledWith({
      repoRoot: "/repo",
      graph: repoGraph,
      summary: graphSummary,
    });
    expect(mockedReadGraphOrderedFiles).toHaveBeenCalledWith({
      repoRoot: "/repo",
      graph: repoGraph,
      summary: graphSummary,
      mode: "architecture-first",
      maxFiles: 40,
      maxSingleFileBytes: 20 * 1024,
      maxTotalBytes: 120 * 1024,
    });
    expect(mockedWriteJson).toHaveBeenCalledTimes(2);
    expect(mockedWriteMarkdown).toHaveBeenCalledTimes(7);
    expect(mockedUpsertGeneratedMarkdownBlock).not.toHaveBeenCalled();
    const knowledgeDocFileCalls = knowledgeDocCalls.filter(
      (call) => call.spec?.key !== "agentRules",
    );
    expect(knowledgeDocFileCalls).toHaveLength(5);
    for (const call of knowledgeDocFileCalls) {
      expect(readImportantFilesFromGenerationCall(call)).toEqual([
        {
          path: "package.json",
          reason: "Project config file",
          content: '{"name":"repo"}\n',
        },
        {
          path: "README.md",
          reason: "Root documentation file",
          content: "# README\n",
        },
      ]);
    }
    expect(logEntries).toEqual([
      "debug:bridger init: starting for /repo",
      "debug:bridger init: ensuring output directories",
      "debug:bridger init: output directories ready",
      "debug:bridger init: building repo context",
      "debug:bridger init: repo context ready (2 indexed files, 1 important files)",
      "debug:bridger init: writing project config",
      "debug:bridger init: project config written",
      "debug:bridger init: building repo graph",
      "debug:bridger init: repo graph ready",
      "debug:bridger init: writing deterministic artifacts",
      "debug:bridger init: deterministic artifacts written",
      "debug:bridger init: reading graph-ordered file context",
      "debug:bridger init: graph-ordered file context ready (2 files)",
      "warn:Skipped 1 graph-ordered context files.",
      "debug:bridger init: generating documentation",
      "debug:bridger init: documentation generated",
      "debug:bridger init: writing generated files",
      "debug:bridger init: generated files written",
      expect.stringContaining("info:SUCCESS: bridger init complete"),
    ]);
    expect(logEntries.at(-1)).toContain(".bridger/artifacts/repo-graph.json");
    expect(logEntries.at(-1)).toContain(".bridger/artifacts/graph-summary.json");
    expect(logEntries.at(-1)).toContain(".bridger/config.json");
    expect(logEntries.at(-1)).toContain(".bridger/templates/ticket-template.md");
    expect(logEntries.at(-1)).not.toContain("ticket-template.md not generated");
    expect(mockedLogger.error).not.toHaveBeenCalled();
    expect(process.exitCode).toBeUndefined();
  });

  it("logs the optional AGENTS.md update when requested", async () => {
    const repoContext = createRepoContext();
    const fileIndex = createFileIndex();
    const repoGraph = createRepoGraph();
    const graphSummary = createGraphSummary();

    mockedResolveRepoRoot.mockReturnValue("/repo");
    mockedEnsureOutputDirs.mockResolvedValue(undefined);
    mockedWriteBridgerConfig.mockResolvedValue(undefined);
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
    mockedBuildRepoGraph.mockResolvedValue(repoGraph);
    mockedBuildGraphSummary.mockReturnValue(graphSummary);
    mockedWriteRepoGraphArtifacts.mockResolvedValue({
      repoGraphPath: "/repo/.bridger/artifacts/repo-graph.json",
      graphSummaryPath: "/repo/.bridger/artifacts/graph-summary.json",
    });
    mockedReadGraphOrderedFiles.mockResolvedValue({
      files: [
        {
          path: "README.md",
          reason: "Root documentation file",
          order: 1,
          content: "# README\n",
        },
      ],
      diagnostics: [],
      totalBytes: 9,
    });
    mockedWriteJson.mockResolvedValue(undefined);
    mockedWriteMarkdown.mockResolvedValue(undefined);
    mockedUpsertGeneratedMarkdownBlock.mockResolvedValue(undefined);

    await runInitCommand({ repo: ".", writeAgentsMd: true });

    expect(mockedUpsertGeneratedMarkdownBlock).toHaveBeenCalledTimes(1);
    expect(mockedUpsertGeneratedMarkdownBlock).toHaveBeenCalledWith(
      expect.objectContaining({
        filePath: "/repo/AGENTS.md",
        startMarker: "<!-- BRIDGER GENERATED START -->",
        endMarker: "<!-- BRIDGER GENERATED END -->",
      }),
    );
    expect(logEntries).toContain("debug:bridger init: updating AGENTS.md");
    expect(logEntries).toContain("debug:bridger init: AGENTS.md updated");
    expect(logEntries.at(-1)).toEqual(
      expect.stringContaining("info:SUCCESS: bridger init complete"),
    );
    expect(logEntries.at(-1)).toContain("Skipped:\n- none");
  });

  it("writes graph artifacts before failing on missing LLM config", async () => {
    const repoContext = createRepoContext();
    const fileIndex = createFileIndex();
    const repoGraph = createRepoGraph();
    const graphSummary = createGraphSummary();
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    try {
      mockedResolveRepoRoot.mockReturnValue("/repo");
      mockedEnsureOutputDirs.mockResolvedValue(undefined);
      mockedWriteBridgerConfig.mockResolvedValue(undefined);
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
      mockedBuildRepoGraph.mockResolvedValue(repoGraph);
      mockedBuildGraphSummary.mockReturnValue(graphSummary);
      mockedWriteRepoGraphArtifacts.mockResolvedValue({
        repoGraphPath: "/repo/.bridger/artifacts/repo-graph.json",
        graphSummaryPath: "/repo/.bridger/artifacts/graph-summary.json",
      });
      mockedReadGraphOrderedFiles.mockResolvedValue({
        files: [
          {
            path: "README.md",
            reason: "Root documentation file",
            order: 1,
            content: "# README\n",
          },
        ],
        diagnostics: [],
        totalBytes: 9,
      });
      mockedWriteJson.mockResolvedValue(undefined);
      mockedGenerateKnowledgeDoc.mockRejectedValue(
        new Error("Missing OpenAI API key"),
      );

      await runInitCommand({ repo: "." });

      expect(mockedWriteRepoGraphArtifacts).toHaveBeenCalledTimes(1);
      expect(mockedWriteBridgerConfig).toHaveBeenCalledTimes(1);
      expect(
        mockedWriteRepoGraphArtifacts.mock.invocationCallOrder[0],
      ).toBeLessThan(mockedGenerateKnowledgeDoc.mock.invocationCallOrder[0]);
      expect(mockedWriteMarkdown).not.toHaveBeenCalled();
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "bridger init failed: Missing OpenAI API key",
      );
      expect(process.exitCode).toBe(1);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
