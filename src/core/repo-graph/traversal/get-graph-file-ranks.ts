import type { RepoGraph } from "../models/repo-graph";
import { normalizeRepoPath } from "../utils/normalize-path";
import { buildAdjacencyMap } from "./build-adjacency-map";
import { getEntrypoints } from "./get-entrypoints";
import { getRootFiles } from "./get-root-files";

export type GraphFileRank = {
  path: string;
  fanIn: number;
  fanOut: number;
  isLeaf: boolean;
  isIsolated: boolean;
  isEntrypoint: boolean;
  isConfig: boolean;
  isDocs: boolean;
};

export function getGraphFileRanks(graph: RepoGraph): GraphFileRank[] {
  const adjacencyMap = buildAdjacencyMap(graph);
  const entrypoints = new Set(getEntrypoints(graph));
  const rootFiles = getRootFiles(graph);
  const configFiles = new Set(rootFiles.configFiles);
  const docsFiles = new Set(rootFiles.docsFiles);

  return graph.nodes
    .filter((node) => node.kind === "file")
    .map((node) => {
      const path = normalizeRepoPath(node.path);
      const fanOut = adjacencyMap.dependenciesByFile.get(path)?.length ?? 0;
      const fanIn = adjacencyMap.consumersByFile.get(path)?.length ?? 0;

      return {
        path,
        fanIn,
        fanOut,
        isLeaf: fanOut === 0,
        isIsolated: fanIn === 0 && fanOut === 0,
        isEntrypoint: entrypoints.has(path),
        isConfig: configFiles.has(path),
        isDocs: docsFiles.has(path),
      };
    })
    .sort((left, right) => left.path.localeCompare(right.path));
}
