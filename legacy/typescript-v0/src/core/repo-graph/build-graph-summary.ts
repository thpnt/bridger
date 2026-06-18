import {
  GraphSummarySchema,
  type GraphSummary,
  type GraphSummaryRankedFile,
} from "./models/graph-summary";
import type { RepoGraph } from "./models/repo-graph";
import { getArchitectureOrder } from "./traversal/get-architecture-order";
import { getDependencyOrder } from "./traversal/get-dependency-order";
import { getEntrypoints } from "./traversal/get-entrypoints";
import {
  getGraphFileRanks,
  type GraphFileRank,
} from "./traversal/get-graph-file-ranks";
import { getRootFiles } from "./traversal/get-root-files";

const MAX_RANKED_FILES = 10;

export function buildGraphSummary(graph: RepoGraph): GraphSummary {
  const ranks = getGraphFileRanks(graph);
  const rootFiles = getRootFiles(graph);

  const summary = {
    generatedAt: new Date().toISOString(),
    graphVersion: graph.graphVersion,
    entrypoints: sortPaths(getEntrypoints(graph)),
    rootFiles: sortPaths(rootFiles.rootFiles),
    configFiles: sortPaths(rootFiles.configFiles),
    docsFiles: sortPaths(rootFiles.docsFiles),
    highFanInFiles: getHighFanInFiles(ranks),
    highFanOutFiles: getHighFanOutFiles(ranks),
    leafFiles: sortPaths(ranks.filter((rank) => rank.isLeaf).map((rank) => rank.path)),
    isolatedFiles: sortPaths(
      ranks.filter((rank) => rank.isIsolated).map((rank) => rank.path),
    ),
    architectureFirstOrder: getArchitectureOrder(graph),
    dependencyFirstOrder: getDependencyOrder(graph),
    stats: graph.stats,
  };

  return GraphSummarySchema.parse(summary);
}

function getHighFanInFiles(ranks: GraphFileRank[]): GraphSummaryRankedFile[] {
  return ranks
    .filter((rank) => rank.fanIn > 0)
    .sort((left, right) =>
      compareCountDescThenPathAsc(left, right, left.fanIn, right.fanIn),
    )
    .slice(0, MAX_RANKED_FILES)
    .map((rank) => ({
      path: rank.path,
      count: rank.fanIn,
      reason: `Imported by ${rank.fanIn} file${rank.fanIn === 1 ? "" : "s"}.`,
    }));
}

function getHighFanOutFiles(ranks: GraphFileRank[]): GraphSummaryRankedFile[] {
  return ranks
    .filter((rank) => rank.fanOut > 0)
    .sort((left, right) =>
      compareCountDescThenPathAsc(left, right, left.fanOut, right.fanOut),
    )
    .slice(0, MAX_RANKED_FILES)
    .map((rank) => ({
      path: rank.path,
      count: rank.fanOut,
      reason: `Imports ${rank.fanOut} file${rank.fanOut === 1 ? "" : "s"}.`,
    }));
}

function compareCountDescThenPathAsc(
  left: { path: string },
  right: { path: string },
  leftCount: number,
  rightCount: number,
): number {
  return rightCount - leftCount || left.path.localeCompare(right.path);
}

function sortPaths(paths: Iterable<string>): string[] {
  return [...paths].sort((left, right) => left.localeCompare(right));
}
