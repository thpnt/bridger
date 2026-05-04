import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { ensureOutputDirs } from "../../../src/core/output/ensure-output-dirs";
import { upsertGeneratedMarkdownBlock } from "../../../src/core/output/upsert-generated-markdown-block";
import { writeJson } from "../../../src/core/output/write-json";
import { writeMarkdown } from "../../../src/core/output/write-markdown";
import { readJsonFile } from "../../../src/core/utils/read-json";
import {
  getBridgerDir,
  getGeneratedDir,
  getTicketsDir,
} from "../../../src/core/utils/paths";

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

    expect((await fs.stat(getBridgerDir(tempDir))).isDirectory()).toBe(true);
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

  it("upserts a generated markdown block into a new file", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    const filePath = path.join(tempDir, "AGENTS.md");

    await upsertGeneratedMarkdownBlock({
      filePath,
      content: "## Rules\n\n- One\n",
      startMarker: "<!-- BRIDGER GENERATED START -->",
      endMarker: "<!-- BRIDGER GENERATED END -->",
    });

    const content = await fs.readFile(filePath, "utf8");
    expect(content).toBe(
      "<!-- BRIDGER GENERATED START -->\n\n## Rules\n\n- One\n\n<!-- BRIDGER GENERATED END -->\n",
    );
  });

  it("replaces an existing generated markdown block without touching surrounding content", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    const filePath = path.join(tempDir, "AGENTS.md");

    await fs.writeFile(
      filePath,
      [
        "# Existing",
        "",
        "<!-- BRIDGER GENERATED START -->",
        "",
        "Old content",
        "",
        "<!-- BRIDGER GENERATED END -->",
        "",
        "Tail",
      ].join("\n"),
      "utf8",
    );

    await upsertGeneratedMarkdownBlock({
      filePath,
      content: "## Rules\n\n- Two\n",
      startMarker: "<!-- BRIDGER GENERATED START -->",
      endMarker: "<!-- BRIDGER GENERATED END -->",
    });

    const content = await fs.readFile(filePath, "utf8");
    expect(content).toBe(
      [
        "# Existing",
        "",
        "<!-- BRIDGER GENERATED START -->",
        "",
        "## Rules",
        "",
        "- Two",
        "",
        "<!-- BRIDGER GENERATED END -->",
        "",
        "Tail",
      ].join("\n"),
    );
  });

  it("throws when only one generated block marker is present", async () => {
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bridger-utils-"));

    const filePath = path.join(tempDir, "AGENTS.md");

    await fs.writeFile(filePath, "<!-- BRIDGER GENERATED START -->\n", "utf8");

    await expect(
      upsertGeneratedMarkdownBlock({
        filePath,
        content: "## Rules\n",
        startMarker: "<!-- BRIDGER GENERATED START -->",
        endMarker: "<!-- BRIDGER GENERATED END -->",
      }),
    ).rejects.toThrow(
      `Malformed generated block in ${filePath}: expected both markers "<!-- BRIDGER GENERATED START -->" and "<!-- BRIDGER GENERATED END -->".`,
    );
  });
});
