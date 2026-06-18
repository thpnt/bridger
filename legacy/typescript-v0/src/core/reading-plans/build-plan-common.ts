import type { CodebaseMap, CodebaseMapFile } from "../codebase-map/models/codebase-map";
import type {
  Confidence,
  FileIndex,
  FileIndexEntry,
  FileRole,
} from "../models/file-index";
import type { RepoContext } from "../models/repo-context";
import type { GraphSummary } from "../repo-graph/models/graph-summary";
import type { RepoGraph } from "../repo-graph/models/repo-graph";
import type {
  ReadingBatch,
  ReadingPlan,
  ReadingPlanEvidence,
  ReadingPlanFile,
  ReadingPlanFileRole,
  ReadingPlanKind,
  ReadingPlanWarning,
} from "./models/reading-plans";
import {
  READING_PLAN_BATCH_BUDGET,
  READING_PLAN_BUDGETS,
} from "./reading-plan-budgets";

export interface ReadingPlanBuildContext {
  repoRoot: string;
  fileIndex: FileIndex;
  repoContext: RepoContext;
  repoGraph: RepoGraph;
  graphSummary: GraphSummary;
  codebaseMap: CodebaseMap;
  fileIndexByPath: Map<string, FileIndexEntry>;
  codebaseFileByPath: Map<string, CodebaseMapFile>;
}

export interface CandidateRanking {
  roles?: FileRole[];
  signalKinds?: string[];
  preferredPaths?: Set<string>;
  preferEntrypoints?: boolean;
  preferCentral?: boolean;
}

export interface BatchDefinition {
  id: string;
  title: string;
  purpose: string;
  selectionRule: string;
  candidates: CodebaseMapFile[];
  roleInBatch: ReadingPlanFileRole | ((file: CodebaseMapFile) => ReadingPlanFileRole);
  reason: string | ((file: CodebaseMapFile) => string);
  evidence?: (file: CodebaseMapFile) => ReadingPlanEvidence[];
  ranking?: CandidateRanking;
}

export interface PlanDefinition {
  kind: ReadingPlanKind;
  targetMemoryFile: string;
  title: string;
  purpose: string;
  agentFocus: string;
  shouldAnswer: string[];
  shouldAvoid: string[];
  batches: BatchDefinition[];
}

export function createBuildContext(input: {
  repoRoot: string;
  fileIndex: FileIndex;
  repoContext: RepoContext;
  repoGraph: RepoGraph;
  graphSummary: GraphSummary;
  codebaseMap: CodebaseMap;
}): ReadingPlanBuildContext {
  return {
    ...input,
    fileIndexByPath: new Map(input.fileIndex.files.map((file) => [file.path, file])),
    codebaseFileByPath: new Map(input.codebaseMap.files.map((file) => [file.path, file])),
  };
}

export function getFileByPath(
  context: ReadingPlanBuildContext,
  filePath: string,
): CodebaseMapFile | undefined {
  return context.codebaseFileByPath.get(filePath);
}

export function getFilesByRole(
  context: ReadingPlanBuildContext,
  roles: FileRole[],
): CodebaseMapFile[] {
  return context.codebaseMap.files.filter((file) =>
    roles.some((role) => file.roles.includes(role)),
  );
}

export function getFilesBySignalKind(
  context: ReadingPlanBuildContext,
  signalKinds: string[],
): CodebaseMapFile[] {
  return context.codebaseMap.files.filter((file) =>
    file.signals.some((signal) => signalKinds.includes(signal.kind)),
  );
}

export function getEntrypointFiles(context: ReadingPlanBuildContext): CodebaseMapFile[] {
  const paths = new Set(context.codebaseMap.entrypoints.map((entrypoint) => entrypoint.path));
  for (const file of context.codebaseMap.files) {
    if (file.isEntrypoint) paths.add(file.path);
  }
  if (paths.size === 0) {
    for (const filePath of context.graphSummary.entrypoints) paths.add(filePath);
  }
  return filesForPaths(context, paths);
}

export function getCentralFiles(context: ReadingPlanBuildContext): CodebaseMapFile[] {
  const paths = new Set(
    context.codebaseMap.files.filter((file) => file.isCentral).map((file) => file.path),
  );
  for (const cluster of context.codebaseMap.clusters) {
    for (const file of cluster.centralFiles) paths.add(file.path);
  }
  return filesForPaths(context, paths);
}

export function getClusterFiles(
  context: ReadingPlanBuildContext,
  clusterIds: Set<string>,
): CodebaseMapFile[] {
  return context.codebaseMap.files.filter(
    (file) => file.clusterId && clusterIds.has(file.clusterId),
  );
}

export function getTestFiles(context: ReadingPlanBuildContext): CodebaseMapFile[] {
  return context.codebaseMap.files.filter((file) => file.isTest);
}

export function getFixtureFiles(context: ReadingPlanBuildContext): CodebaseMapFile[] {
  return context.codebaseMap.files.filter((file) => file.isFixture);
}

export function getConfigFiles(context: ReadingPlanBuildContext): CodebaseMapFile[] {
  return getFilesByRole(context, ["config", "project-config"]);
}

export function getFilesWithWarningsOrUnresolvedImports(
  context: ReadingPlanBuildContext,
): CodebaseMapFile[] {
  const paths = new Set(context.codebaseMap.unresolvedImports.byFile.map((item) => item.path));
  for (const warning of context.fileIndex.warnings ?? []) {
    if (warning.filePath) paths.add(warning.filePath);
  }
  return filesForPaths(context, paths);
}

export function rankCandidates(
  context: ReadingPlanBuildContext,
  candidates: CodebaseMapFile[],
  ranking: CandidateRanking = {},
): CodebaseMapFile[] {
  const unique = new Map(candidates.map((file) => [file.path, file]));
  return [...unique.values()].sort((left, right) => {
    const scoreDifference = scoreCandidate(context, right, ranking) - scoreCandidate(context, left, ranking);
    return scoreDifference || left.path.localeCompare(right.path);
  });
}

export function dedupePlanFilesWithinBatch(files: ReadingPlanFile[]): ReadingPlanFile[] {
  const seen = new Set<string>();
  return files.filter((file) => {
    if (seen.has(file.path)) return false;
    seen.add(file.path);
    return true;
  });
}

export function applyBatchBudget(files: ReadingPlanFile[]): {
  files: ReadingPlanFile[];
  estimatedBytes: number;
  truncated: boolean;
} {
  const selected: ReadingPlanFile[] = [];
  let estimatedBytes = 0;
  for (const file of files) {
    if (selected.length >= READING_PLAN_BATCH_BUDGET.maxFiles) break;
    if (estimatedBytes + file.estimatedBytes > READING_PLAN_BATCH_BUDGET.maxBytes) break;
    selected.push(file);
    estimatedBytes += file.estimatedBytes;
  }
  return { files: selected, estimatedBytes, truncated: selected.length < files.length };
}

export function estimateBytesForPath(
  context: ReadingPlanBuildContext,
  filePath: string,
): number {
  return context.fileIndexByPath.get(filePath)?.sizeBytes ??
    context.repoGraph.nodes.find((node) => node.kind === "file" && node.path === filePath)?.sizeBytes ??
    0;
}

export function buildBatch(
  context: ReadingPlanBuildContext,
  planKind: ReadingPlanKind,
  order: number,
  definition: BatchDefinition,
): { batch: ReadingBatch; warnings: ReadingPlanWarning[] } {
  const ranked = rankCandidates(context, definition.candidates, definition.ranking);
  const planFiles = dedupePlanFilesWithinBatch(
    ranked.map((file) => toPlanFile(context, file, definition)),
  );
  const budgeted = applyBatchBudget(planFiles);
  const warnings: ReadingPlanWarning[] = [];
  if (planFiles.length === 0) {
    warnings.push({
      code: "missing-batch-category",
      message: `No files matched the ${definition.title.toLowerCase()} selection rule.`,
      planKind,
      batchId: definition.id,
      severity: "info",
    });
  }
  if (budgeted.truncated) {
    warnings.push({
      code: "batch-truncated",
      message: `Batch ${definition.id} was truncated from ${planFiles.length} to ${budgeted.files.length} files.`,
      planKind,
      batchId: definition.id,
      severity: "warning",
    });
  }
  return {
    batch: {
      id: definition.id,
      title: definition.title,
      purpose: definition.purpose,
      order,
      selectionRule: definition.selectionRule,
      files: budgeted.files,
      budget: {
        maxFiles: READING_PLAN_BATCH_BUDGET.maxFiles,
        estimatedBytes: budgeted.estimatedBytes,
        truncated: budgeted.truncated,
      },
    },
    warnings,
  };
}

export function buildPlan(
  context: ReadingPlanBuildContext,
  definition: PlanDefinition,
): ReadingPlan {
  const built = definition.batches.map((batch, index) =>
    buildBatch(context, definition.kind, index + 1, batch),
  );
  const warnings = built.flatMap((item) => item.warnings);
  const limit = READING_PLAN_BUDGETS[definition.kind];
  let fileCount = 0;
  let estimatedBytes = 0;
  let planTruncated = false;
  const batches = built.map(({ batch }) => {
    const files: ReadingPlanFile[] = [];
    for (const file of batch.files) {
      if (fileCount >= limit.maxFiles || estimatedBytes + file.estimatedBytes > limit.maxBytes) {
        planTruncated = true;
        continue;
      }
      files.push(file);
      fileCount += 1;
      estimatedBytes += file.estimatedBytes;
    }
    const batchTruncated = batch.budget.truncated || files.length < batch.files.length;
    if (files.length < batch.files.length && !batch.budget.truncated) {
      warnings.push({
        code: "plan-batch-truncated",
        message: `Batch ${batch.id} lost ${batch.files.length - files.length} file references to the plan budget.`,
        planKind: definition.kind,
        batchId: batch.id,
        severity: "warning",
      });
    }
    return {
      ...batch,
      files,
      budget: {
        ...batch.budget,
        estimatedBytes: files.reduce((total, file) => total + file.estimatedBytes, 0),
        truncated: batchTruncated,
      },
    };
  });
  if (planTruncated) {
    warnings.push({
      code: "plan-truncated",
      message: `Plan ${definition.kind} was truncated to ${fileCount} file references.`,
      planKind: definition.kind,
      severity: "warning",
    });
  }
  return {
    kind: definition.kind,
    targetMemoryFile: definition.targetMemoryFile,
    title: definition.title,
    purpose: definition.purpose,
    inputStrategy: {
      agentFocus: definition.agentFocus,
      shouldAnswer: definition.shouldAnswer,
      shouldAvoid: definition.shouldAvoid,
    },
    batches,
    budget: {
      maxFiles: limit.maxFiles,
      estimatedBytes,
      truncated: planTruncated,
    },
    warnings: sortWarnings(warnings),
  };
}

export function combineFiles(...groups: CodebaseMapFile[][]): CodebaseMapFile[] {
  return groups.flat();
}

export function codebaseEvidence(detail: string): ReadingPlanEvidence[] {
  return [{ source: "codebase-map", detail }];
}

function filesForPaths(
  context: ReadingPlanBuildContext,
  paths: Set<string>,
): CodebaseMapFile[] {
  return [...paths]
    .sort((left, right) => left.localeCompare(right))
    .flatMap((filePath) => {
      const file = context.codebaseFileByPath.get(filePath);
      return file ? [file] : [];
    });
}

function scoreCandidate(
  context: ReadingPlanBuildContext,
  file: CodebaseMapFile,
  ranking: CandidateRanking,
): number {
  let score = 0;
  score += (ranking.roles ?? []).filter((role) => file.roles.includes(role)).length * 1_000;
  score += file.signals.filter((signal) => (ranking.signalKinds ?? []).includes(signal.kind)).length * 700;
  if (ranking.preferredPaths?.has(file.path)) score += 1_500;
  if (ranking.preferEntrypoints && file.isEntrypoint) score += 1_200;
  if (ranking.preferCentral && file.isCentral) score += 1_000;
  score += file.fanIn * 20 + file.fanOut * 10;
  score -= Math.floor(estimateBytesForPath(context, file.path) / 10_000);
  return score;
}

function toPlanFile(
  context: ReadingPlanBuildContext,
  file: CodebaseMapFile,
  definition: BatchDefinition,
): ReadingPlanFile {
  const indexFile = context.fileIndexByPath.get(file.path);
  const roleInBatch = typeof definition.roleInBatch === "function"
    ? definition.roleInBatch(file)
    : definition.roleInBatch;
  const reason = typeof definition.reason === "function"
    ? definition.reason(file)
    : definition.reason;
  const evidence = definition.evidence?.(file) ?? codebaseEvidence(
    `Selected from roles [${file.roles.join(", ") || "none"}], signals [${file.signals.map((signal) => signal.kind).join(", ") || "none"}], central=${file.isCentral}, entrypoint=${file.isEntrypoint}.`,
  );
  return {
    path: file.path,
    roleInBatch,
    reason,
    evidence: [...evidence].sort((left, right) =>
      left.source.localeCompare(right.source) || left.detail.localeCompare(right.detail),
    ),
    confidence: getConfidence(file, indexFile),
    estimatedBytes: estimateBytesForPath(context, file.path),
  };
}

function getConfidence(
  file: CodebaseMapFile,
  indexFile: FileIndexEntry | undefined,
): Confidence {
  if (file.signals.some((signal) => signal.confidence === "observed")) return "observed";
  return indexFile?.confidence ?? "inferred";
}

export function sortWarnings(warnings: ReadingPlanWarning[]): ReadingPlanWarning[] {
  return [...warnings].sort((left, right) =>
    (left.planKind ?? "").localeCompare(right.planKind ?? "") ||
    (left.batchId ?? "").localeCompare(right.batchId ?? "") ||
    (left.path ?? "").localeCompare(right.path ?? "") ||
    left.code.localeCompare(right.code) ||
    left.message.localeCompare(right.message),
  );
}
