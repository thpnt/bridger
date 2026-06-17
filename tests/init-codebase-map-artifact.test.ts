import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/core/doc-generator/generators/generate-knowledge-doc", () => ({
  generateKnowledgeDoc: vi
    .fn()
    .mockRejectedValue(new Error("OPENAI_API_KEY is required")),
}));

import { runInitCommand } from "../src/cli/commands/init";
import { CodebaseMapSchema } from "../src/core/codebase-map/models/codebase-map";
import { ReadingPlansSchema } from "../src/core/reading-plans/models/reading-plans";
import {
  getCodebaseMapPath,
  getFileIndexPath,
  getGraphSummaryPath,
  getMemoryFilePath,
  getReadingPlansPath,
  getRepoContextPath,
  getRepoGraphPath,
} from "../src/core/project/bridger-paths";

let tempDir = "";

afterEach(async () => {
  process.exitCode = undefined;
  if (tempDir) await fs.rm(tempDir, { recursive: true, force: true });
  tempDir = "";
});

describe("init deterministic artifacts", () => {
  it("writes all deterministic artifacts before LLM failure without changing memory generation", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-init-map-"));
    await fs.mkdir(path.join(tempDir, "src"), { recursive: true });
    await fs.writeFile(
      path.join(tempDir, "package.json"),
      JSON.stringify({ name: "fixture", scripts: { test: "vitest" } }),
      "utf8",
    );
    await fs.writeFile(path.join(tempDir, "src", "index.ts"), "export {};\n", "utf8");
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    try {
      await runInitCommand({ repo: tempDir });

      const codebaseMap = JSON.parse(
        await fs.readFile(getCodebaseMapPath(tempDir), "utf8"),
      );
      const readingPlans = JSON.parse(
        await fs.readFile(getReadingPlansPath(tempDir), "utf8"),
      );
      expect(CodebaseMapSchema.safeParse(codebaseMap).success).toBe(true);
      expect(ReadingPlansSchema.safeParse(readingPlans).success).toBe(true);
      await expect(fs.access(getFileIndexPath(tempDir))).resolves.toBeUndefined();
      await expect(fs.access(getRepoContextPath(tempDir))).resolves.toBeUndefined();
      await expect(fs.access(getRepoGraphPath(tempDir))).resolves.toBeUndefined();
      await expect(fs.access(getGraphSummaryPath(tempDir))).resolves.toBeUndefined();
      await expect(
        fs.access(getMemoryFilePath(tempDir, "repo-analysis.md")),
      ).rejects.toThrow();
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        "bridger init failed: OPENAI_API_KEY is required",
      );
      expect(process.exitCode).toBe(1);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});
