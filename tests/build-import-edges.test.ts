import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { buildFilesystemGraph } from "../src/core/repo-graph/build-filesystem-graph";
import { buildImportEdges } from "../src/core/repo-graph/build-import-edges";
import {
  RepoGraphDiagnosticSchema,
  RepoGraphEdgeSchema,
} from "../src/core/repo-graph/models/repo-graph";
import type { FileIndex } from "../src/core/models/file-index";
import { RepoRelativePathSchema } from "../src/core/models/path";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await fs.rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

describe("buildImportEdges", () => {
  it("adds ts/js import edges and unresolved diagnostics", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await writeRepoFile(
      repoRoot,
      "src/index.ts",
      [
        'import app from "./app";',
        'import users from "./features/users";',
        'import React from "react";',
        'import missing from "./missing";',
        "",
      ].join("\n"),
    );
    await writeRepoFile(repoRoot, "src/app.ts", "export default function app() {}\n");
    await writeRepoFile(
      repoRoot,
      "src/features/users/index.ts",
      "export default function users() {}\n",
    );

    const fileIndex = createFileIndex([
      { path: "src/index.ts", content: null, sizeBytes: 128 },
      { path: "src/app.ts", content: null, sizeBytes: 64 },
      { path: "src/features/users/index.ts", content: null, sizeBytes: 64 },
    ]);

    const result = await buildImportEdges({
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
    });

    expect(result.edges.map((edge) => `${edge.from} -> ${edge.to}`)).toEqual([
      "src/index.ts -> src/app.ts",
      "src/index.ts -> src/features/users/index.ts",
    ]);

    expect(result.diagnostics).toEqual([
      {
        level: "warning",
        code: "unresolved-import",
        file: "src/index.ts",
        message: 'Could not resolve local import "./missing" from src/index.ts.',
      },
    ]);

    for (const edge of result.edges) {
      expect(RepoGraphEdgeSchema.safeParse(edge).success).toBe(true);
    }

    for (const diagnostic of result.diagnostics) {
      expect(RepoGraphDiagnosticSchema.safeParse(diagnostic).success).toBe(true);
    }
  });

  it("adds python import edges and unresolved diagnostics", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await writeRepoFile(
      repoRoot,
      "main.py",
      ["import app.service", "import requests", ""].join("\n"),
    );
    await writeRepoFile(repoRoot, "app/service.py", "def run():\n    return None\n");
    await writeRepoFile(
      repoRoot,
      "app/routes/user.py",
      ["from ..domain import users", "from . import missing", ""].join("\n"),
    );
    await writeRepoFile(repoRoot, "app/domain/users.py", "def load():\n    return []\n");

    const fileIndex = createFileIndex([
      { path: "main.py", content: null, sizeBytes: 32 },
      { path: "app/service.py", content: null, sizeBytes: 64 },
      { path: "app/routes/user.py", content: null, sizeBytes: 64 },
      { path: "app/domain/users.py", content: null, sizeBytes: 64 },
    ]);

    const result = await buildImportEdges({
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
    });

    expect(result.edges.map((edge) => `${edge.from} -> ${edge.to}`)).toEqual([
      "app/routes/user.py -> app/domain/users.py",
      "main.py -> app/service.py",
    ]);

    expect(result.diagnostics).toEqual([
      {
        level: "warning",
        code: "unresolved-import",
        file: "app/routes/user.py",
        message: 'Could not resolve local import ".missing" from app/routes/user.py.',
      },
    ]);

    for (const edge of result.edges) {
      expect(RepoGraphEdgeSchema.safeParse(edge).success).toBe(true);
    }

    for (const diagnostic of result.diagnostics) {
      expect(RepoGraphDiagnosticSchema.safeParse(diagnostic).success).toBe(true);
    }
  });

  it("deduplicates duplicate import edges", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await writeRepoFile(
      repoRoot,
      "src/index.ts",
      [
        'import app from "./app";',
        'import { app2 } from "./app";',
        "",
      ].join("\n"),
    );
    await writeRepoFile(repoRoot, "src/app.ts", "export const app = true;\n");

    const fileIndex = createFileIndex([
      { path: "src/index.ts", content: null, sizeBytes: 64 },
      { path: "src/app.ts", content: null, sizeBytes: 64 },
    ]);

    const result = await buildImportEdges({
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
    });

    expect(result.edges).toEqual([
      {
        from: "src/index.ts",
        to: "src/app.ts",
        type: "imports",
        confidence: "high",
        source: "typescript-js-imports",
        importSpecifier: "./app",
      },
    ]);
  });

  it("skips files over maxFileBytes", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await writeRepoFile(
      repoRoot,
      "src/large.ts",
      'import app from "./app";\n',
    );
    await writeRepoFile(repoRoot, "src/app.ts", "export default function app() {}\n");

    const fileIndex = createFileIndex([
      { path: "src/large.ts", content: null, sizeBytes: 300_000 },
      { path: "src/app.ts", content: null, sizeBytes: 8 },
    ]);

    const result = await buildImportEdges({
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
      maxFileBytes: 10,
    });

    expect(result.edges).toEqual([]);
    expect(result.diagnostics).toEqual([
      {
        level: "info",
        code: "skipped-large-file",
        file: "src/large.ts",
        message:
          "Skipped import extraction for src/large.ts because it exceeds 10 bytes.",
      },
    ]);
  });

  it("emits read-error diagnostics", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    const fileIndex = createFileIndex([
      { path: "src/missing-file.ts", content: null, sizeBytes: 64 },
    ]);

    const result = await buildImportEdges({
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
    });

    expect(result.edges).toEqual([]);
    expect(result.diagnostics).toEqual([
      {
        level: "warning",
        code: "read-error",
        file: "src/missing-file.ts",
        message: "Could not read src/missing-file.ts for import extraction.",
      },
    ]);
  });

  it("returns stable sorted output", async () => {
    const repoRoot = await createTempRepo();
    tempDir = repoRoot;

    await writeRepoFile(
      repoRoot,
      "src/index.ts",
      [
        'import users from "./features/users";',
        'import app from "./app";',
        'import missing from "./missing";',
        "",
      ].join("\n"),
    );
    await writeRepoFile(repoRoot, "src/app.ts", "export default function app() {}\n");
    await writeRepoFile(
      repoRoot,
      "src/features/users/index.ts",
      "export default function users() {}\n",
    );

    const fileIndex = createFileIndex([
      { path: "src/features/users/index.ts", content: null, sizeBytes: 64 },
      { path: "src/index.ts", content: null, sizeBytes: 128 },
      { path: "src/app.ts", content: null, sizeBytes: 64 },
    ]);

    const input = {
      repoRoot,
      filesystemGraph: buildFilesystemGraph({
        repoRoot,
        fileIndex,
      }),
      fileIndex,
    };

    const firstResult = await buildImportEdges(input);
    const secondResult = await buildImportEdges(input);

    expect(firstResult).toEqual(secondResult);
  });
});

async function createTempRepo(): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), "bridger-graph-"));
}

async function writeRepoFile(
  repoRoot: string,
  filePath: string,
  content: string,
): Promise<void> {
  const absolutePath = path.join(repoRoot, filePath);
  await fs.mkdir(path.dirname(absolutePath), { recursive: true });
  await fs.writeFile(absolutePath, content, "utf8");
}

function createFileIndex(
  files: Array<{ path: string; content?: string | null; sizeBytes?: number }>,
): FileIndex {
  return {
    generatedAt: new Date().toISOString(),
    files: files.map((file) => {
      const entry: FileIndex["files"][number] = {
        path: RepoRelativePathSchema.parse(file.path),
        sizeBytes: file.sizeBytes ?? file.content?.length ?? 0,
        tags: [],
      };

      const extension = getExtension(file.path);

      if (extension !== null) {
        entry.extension = extension;
      }

      return entry;
    }),
  };
}

function getExtension(filePath: string): string | null {
  const fileName = filePath.split("/").at(-1) ?? filePath;
  const dotIndex = fileName.lastIndexOf(".");

  if (dotIndex <= 0 || dotIndex === fileName.length - 1) {
    return null;
  }

  return fileName.slice(dotIndex);
}
