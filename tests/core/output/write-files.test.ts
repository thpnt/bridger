import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { ensureOutputDirs } from "../../../src/core/output/ensure-output-dirs";
import { writeJson } from "../../../src/core/output/write-json";
import { writeMarkdown } from "../../../src/core/output/write-markdown";
import { readJsonFile } from "../../../src/core/utils/read-json";
import { getAgentReadyDir, getGeneratedDir, getTicketsDir } from "../../../src/core/utils/paths";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("output helpers", () => {
  it("ensures the bridger output directories exist", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    await ensureOutputDirs(tempDir);

    expect((await fs.stat(getAgentReadyDir(tempDir))).isDirectory()).toBe(true);
    expect((await fs.stat(getGeneratedDir(tempDir))).isDirectory()).toBe(true);
    expect((await fs.stat(getTicketsDir(tempDir))).isDirectory()).toBe(true);
  });

  it("writes and reads stable pretty json", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    const filePath = path.join(tempDir, "nested", "data.json");

    await writeJson(filePath, { hello: "world" });

    const content = await fs.readFile(filePath, "utf8");
    expect(content).toBe('{\n  "hello": "world"\n}\n');
    await expect(readJsonFile<{ hello: string }>(filePath)).resolves.toEqual({ hello: "world" });
  });

  it("writes markdown with a trailing newline", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    const filePath = path.join(tempDir, "nested", "note.md");

    await writeMarkdown(filePath, "# Hello");

    const content = await fs.readFile(filePath, "utf8");
    expect(content).toBe("# Hello\n");
  });
});
