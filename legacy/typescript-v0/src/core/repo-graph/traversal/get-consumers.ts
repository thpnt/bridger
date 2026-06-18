import type { RepoGraph } from "../models/repo-graph";
import { buildAdjacencyMap, traverseAdjacency } from "./build-adjacency-map";

export function getConsumers(
  graph: RepoGraph,
  filePath: string,
  depth = 1,
): string[] {
  const adjacencyMap = buildAdjacencyMap(graph);

  return traverseAdjacency({
    startPath: filePath,
    depth,
    nextPathsByFile: adjacencyMap.consumersByFile,
  });
}
