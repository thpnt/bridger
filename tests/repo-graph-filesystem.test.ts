import { describe, expect, it } from "vitest";

import { buildFilesystemGraph } from "../src/core/repo-graph/build-filesystem-graph";
import { RepoRelativePathSchema } from "../src/core/models/generated-paths";
import {
  RepoGraphEdgeSchema,
  RepoGraphNodeSchema,
} from "../src/core/repo-graph/models/repo-graph";
import type { FileIndex } from "../src/core/models/file-index";

describe("buildFilesystemGraph", () => {
  it("creates file nodes, directory nodes, and contains edges", () => {
    const fileIndex: FileIndex = {
      generatedAt: new Date().toISOString(),
      files: [
        {
          path: RepoRelativePathSchema.parse("README.md"),
          extension: ".md",
          sizeBytes: 50,
          tags: [],
        },
        {
          path: RepoRelativePathSchema.parse("src/app/page.tsx"),
          extension: ".tsx",
          sizeBytes: 100,
          tags: [],
        },
        {
          path: RepoRelativePathSchema.parse("src/app/components/Button.tsx"),
          extension: ".tsx",
          sizeBytes: 80,
          tags: [],
        },
      ],
    };

    const result = buildFilesystemGraph({
      repoRoot: "/tmp/example",
      fileIndex,
    });

    expect(result.nodes.map((node) => node.path)).toEqual([
      "README.md",
      "src",
      "src/app",
      "src/app/components",
      "src/app/components/Button.tsx",
      "src/app/page.tsx",
    ]);

    expect(result.edges.map((edge) => `${edge.from} -> ${edge.to}`)).toEqual([
      "src -> src/app",
      "src/app -> src/app/components",
      "src/app -> src/app/page.tsx",
      "src/app/components -> src/app/components/Button.tsx",
    ]);
  });

  it("normalizes paths and deduplicates parent directories", () => {
    const fileIndex: FileIndex = {
      generatedAt: new Date().toISOString(),
      files: [
        {
          path: RepoRelativePathSchema.parse("src\\app\\page.tsx"),
          extension: "tsx",
          sizeBytes: 100,
          tags: [],
        },
        {
          path: RepoRelativePathSchema.parse("./src/app/layout.tsx"),
          extension: ".tsx",
          sizeBytes: 100,
          tags: [],
        },
      ],
    };

    const result = buildFilesystemGraph({
      repoRoot: "/tmp/example",
      fileIndex,
    });

    expect(result.nodes.map((node) => node.path)).toEqual([
      "src",
      "src/app",
      "src/app/layout.tsx",
      "src/app/page.tsx",
    ]);

    expect(result.nodes.filter((node) => node.path === "src")).toHaveLength(1);
    expect(result.nodes.filter((node) => node.path === "src/app")).toHaveLength(
      1,
    );
  });

  it("returns nodes and edges that validate against graph schemas", () => {
    const fileIndex: FileIndex = {
      generatedAt: new Date().toISOString(),
      files: [
        {
          path: RepoRelativePathSchema.parse("src/index.ts"),
          extension: ".ts",
          sizeBytes: 100,
          tags: [],
        },
      ],
    };

    const result = buildFilesystemGraph({
      repoRoot: "/tmp/example",
      fileIndex,
    });

    for (const node of result.nodes) {
      expect(RepoGraphNodeSchema.safeParse(node).success).toBe(true);
    }

    for (const edge of result.edges) {
      expect(RepoGraphEdgeSchema.safeParse(edge).success).toBe(true);
    }
  });

  it("returns stable output across runs", () => {
    const fileIndex: FileIndex = {
      generatedAt: new Date().toISOString(),
      files: [
        {
          path: RepoRelativePathSchema.parse("src/app/page.tsx"),
          extension: ".tsx",
          sizeBytes: 100,
          tags: [],
        },
        {
          path: RepoRelativePathSchema.parse("README.md"),
          extension: ".md",
          sizeBytes: 50,
          tags: [],
        },
      ],
    };

    const input = {
      repoRoot: "/tmp/example",
      fileIndex,
    };

    expect(buildFilesystemGraph(input)).toEqual(buildFilesystemGraph(input));
  });

  it("normalizes file extensions", () => {
    const fileIndex: FileIndex = {
      generatedAt: new Date().toISOString(),
      files: [
        {
          path: RepoRelativePathSchema.parse("src/app/page.tsx"),
          extension: "tsx",
          sizeBytes: 100,
          tags: [],
        },
      ],
    };

    const result = buildFilesystemGraph({
      repoRoot: "/tmp/example",
      fileIndex,
    });

    const fileNode = result.nodes.find(
      (node) => node.path === "src/app/page.tsx",
    );

    expect(fileNode?.extension).toBe(".tsx");
    expect(fileNode?.language).toBe("typescript");
  });
});
