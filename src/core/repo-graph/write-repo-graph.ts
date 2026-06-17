import { writeJson } from "../output/write-json";
import { getGraphSummaryPath, getRepoGraphPath } from "../project/bridger-paths";
import {
  GraphSummarySchema,
  type GraphSummary,
} from "./models/graph-summary";
import { RepoGraphSchema, type RepoGraph } from "./models/repo-graph";

export type WriteRepoGraphArtifactsResult = {
  repoGraphPath: string;
  graphSummaryPath: string;
};

export async function writeRepoGraph(input: {
  repoRoot: string;
  graph: RepoGraph;
}): Promise<string> {
  const outputPath = getRepoGraphPath(input.repoRoot);

  await writeJson(outputPath, RepoGraphSchema.parse(input.graph));

  return outputPath;
}

export async function writeGraphSummary(input: {
  repoRoot: string;
  summary: GraphSummary;
}): Promise<string> {
  const outputPath = getGraphSummaryPath(input.repoRoot);

  await writeJson(outputPath, GraphSummarySchema.parse(input.summary));

  return outputPath;
}

export async function writeRepoGraphArtifacts(input: {
  repoRoot: string;
  graph: RepoGraph;
  summary: GraphSummary;
}): Promise<WriteRepoGraphArtifactsResult> {
  const repoGraphPath = await writeRepoGraph({
    repoRoot: input.repoRoot,
    graph: input.graph,
  });

  const graphSummaryPath = await writeGraphSummary({
    repoRoot: input.repoRoot,
    summary: input.summary,
  });

  return {
    repoGraphPath,
    graphSummaryPath,
  };
}
