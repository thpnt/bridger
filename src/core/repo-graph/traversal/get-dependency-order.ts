import type { RepoGraph, RepoGraphNode, RepoGraphNodeTag } from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";
import { getGraphFileRanks } from "./get-graph-file-ranks";

export function getDependencyOrder(graph: RepoGraph): string[] {
  const filePaths = getFilePaths(graph);
  const nodeByPath = getFileNodeByPath(graph);
  const ranks = getGraphFileRanks(graph);
  const rankByPath = new Map(ranks.map((rank) => [rank.path, rank]));

  return uniqueStableOrder([
    ...sortPaths(
      filePaths.filter((path) => {
        const node = nodeByPath.get(path);
        const rank = rankByPath.get(path);

        return Boolean(rank?.isLeaf) && !isTestFile(path, node);
      }),
    ),
    ...sortPaths(
      filePaths.filter((path) => {
        const node = nodeByPath.get(path);
        const rank = rankByPath.get(path);

        return (
          isSharedUtilityFile(path, node) &&
          (rank?.fanOut ?? 0) <= 1 &&
          !isTestFile(path, node)
        );
      }),
    ),
    ...sortPaths(
      filePaths.filter((path) => {
        const node = nodeByPath.get(path);

        return isServiceOrHelperFile(path, node) && !isTestFile(path, node);
      }),
    ),
    ...sortPaths(
      filePaths.filter((path) => {
        const node = nodeByPath.get(path);

        return isFeatureOrComponentFile(path, node) && !isTestFile(path, node);
      }),
    ),
    ...sortPaths(
      filePaths.filter((path) => {
        const node = nodeByPath.get(path);
        const rank = rankByPath.get(path);

        return Boolean(rank?.isEntrypoint) && !isTestFile(path, node);
      }),
    ),
    ...sortPaths(
      filePaths.filter((path) => isTestFile(path, nodeByPath.get(path))),
    ),
    ...filePaths,
  ]);
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

function isServiceOrHelperFile(path: string, node?: RepoGraphNode): boolean {
  const lowerPath = path.toLowerCase();
  const fileName = lowerPath.split("/").at(-1) ?? lowerPath;

  return (
    hasTag(node, "service") ||
    lowerPath.startsWith("services/") ||
    lowerPath.startsWith("service/") ||
    lowerPath.startsWith("helpers/") ||
    lowerPath.includes("/services/") ||
    lowerPath.includes("/service/") ||
    lowerPath.includes("/helpers/") ||
    fileName.endsWith("service.ts") ||
    fileName.endsWith("service.js") ||
    fileName.endsWith("service.py") ||
    fileName.endsWith("helper.ts") ||
    fileName.endsWith("helper.js") ||
    fileName.endsWith("helpers.ts") ||
    fileName.endsWith("helpers.js")
  );
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

function isFeatureOrComponentFile(path: string, node?: RepoGraphNode): boolean {
  const lowerPath = path.toLowerCase();

  return (
    isFeatureOrDomainFile(path) ||
    hasTag(node, "component") ||
    lowerPath.startsWith("components/") ||
    lowerPath.includes("/components/")
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
