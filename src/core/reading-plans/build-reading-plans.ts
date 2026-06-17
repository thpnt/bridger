import type { CodebaseMap } from "../codebase-map/models/codebase-map";
import type { FileIndex } from "../models/file-index";
import type { RepoContext } from "../models/repo-context";
import type { GraphSummary } from "../repo-graph/models/graph-summary";
import type { RepoGraph } from "../repo-graph/models/repo-graph";
import { buildAgentRulesPlan } from "./build-agent-rules-plan";
import { buildArchitecturePlan } from "./build-architecture-plan";
import { buildBusinessLogicPlan } from "./build-business-logic-plan";
import { buildConventionsPlan } from "./build-conventions-plan";
import { createBuildContext, sortWarnings } from "./build-plan-common";
import { buildRepoAnalysisPlan } from "./build-repo-analysis-plan";
import { buildTestingPlan } from "./build-testing-plan";
import {
  ReadingPlansSchema,
  type ReadingPlans,
  type ReadingPlanWarning,
} from "./models/reading-plans";

export function buildReadingPlans(input: {
  repoRoot: string;
  fileIndex: FileIndex;
  repoContext: RepoContext;
  repoGraph: RepoGraph;
  graphSummary: GraphSummary;
  codebaseMap: CodebaseMap;
}): ReadingPlans {
  const context = createBuildContext(input);
  const plans = [
    buildRepoAnalysisPlan(context),
    buildArchitecturePlan(context),
    buildBusinessLogicPlan(context),
    buildConventionsPlan(context),
    buildTestingPlan(context),
    buildAgentRulesPlan(context),
  ];
  const warnings: ReadingPlanWarning[] = [
    ...input.codebaseMap.warnings.map((message) => ({
      code: "codebase-map-warning",
      message,
      severity: "warning" as const,
    })),
    ...(input.fileIndex.warnings ?? []).map((warning) => ({
      code: warning.code,
      message: warning.message,
      ...(warning.filePath ? { path: warning.filePath } : {}),
      severity: warning.severity,
    })),
  ];
  const allFiles = plans.flatMap((plan) =>
    plan.batches.flatMap((batch) => batch.files),
  );
  const uniquePaths = new Set(allFiles.map((file) => file.path));

  return ReadingPlansSchema.parse({
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    sourceArtifacts: {
      ...(input.fileIndex.schemaVersion
        ? { fileIndexSchemaVersion: input.fileIndex.schemaVersion }
        : {}),
      repoGraphVersion: input.repoGraph.graphVersion,
      graphSummaryVersion: input.graphSummary.graphVersion,
      codebaseMapSchemaVersion: input.codebaseMap.schemaVersion,
    },
    plans,
    stats: {
      planCount: plans.length,
      batchCount: plans.reduce((total, plan) => total + plan.batches.length, 0),
      uniqueFileCount: uniquePaths.size,
      repeatedFileReferences: allFiles.length - uniquePaths.size,
      estimatedTotalBytes: allFiles.reduce(
        (total, file) => total + file.estimatedBytes,
        0,
      ),
    },
    warnings: sortWarnings(warnings),
  });
}
