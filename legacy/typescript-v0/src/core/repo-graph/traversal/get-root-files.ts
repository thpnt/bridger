import type { RepoGraph, RepoGraphNode } from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";

export type GraphRootFiles = {
  rootFiles: string[];
  configFiles: string[];
  docsFiles: string[];
};

export function getRootFiles(graph: RepoGraph): GraphRootFiles {
  const rootFiles = new Set<string>();
  const configFiles = new Set<string>();
  const docsFiles = new Set<string>();

  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }

    const path = normalizeRepoPath(node.path);
    const lowerPath = path.toLowerCase();

    if (isRootFile(path)) {
      rootFiles.add(path);
    }

    if (isConfigFileNode(node, lowerPath)) {
      configFiles.add(path);
    }

    if (isDocsFileNode(node, lowerPath)) {
      docsFiles.add(path);
    }
  }

  return {
    rootFiles: sortPaths(rootFiles),
    configFiles: sortPaths(configFiles),
    docsFiles: sortPaths(docsFiles),
  };
}

function isRootFile(path: string): boolean {
  return !path.includes("/");
}

function isConfigFileNode(node: RepoGraphNode, lowerPath: string): boolean {
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;

  return (
    node.tags.includes("config") ||
    lowerPath.startsWith(".github/") ||
    fileName === "package.json" ||
    fileName === "tsconfig.json" ||
    fileName === "jsconfig.json" ||
    fileName === "components.json" ||
    fileName === "pyproject.toml" ||
    fileName === "ruff.toml" ||
    fileName === "mypy.ini" ||
    fileName === "pytest.ini" ||
    fileName === "dockerfile" ||
    fileName === "docker-compose.yml" ||
    fileName === ".env.example" ||
    fileName.startsWith("next.config.") ||
    fileName.startsWith("vite.config.") ||
    fileName.startsWith("vitest.config.") ||
    fileName.startsWith("jest.config.") ||
    fileName.startsWith("playwright.config.") ||
    fileName.startsWith("tailwind.config.") ||
    fileName.startsWith("postcss.config.") ||
    fileName.startsWith("eslint.config.") ||
    fileName.startsWith("prettier.config.")
  );
}

function isDocsFileNode(node: RepoGraphNode, lowerPath: string): boolean {
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;

  return (
    node.tags.includes("docs") ||
    lowerPath.startsWith("docs/") ||
    fileName === "readme.md" ||
    fileName === "agents.md" ||
    fileName === "claude.md" ||
    fileName.endsWith(".md")
  );
}

function sortPaths(paths: Iterable<string>): string[] {
  return [...paths].sort((left, right) => left.localeCompare(right));
}
