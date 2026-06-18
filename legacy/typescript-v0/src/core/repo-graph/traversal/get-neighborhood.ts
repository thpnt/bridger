import type { RepoGraph } from "../models/repo-graph";
import { getConsumers } from "./get-consumers";
import { getDependencies } from "./get-dependencies";

export function getNeighborhood(
  graph: RepoGraph,
  filePath: string,
  depth = 1,
): string[] {
  const dependencies = getDependencies(graph, filePath, depth);
  const consumers = getConsumers(graph, filePath, depth);

  return [...new Set([...dependencies, ...consumers])].sort((a, b) =>
    a.localeCompare(b),
  );
}
