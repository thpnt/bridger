import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildGeneratedDocPaths, getTicketTemplateRelativePath, RepoRelativePathSchema } from "../../src/core/models/generated-paths";

const logEntries = vi.hoisted(() => [] as string[]);

vi.mock("../../src/core/context-builder/build-repo-context", () => ({
  buildRepoContextArtifacts: vi.fn(),
}));

vi.mock("../../src/core/doc-generator/generators/generate-knowledge-doc", () => ({
  generateKnowledgeDoc: vi.fn().mockImplementation(async ({ spec }) => `generated:${spec.key}`),
}));

vi.mock("../../src/core/output/ensure-output-dirs", () => ({
  ensureOutputDirs: vi.fn(),
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
import { ensureOutputDirs } from "../../src/core/output/ensure-output-dirs";
import { upsertGeneratedMarkdownBlock } from "../../src/core/output/upsert-generated-markdown-block";
import { writeJson } from "../../src/core/output/write-json";
import { writeMarkdown } from "../../src/core/output/write-markdown";
import { resolveRepoRoot } from "../../src/core/utils/paths";
import { logger } from "../../src/shared/logger";

const mockedBuildRepoContextArtifacts = vi.mocked(buildRepoContextArtifacts);
const mockedEnsureOutputDirs = vi.mocked(ensureOutputDirs);
const mockedWriteJson = vi.mocked(writeJson);
const mockedWriteMarkdown = vi.mocked(writeMarkdown);
const mockedUpsertGeneratedMarkdownBlock = vi.mocked(upsertGeneratedMarkdownBlock);
const mockedResolveRepoRoot = vi.mocked(resolveRepoRoot);
const mockedLogger = vi.mocked(logger);

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

beforeEach(() => {
  logEntries.length = 0;
  mockedBuildRepoContextArtifacts.mockReset();
  mockedEnsureOutputDirs.mockReset();
  mockedWriteJson.mockReset();
  mockedWriteMarkdown.mockReset();
  mockedUpsertGeneratedMarkdownBlock.mockReset();
  mockedResolveRepoRoot.mockReset();
  mockedLogger.info.mockClear();
  mockedLogger.debug.mockClear();
  mockedLogger.error.mockClear();
  process.exitCode = undefined;
});

describe("runInitCommand", () => {
  it("logs the major init steps and prints the success summary in dev mode", async () => {
    const repoContext = createRepoContext();
    const fileIndex = createFileIndex();

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
    mockedWriteJson.mockResolvedValue(undefined);
    mockedWriteMarkdown.mockResolvedValue(undefined);

    await runInitCommand({ repo: "." });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedEnsureOutputDirs).toHaveBeenCalledWith("/repo");
    expect(mockedBuildRepoContextArtifacts).toHaveBeenCalledWith("/repo");
    expect(mockedWriteJson).toHaveBeenCalledTimes(2);
    expect(mockedWriteMarkdown).toHaveBeenCalledTimes(7);
    expect(mockedUpsertGeneratedMarkdownBlock).not.toHaveBeenCalled();
    expect(logEntries).toEqual([
      "debug:bridger init: starting for /repo",
      "debug:bridger init: ensuring output directories",
      "debug:bridger init: output directories ready",
      "debug:bridger init: building repo context",
      "debug:bridger init: repo context ready (2 indexed files, 1 important files)",
      "debug:bridger init: writing context artifacts",
      "debug:bridger init: context artifacts written",
      "debug:bridger init: generating documentation",
      "debug:bridger init: documentation generated",
      "debug:bridger init: writing generated files",
      "debug:bridger init: generated files written",
      expect.stringContaining("info:SUCCESS: bridger init complete"),
    ]);
    expect(mockedLogger.error).not.toHaveBeenCalled();
    expect(process.exitCode).toBeUndefined();
  });

  it("logs the optional AGENTS.md update when requested", async () => {
    const repoContext = createRepoContext();
    const fileIndex = createFileIndex();

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
  });
});
