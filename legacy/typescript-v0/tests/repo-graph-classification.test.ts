import { describe, expect, it } from "vitest";

import { getEntrypoints } from "../src/core/repo-graph/traversal/get-entrypoints";
import { getGraphFileRanks } from "../src/core/repo-graph/traversal/get-graph-file-ranks";
import { getRootFiles } from "../src/core/repo-graph/traversal/get-root-files";
import type {
  RepoGraph,
  RepoGraphEdge,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "../src/core/repo-graph/models/repo-graph";

function fileNode(
  path: string,
  tags: RepoGraphNodeTag[] = ["source"],
): RepoGraphNode {
  const extension = path.includes(".")
    ? path.slice(path.lastIndexOf("."))
    : null;

  return {
    id: path,
    path,
    kind: "file",
    extension,
    language: getLanguageFromPath(path),
    sizeBytes: 100,
    tags,
  };
}

function getLanguageFromPath(path: string): RepoGraphNode["language"] {
  if (path.endsWith(".ts") || path.endsWith(".tsx")) {
    return "typescript";
  }

  if (path.endsWith(".js") || path.endsWith(".jsx")) {
    return "javascript";
  }

  if (path.endsWith(".py")) {
    return "python";
  }

  if (path.endsWith(".md")) {
    return "markdown";
  }

  if (path.endsWith(".json")) {
    return "json";
  }

  return "unknown";
}

function importEdge(from: string, to: string): RepoGraphEdge {
  return {
    from,
    to,
    type: "imports",
    confidence: "high",
    source: "typescript-js-imports",
    importSpecifier: "./x",
  };
}

function containsEdge(from: string, to: string): RepoGraphEdge {
  return {
    from,
    to,
    type: "contains",
    confidence: "high",
    source: "filesystem",
  };
}

function createClassificationGraph(): RepoGraph {
  return {
    generatedAt: new Date().toISOString(),
    graphVersion: 1,
    repoRoot: "/tmp/example",
    nodes: [
      fileNode("README.md", ["root", "docs"]),
      fileNode("AGENTS.md", ["root", "docs"]),
      fileNode("package.json", ["root", "config"]),
      fileNode("tsconfig.json", ["root", "config"]),
      fileNode("src/index.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/app/page.tsx", ["source", "entrypoint-candidate", "route"]),
      fileNode("src/app/api/users/route.ts", [
        "source",
        "entrypoint-candidate",
        "route",
        "api-route",
      ]),
      fileNode("src/cli/index.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/main.ts", ["source", "entrypoint-candidate"]),
      fileNode("src/lib/utils.ts", ["source", "utility"]),
      fileNode("src/components/Button.tsx", ["source", "component"]),
      fileNode("src/service.ts", ["source", "service"]),
      fileNode("src/feature.ts", ["source"]),
      fileNode("main.py", ["root", "entrypoint-candidate"]),
      fileNode("app.py", ["root", "entrypoint-candidate"]),
      fileNode("src/main.py", ["source", "entrypoint-candidate"]),
      fileNode("src/worker.py", ["source"]),
      fileNode("tests/app.test.ts", ["source", "test"]),
      fileNode("docs/architecture.md", ["docs"]),
    ],
    edges: [
      containsEdge("src", "src/index.ts"),
      importEdge("src/index.ts", "src/service.ts"),
      importEdge("src/index.ts", "src/lib/utils.ts"),
      importEdge("src/service.ts", "src/lib/utils.ts"),
      importEdge("src/components/Button.tsx", "src/lib/utils.ts"),
      importEdge("src/feature.ts", "src/service.ts"),
    ],
    diagnostics: [],
    stats: {
      fileCount: 19,
      directoryCount: 0,
      containsEdgeCount: 1,
      importEdgeCount: 5,
      unresolvedImportCount: 0,
      supportedLanguageFileCount: 19,
    },
  };
}

describe("repo graph classification", () => {
  it("detects entrypoints", () => {
    const entrypoints = getEntrypoints(createClassificationGraph());

    expect(entrypoints).toEqual(sortPaths(entrypoints));
    expect(entrypoints).toEqual(
      expect.arrayContaining([
        "src/index.ts",
        "src/app/page.tsx",
        "src/app/api/users/route.ts",
        "src/cli/index.ts",
        "src/main.ts",
        "main.py",
        "app.py",
        "src/main.py",
      ]),
    );

    expect(entrypoints).not.toContain("src/service.ts");
    expect(entrypoints).not.toContain("src/lib/utils.ts");
    expect(entrypoints).not.toContain("src/components/Button.tsx");
    expect(entrypoints).not.toContain("tests/app.test.ts");
  });

  it("classifies root, config, and docs files", () => {
    const rootFiles = getRootFiles(createClassificationGraph());

    expect(rootFiles.rootFiles).toEqual(sortPaths(rootFiles.rootFiles));
    expect(rootFiles.configFiles).toEqual(sortPaths(rootFiles.configFiles));
    expect(rootFiles.docsFiles).toEqual(sortPaths(rootFiles.docsFiles));

    expect(rootFiles.rootFiles).toEqual(
      expect.arrayContaining([
        "AGENTS.md",
        "README.md",
        "app.py",
        "main.py",
        "package.json",
        "tsconfig.json",
      ]),
    );

    expect(rootFiles.configFiles).toEqual(
      expect.arrayContaining(["package.json", "tsconfig.json"]),
    );

    expect(rootFiles.docsFiles).toEqual(
      expect.arrayContaining(["README.md", "AGENTS.md", "docs/architecture.md"]),
    );
  });

  it("computes graph file ranks", () => {
    const ranks = getGraphFileRanks(createClassificationGraph());
    const byPath = new Map(ranks.map((rank) => [rank.path, rank]));

    expect(ranks.map((rank) => rank.path)).toEqual(
      sortPaths(ranks.map((rank) => rank.path)),
    );

    expect(byPath.get("src/index.ts")).toMatchObject({
      fanIn: 0,
      fanOut: 2,
      isLeaf: false,
      isIsolated: false,
      isEntrypoint: true,
    });

    expect(byPath.get("src/service.ts")).toMatchObject({
      fanIn: 2,
      fanOut: 1,
      isLeaf: false,
      isIsolated: false,
    });

    expect(byPath.get("src/lib/utils.ts")).toMatchObject({
      fanIn: 3,
      fanOut: 0,
      isLeaf: true,
      isIsolated: false,
    });

    expect(byPath.get("src/worker.py")).toMatchObject({
      fanIn: 0,
      fanOut: 0,
      isLeaf: true,
      isIsolated: true,
    });

    expect(byPath.get("package.json")).toMatchObject({
      isConfig: true,
      isDocs: false,
    });

    expect(byPath.get("README.md")).toMatchObject({
      isConfig: false,
      isDocs: true,
    });
  });

  it("ignores contains edges for fan-in and fan-out counts", () => {
    const ranks = getGraphFileRanks(createClassificationGraph());
    const byPath = new Map(ranks.map((rank) => [rank.path, rank]));

    expect(byPath.get("src/index.ts")).toMatchObject({
      fanIn: 0,
      fanOut: 2,
    });
  });
});

function sortPaths(paths: string[]): string[] {
  return [...paths].sort((left, right) => left.localeCompare(right));
}
