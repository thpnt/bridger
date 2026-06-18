import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { runInitCommand } from "../src/cli/commands/init";
import { CodebaseMapSchema } from "../src/core/codebase-map/models/codebase-map";
import {
  getAgentsGeneratedExportPath,
  getCodebaseMapPath,
  getFileIndexPath,
  getGraphSummaryPath,
  getMemoryDir,
  getReadingPlansPath,
  getRepoContextPath,
  getRepoGraphPath,
} from "../src/core/project/bridger-paths";
import { ReadingPlansSchema } from "../src/core/reading-plans/models/reading-plans";

let tempDir = "";

afterEach(async () => {
  process.exitCode = undefined;
  if (tempDir) await fs.rm(tempDir, { recursive: true, force: true });
  tempDir = "";
});

describe("init deterministic artifacts", () => {
  it("writes all WS2 artifacts without generating final memory or AGENTS files", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-init-map-"));
    await fs.mkdir(path.join(tempDir, "src"), { recursive: true });
    await fs.writeFile(
      path.join(tempDir, "package.json"),
      JSON.stringify({ name: "fixture", scripts: { test: "vitest" } }),
      "utf8",
    );
    await fs.writeFile(
      path.join(tempDir, "src", "index.ts"),
      "export {};\n",
      "utf8",
    );

    await runInitCommand({ repo: tempDir });

    const codebaseMap = JSON.parse(
      await fs.readFile(getCodebaseMapPath(tempDir), "utf8"),
    );
    const readingPlans = JSON.parse(
      await fs.readFile(getReadingPlansPath(tempDir), "utf8"),
    );
    const memoryEntries = await fs.readdir(getMemoryDir(tempDir));

    expect(CodebaseMapSchema.safeParse(codebaseMap).success).toBe(true);
    expect(ReadingPlansSchema.safeParse(readingPlans).success).toBe(true);
    expect(readingPlans.plans.map((plan: { kind: string }) => plan.kind)).toEqual([
      "repo-analysis",
      "architecture",
      "business-logic",
      "conventions",
      "testing",
    ]);
    await expect(fs.access(getFileIndexPath(tempDir))).resolves.toBeUndefined();
    await expect(fs.access(getRepoContextPath(tempDir))).resolves.toBeUndefined();
    await expect(fs.access(getRepoGraphPath(tempDir))).resolves.toBeUndefined();
    await expect(fs.access(getGraphSummaryPath(tempDir))).resolves.toBeUndefined();
    expect(memoryEntries).toEqual([]);
    await expect(
      fs.access(getAgentsGeneratedExportPath(tempDir)),
    ).rejects.toThrow();
    await expect(fs.access(path.join(tempDir, "AGENTS.md"))).rejects.toThrow();
    expect(process.exitCode).toBeUndefined();
  });
});
