import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  readReadingPlanFiles,
  type ReadReadingPlanFilesResult,
} from "../src/core/reading-plans/read-reading-plan-files";
import type { ReadingPlan } from "../src/core/reading-plans/models/reading-plans";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
  }

  tempDir = "";
});

describe("readReadingPlanFiles", () => {
  it("reads referenced files and preserves plan, batch, and file metadata", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    await writeRepoFile(tempDir, "src/index.ts", "export const value = 1;\n");
    await writeRepoFile(tempDir, "src/lib.ts", "export const helper = 2;\n");
    const plan = createPlan([
      batch("orientation", 1, [
        planFile("src/index.ts", "entrypoint", "Entrypoint evidence."),
      ]),
      batch("supporting-context", 2, [
        planFile("src/lib.ts", "utility", "Shared helper evidence."),
      ]),
    ]);

    const result = await readReadingPlanFiles({ repoRoot: tempDir, plan });

    expectPlanHeader(result);
    expect(result.batches.map((item) => item.id)).toEqual([
      "orientation",
      "supporting-context",
    ]);
    expect(result.batches[0]).toMatchObject({
      id: "orientation",
      title: "Orientation",
      purpose: "Read the selected files.",
      order: 1,
      selectionRule: "Keep batch ordering stable.",
      budget: { maxFiles: 4, estimatedBytes: 200, truncated: false },
    });
    expect(result.batches[0]?.files[0]).toMatchObject({
      path: "src/index.ts",
      roleInBatch: "entrypoint",
      reason: "Entrypoint evidence.",
      evidence: [{ source: "codebase-map", detail: "Selected by fixture." }],
      confidence: "observed",
      estimatedBytes: 24,
      content: "export const value = 1;\n",
      truncated: false,
    });
    expect(result.batches[0]?.files[0]?.bytesRead).toBeGreaterThan(0);
    expect(result.diagnostics).toEqual([]);
  });

  it("preserves repeated file appearances across batches without duplicate read diagnostics", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    await writeRepoFile(tempDir, "src/shared.ts", "export const shared = true;\n");
    const repeated = planFile(
      "src/shared.ts",
      "supporting-context",
      "Repeated on purpose.",
    );
    const plan = createPlan([
      batch("first", 1, [repeated]),
      batch("second", 2, [repeated]),
    ]);

    const result = await readReadingPlanFiles({ repoRoot: tempDir, plan });

    expect(result.batches[0]?.files[0]?.content).toBe(
      "export const shared = true;\n",
    );
    expect(result.batches[1]?.files[0]?.content).toBe(
      "export const shared = true;\n",
    );
    expect(result.diagnostics).toEqual([]);
  });

  it("returns diagnostics for missing files and preserves the file entry", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    const plan = createPlan([
      batch("missing", 1, [
        planFile("src/missing.ts", "supporting-context", "Missing file."),
      ]),
    ]);

    const result = await readReadingPlanFiles({ repoRoot: tempDir, plan });

    expect(result.batches[0]?.files[0]).toMatchObject({
      path: "src/missing.ts",
      content: "",
      bytesRead: 0,
      truncated: false,
    });
    expect(result.diagnostics).toEqual([
      {
        code: "file-not-found",
        message: "Reading plan file not found: src/missing.ts",
        path: "src/missing.ts",
        batchId: "missing",
        severity: "warning",
      },
    ]);
  });

  it("prevents reading files outside repoRoot", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    const plan = createPlan([
      batch("outside", 1, [
        planFile("../bridger-outside.txt", "risk-signal", "Outside repo."),
      ]),
    ]);

    const result = await readReadingPlanFiles({ repoRoot: tempDir, plan });

    expect(result.batches[0]?.files[0]?.content).toBe("");
    expect(result.diagnostics).toEqual([
      {
        code: "file-outside-repo",
        message:
          "Reading plan file resolves outside repo root: ../bridger-outside.txt",
        path: "../bridger-outside.txt",
        batchId: "outside",
        severity: "warning",
      },
    ]);
  });

  it("truncates file content deterministically when maxBytesPerFile is set", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    await writeRepoFile(tempDir, "src/large.ts", "abcdefghij");
    const plan = createPlan([
      batch("truncated", 1, [
        planFile("src/large.ts", "utility", "Large file."),
      ]),
    ]);

    const result = await readReadingPlanFiles({
      repoRoot: tempDir,
      plan,
      maxBytesPerFile: 5,
    });

    expect(result.batches[0]?.files[0]).toMatchObject({
      content: "abcde",
      bytesRead: 5,
      truncated: true,
    });
    expect(result.diagnostics).toEqual([
      {
        code: "file-truncated",
        message:
          "Reading plan file exceeded maxBytesPerFile and was truncated: src/large.ts",
        path: "src/large.ts",
        batchId: "truncated",
        severity: "warning",
      },
    ]);
  });

  it("does not modify reading-plans.json or other artifacts", async () => {
    tempDir = await mkdtemp(path.join(os.tmpdir(), "bridger-read-plan-"));
    const artifactPath = path.join(
      tempDir,
      ".bridger",
      "artifacts",
      "reading-plans.json",
    );
    const artifactContent = '{"schemaVersion":1}\n';
    await writeRepoFile(tempDir, "src/index.ts", "export const value = 1;\n");
    await mkdir(path.dirname(artifactPath), { recursive: true });
    await writeFile(artifactPath, artifactContent, "utf8");
    const plan = createPlan([
      batch("orientation", 1, [
        planFile("src/index.ts", "entrypoint", "Entrypoint evidence."),
      ]),
    ]);

    await readReadingPlanFiles({ repoRoot: tempDir, plan });

    await expect(readFile(artifactPath, "utf8")).resolves.toBe(artifactContent);
  });
});

function expectPlanHeader(result: ReadReadingPlanFilesResult): void {
  expect(result).toMatchObject({
    planKind: "architecture",
    targetMemoryFile: ".bridger/memory/architecture.md",
    title: "Architecture plan",
    purpose: "Read architecture evidence.",
    inputStrategy: {
      agentFocus: "Understand structure.",
      shouldAnswer: ["What is wired together?"],
      shouldAvoid: ["Speculation."],
    },
    budget: { maxFiles: 12, estimatedBytes: 400, truncated: false },
    warnings: [],
  });
}

function createPlan(batches: ReadingPlan["batches"]): ReadingPlan {
  return {
    kind: "architecture",
    targetMemoryFile: ".bridger/memory/architecture.md",
    title: "Architecture plan",
    purpose: "Read architecture evidence.",
    inputStrategy: {
      agentFocus: "Understand structure.",
      shouldAnswer: ["What is wired together?"],
      shouldAvoid: ["Speculation."],
    },
    batches,
    budget: { maxFiles: 12, estimatedBytes: 400, truncated: false },
    warnings: [],
  };
}

function batch(
  id: string,
  order: number,
  files: ReadingPlan["batches"][number]["files"],
): ReadingPlan["batches"][number] {
  return {
    id,
    title: toTitle(id),
    purpose: "Read the selected files.",
    order,
    selectionRule: "Keep batch ordering stable.",
    files,
    budget: { maxFiles: 4, estimatedBytes: 200, truncated: false },
  };
}

function planFile(
  filePath: string,
  roleInBatch: ReadingPlan["batches"][number]["files"][number]["roleInBatch"],
  reason: string,
): ReadingPlan["batches"][number]["files"][number] {
  return {
    path: filePath,
    roleInBatch,
    reason,
    evidence: [{ source: "codebase-map", detail: "Selected by fixture." }],
    confidence: "observed",
    estimatedBytes: 24,
  };
}

async function writeRepoFile(
  repoRoot: string,
  relativePath: string,
  content: string,
): Promise<void> {
  const filePath = path.join(repoRoot, relativePath);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content, "utf8");
}

function toTitle(id: string): string {
  return id
    .split("-")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
