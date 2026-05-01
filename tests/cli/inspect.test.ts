import { beforeEach, describe, expect, it, vi } from "vitest";

import { RepoRelativePathSchema } from "../../src/core/models/generated-paths";

vi.mock("../../src/core/repo-scanner/detect-stack", () => ({
  detectStack: vi.fn(),
}));

vi.mock("../../src/core/repo-scanner/detect-commands", () => ({
  detectCommands: vi.fn(),
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

import { formatInspectSummary, runInspectCommand } from "../../src/cli/commands/inspect";
import { buildFileIndex } from "../../src/core/repo-scanner/build-file-index";
import { detectCommands } from "../../src/core/repo-scanner/detect-commands";
import { detectStack } from "../../src/core/repo-scanner/detect-stack";
import { resolveRepoRoot } from "../../src/core/utils/paths";
import { logger } from "../../src/shared/logger";

const mockedBuildFileIndex = vi.mocked(buildFileIndex);
const mockedDetectCommands = vi.mocked(detectCommands);
const mockedDetectStack = vi.mocked(detectStack);
const mockedResolveRepoRoot = vi.mocked(resolveRepoRoot);
const mockedLogger = vi.mocked(logger);

beforeEach(() => {
  mockedBuildFileIndex.mockReset();
  mockedDetectCommands.mockReset();
  mockedDetectStack.mockReset();
  mockedResolveRepoRoot.mockReset();
  mockedLogger.info.mockReset();
  mockedLogger.error.mockReset();
  process.exitCode = undefined;
});

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

describe("runInspectCommand", () => {
  it("uses deterministic scanner pieces and logs the summary without requiring the LLM", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    mockedDetectStack.mockResolvedValue({
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: ["Tailwind"],
      validation: ["Zod"],
      database: ["Supabase"],
      testFramework: ["Vitest"],
    });
    mockedDetectCommands.mockResolvedValue({
      install: "pnpm install",
      dev: "pnpm dev",
      test: "pnpm test",
    });
    mockedBuildFileIndex.mockResolvedValue({
      generatedAt: "2026-05-01T00:00:00.000Z",
      files: [
        {
          path: RepoRelativePathSchema.parse("README.md"),
          extension: ".md",
          sizeBytes: 100,
          tags: ["readme"],
        },
      ],
    });

    await runInspectCommand({ repo: "." });

    expect(mockedResolveRepoRoot).toHaveBeenCalledWith(".");
    expect(mockedDetectStack).toHaveBeenCalledWith("/repo");
    expect(mockedDetectCommands).toHaveBeenCalledWith("/repo", "pnpm");
    expect(mockedBuildFileIndex).toHaveBeenCalledWith("/repo");
    expect(mockedLogger.info).toHaveBeenCalledTimes(1);
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Repo: /repo");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Framework: Next.js");
    expect(mockedLogger.info.mock.calls[0]?.[0]).toContain("Indexed files: 1");
    expect(process.exitCode).toBeUndefined();
  });

  it("sets a non-zero exit code only on real errors", async () => {
    mockedResolveRepoRoot.mockReturnValue("/repo");
    mockedDetectStack.mockRejectedValue(new Error("bad repo"));

    await runInspectCommand({ repo: "." });

    expect(mockedLogger.error).toHaveBeenCalledWith(
      "Failed to inspect repository: bad repo",
    );
    expect(process.exitCode).toBe(1);
  });
});
