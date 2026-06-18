import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { runInspectCommand } from "../src/cli/commands/inspect";
import { getBridgerDir, getReadingPlansPath } from "../src/core/project/bridger-paths";
import { logger } from "../src/shared/logger";

let tempDir = "";

afterEach(async () => {
  process.exitCode = undefined;
  vi.restoreAllMocks();
  if (tempDir) await fs.rm(tempDir, { recursive: true, force: true });
  tempDir = "";
});

describe("inspect --graph filesystem behavior", () => {
  it("builds a live cluster preview without writing Bridger artifacts", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-inspect-map-"));
    await fs.mkdir(path.join(tempDir, "src", "core", "foo"), {
      recursive: true,
    });
    await fs.writeFile(
      path.join(tempDir, "package.json"),
      JSON.stringify({ name: "fixture" }),
      "utf8",
    );
    await fs.writeFile(
      path.join(tempDir, "src", "core", "foo", "service.ts"),
      "export const value = 1;\n",
      "utf8",
    );
    const logSpy = vi.spyOn(logger, "info").mockImplementation(() => undefined);

    await runInspectCommand({ repo: tempDir, graph: true });

    expect(logSpy).toHaveBeenCalledOnce();
    expect(String(logSpy.mock.calls[0]?.[0])).toContain("Clusters");
    expect(String(logSpy.mock.calls[0]?.[0])).toContain("src-core-foo");
    await expect(fs.access(getBridgerDir(tempDir))).rejects.toThrow();
    await expect(fs.access(getReadingPlansPath(tempDir))).rejects.toThrow();
    expect(process.exitCode).toBeUndefined();
  });
});
