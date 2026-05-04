import type { RepoGraph } from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";

export type GraphAdjacencyMap = {
  dependenciesByFile: Map<string, string[]>;
  consumersByFile: Map<string, string[]>;
};

export function buildAdjacencyMap(graph: RepoGraph): GraphAdjacencyMap {
  const dependenciesByFile = new Map<string, Set<string>>();
  const consumersByFile = new Map<string, Set<string>>();

  for (const node of graph.nodes) {
    if (node.kind !== "file") {
      continue;
    }

    const path = normalizeRepoPath(node.path);

    dependenciesByFile.set(path, new Set());
    consumersByFile.set(path, new Set());
  }

  for (const edge of graph.edges) {
    if (edge.type !== "imports") {
      continue;
    }

    const fromPath = normalizeRepoPath(edge.from);
    const toPath = normalizeRepoPath(edge.to);

    if (!dependenciesByFile.has(fromPath)) {
      dependenciesByFile.set(fromPath, new Set());
    }

    if (!consumersByFile.has(toPath)) {
      consumersByFile.set(toPath, new Set());
    }

    dependenciesByFile.get(fromPath)?.add(toPath);
    consumersByFile.get(toPath)?.add(fromPath);
  }

  return {
    dependenciesByFile: sortMapValues(dependenciesByFile),
    consumersByFile: sortMapValues(consumersByFile),
  };
}

export function traverseAdjacency(input: {
  startPath: string;
  depth?: number;
  nextPathsByFile: Map<string, string[]>;
}): string[] {
  const startPath = normalizeRepoPath(input.startPath);
  const maxDepth = Math.max(0, Math.floor(input.depth ?? 1));

  if (maxDepth === 0) {
    return [];
  }

  const visited = new Set<string>([startPath]);
  const results = new Set<string>();
  const queue: Array<{ path: string; depth: number }> = [
    { path: startPath, depth: 0 },
  ];

  while (queue.length > 0) {
    const current = queue.shift();

    if (!current || current.depth >= maxDepth) {
      continue;
    }

    const nextPaths = input.nextPathsByFile.get(current.path) ?? [];

    for (const nextPath of nextPaths) {
      if (visited.has(nextPath)) {
        continue;
      }

      visited.add(nextPath);
      results.add(nextPath);

      queue.push({
        path: nextPath,
        depth: current.depth + 1,
      });
    }
  }

  return [...results].sort((a, b) => a.localeCompare(b));
}

function sortMapValues(input: Map<string, Set<string>>): Map<string, string[]> {
  const output = new Map<string, string[]>();

  for (const [path, values] of [...input.entries()].sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    output.set(path, [...values].sort((left, right) =>
      left.localeCompare(right),
    ));
  }

  return output;
}
