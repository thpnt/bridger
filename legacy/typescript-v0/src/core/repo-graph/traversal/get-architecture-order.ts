import type {
  RepoGraph,
  RepoGraphNode,
  RepoGraphNodeTag,
} from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";
import { getDependencies } from "./get-dependencies";
import { getEntrypoints } from "./get-entrypoints";
import { getGraphFileRanks } from "./get-graph-file-ranks";
import { getRootFiles } from "./get-root-files";

export function getArchitectureOrder(graph: RepoGraph): string[] {
  const filePaths = getFilePaths(graph);
  const nodeByPath = getFileNodeByPath(graph);
  const ranks = getGraphFileRanks(graph);
  const rankByPath = new Map(ranks.map((rank) => [rank.path, rank]));
  const rootFiles = getRootFiles(graph);
  const entrypoints = getEntrypoints(graph);
  const entrypointDependencies = getDirectEntrypointDependencies(
    graph,
    entrypoints,
  );

  void rankByPath;

  return uniqueStableOrder([
    ...sortPaths(
      [
        ...rootFiles.docsFiles,
        ...rootFiles.configFiles,
        ...rootFiles.rootFiles,
      ].filter((path) => !isTestFile(path, nodeByPath.get(path))),
    ),
    ...sortPaths(
      entrypoints.filter((path) => !isTestFile(path, nodeByPath.get(path))),
    ),
    ...sortPaths(
      entrypointDependencies.filter(
        (path) => !isTestFile(path, nodeByPath.get(path)),
      ),
    ),
    ...sortPaths(
      filePaths.filter(
        (path) =>
          isFeatureOrDomainFile(path) &&
          !isTestFile(path, nodeByPath.get(path)),
      ),
    ),
    ...sortPaths(
      filePaths.filter((path) =>
        isComponentServiceOrLibFile(path, nodeByPath.get(path)) &&
        !isTestFile(path, nodeByPath.get(path)),
      ),
    ),
    ...sortPaths(
      filePaths.filter((path) =>
        isSharedUtilityFile(path, nodeByPath.get(path)) &&
        !isTestFile(path, nodeByPath.get(path)),
      ),
    ),
    ...sortPaths(
      filePaths.filter((path) => isTestFile(path, nodeByPath.get(path))),
    ),
    ...filePaths,
  ]);
}

function getDirectEntrypointDependencies(
  graph: RepoGraph,
  entrypoints: string[],
): string[] {
  const dependencies = new Set<string>();

  for (const entrypoint of entrypoints) {
    for (const dependency of getDependencies(graph, entrypoint, 1)) {
      dependencies.add(dependency);
    }
  }

  return sortPaths(dependencies);
}

function getFilePaths(graph: RepoGraph): string[] {
  return graph.nodes
    .filter((node) => node.kind === "file")
    .map((node) => normalizeRepoPath(node.path))
    .sort((a, b) => a.localeCompare(b));
}

function getFileNodeByPath(graph: RepoGraph): Map<string, RepoGraphNode> {
  const nodesByPath = new Map<string, RepoGraphNode>();

  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }

    nodesByPath.set(normalizeRepoPath(node.path), node);
  }

  return nodesByPath;
}

function sortPaths(paths: Iterable<string>): string[] {
  return [...paths].sort((a, b) => a.localeCompare(b));
}

function uniqueStableOrder(paths: Iterable<string>): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];

  for (const path of paths) {
    if (seen.has(path)) {
      continue;
    }

    seen.add(path);
    ordered.push(path);
  }

  return ordered;
}

function hasTag(node: RepoGraphNode | undefined, tag: RepoGraphNodeTag): boolean {
  return node?.tags.includes(tag) ?? false;
}

function isFeatureOrDomainFile(path: string): boolean {
  const lowerPath = path.toLowerCase();

  return (
    lowerPath.startsWith("features/") ||
    lowerPath.startsWith("feature/") ||
    lowerPath.startsWith("domain/") ||
    lowerPath.startsWith("domains/") ||
    lowerPath.startsWith("modules/") ||
    lowerPath.includes("/features/") ||
    lowerPath.includes("/feature/") ||
    lowerPath.includes("/domain/") ||
    lowerPath.includes("/domains/") ||
    lowerPath.includes("/modules/") ||
    lowerPath.includes("/use-cases/") ||
    lowerPath.includes("/usecases/") ||
    lowerPath.includes("/entities/") ||
    lowerPath.includes("/models/")
  );
}

function isComponentServiceOrLibFile(
  path: string,
  node?: RepoGraphNode,
): boolean {
  if (isSharedUtilityFile(path, node)) {
    return false;
  }

  const lowerPath = path.toLowerCase();

  return (
    hasTag(node, "component") ||
    hasTag(node, "service") ||
    lowerPath.startsWith("components/") ||
    lowerPath.startsWith("services/") ||
    lowerPath.startsWith("lib/") ||
    lowerPath.includes("/components/") ||
    lowerPath.includes("/services/") ||
    lowerPath.includes("/service/") ||
    lowerPath.includes("/lib/")
  );
}

function isSharedUtilityFile(path: string, node?: RepoGraphNode): boolean {
  const lowerPath = path.toLowerCase();

  return (
    hasTag(node, "utility") ||
    lowerPath.startsWith("utils/") ||
    lowerPath.startsWith("helpers/") ||
    lowerPath.includes("/utils/") ||
    lowerPath.includes("/util/") ||
    lowerPath.includes("/helpers/") ||
    lowerPath.endsWith("utils.ts") ||
    lowerPath.endsWith("utils.js") ||
    lowerPath.endsWith("util.ts") ||
    lowerPath.endsWith("util.js") ||
    lowerPath.endsWith("helpers.ts") ||
    lowerPath.endsWith("helpers.js")
  );
}

function isTestFile(path: string, node?: RepoGraphNode): boolean {
  const lowerPath = path.toLowerCase();
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;

  return (
    hasTag(node, "test") ||
    lowerPath.startsWith("tests/") ||
    lowerPath.startsWith("test/") ||
    lowerPath.includes("/__tests__/") ||
    lowerPath.includes(".test.") ||
    lowerPath.includes(".spec.") ||
    lowerPath.endsWith("_test.py") ||
    fileName.startsWith("test_")
  );
}
