import { describe, expect, it } from "vitest";

import {
  RepoGraphDiagnosticSchema,
  RepoGraphEdgeSchema,
  RepoGraphNodeSchema,
  RepoGraphSchema,
} from "../src/core/repo-graph/models/repo-graph";
import { GraphSummarySchema } from "../src/core/repo-graph/models/graph-summary";

describe("repo graph models", () => {
  it("rejects invalid node kinds", () => {
    const result = RepoGraphNodeSchema.safeParse({
      id: "src/index.ts",
      path: "src/index.ts",
      kind: "module",
      extension: ".ts",
      language: "typescript",
      sizeBytes: 100,
      tags: ["source"],
    });

    expect(result.success).toBe(false);
  });

  it("rejects invalid edge types", () => {
    const result = RepoGraphEdgeSchema.safeParse({
      from: "src/index.ts",
      to: "src/app.ts",
      type: "depends-on",
      confidence: "high",
      source: "typescript-js-imports",
    });

    expect(result.success).toBe(false);
  });

  it("rejects invalid diagnostic codes", () => {
    const result = RepoGraphDiagnosticSchema.safeParse({
      level: "warning",
      code: "bad-import",
      file: "src/index.ts",
      message: "Invalid import.",
    });

    expect(result.success).toBe(false);
  });

  it("accepts read-error diagnostic codes", () => {
    const result = RepoGraphDiagnosticSchema.safeParse({
      level: "warning",
      code: "read-error",
      file: "src/index.ts",
      message: "Could not read src/index.ts for import extraction.",
    });

    expect(result.success).toBe(true);
  });

  it("accepts a valid minimal repo graph", () => {
    const result = RepoGraphSchema.safeParse({
      generatedAt: new Date().toISOString(),
      graphVersion: 1,
      repoRoot: "/tmp/example",
      nodes: [
        {
          id: "src/index.ts",
          path: "src/index.ts",
          kind: "file",
          extension: ".ts",
          language: "typescript",
          sizeBytes: 100,
          tags: ["source", "entrypoint-candidate"],
        },
      ],
      edges: [],
      diagnostics: [],
      stats: {
        fileCount: 1,
        directoryCount: 0,
        containsEdgeCount: 0,
        importEdgeCount: 0,
        unresolvedImportCount: 0,
        supportedLanguageFileCount: 1,
      },
    });

    expect(result.success).toBe(true);
  });

  it("accepts a valid minimal graph summary", () => {
    const result = GraphSummarySchema.safeParse({
      generatedAt: new Date().toISOString(),
      graphVersion: 1,
      entrypoints: ["src/index.ts"],
      rootFiles: [],
      configFiles: [],
      docsFiles: [],
      highFanInFiles: [
        {
          path: "src/utils.ts",
          count: 3,
          reason: "Imported by multiple files.",
        },
      ],
      highFanOutFiles: [],
      leafFiles: ["src/utils.ts"],
      isolatedFiles: [],
      architectureFirstOrder: ["src/index.ts", "src/utils.ts"],
      dependencyFirstOrder: ["src/utils.ts", "src/index.ts"],
      stats: {
        fileCount: 2,
        directoryCount: 0,
        containsEdgeCount: 0,
        importEdgeCount: 1,
        unresolvedImportCount: 0,
        supportedLanguageFileCount: 2,
      },
    });

    expect(result.success).toBe(true);
  });
});
