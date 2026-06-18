import type {
  CodebaseCluster,
  CodebaseMap,
  CodebaseMapFile,
} from "../codebase-map/models/codebase-map";
import type { Confidence } from "../models/file-index";
import type { RepoGraph } from "../repo-graph/models/repo-graph";
import { getEntrypoints } from "../repo-graph/traversal/get-entrypoints";
import { buildAdjacencyMap } from "../repo-graph/traversal/build-adjacency-map";
import { normalizeRepoPath } from "../repo-graph/utils/normalize-path";
import {
  AffectedTraversalResultSchema,
  type AffectedFileCandidate,
  type AffectedTraversalDiagnostic,
  type AffectedTraversalRelation,
  type AffectedTraversalResult,
} from "./models/affected-traversal";

const DEFAULT_MAX_DISTANCE = 3;
const DEFAULT_MAX_RELATED_FILES = 25;
const RELATION_ORDER: Record<AffectedTraversalRelation, number> = {
  dependency: 0,
  consumer: 1,
  test: 2,
  "entrypoint-consumer": 3,
  "same-cluster": 4,
};
const CONFIDENCE_ORDER: Record<Confidence, number> = {
  observed: 0,
  inferred: 1,
  ambiguous: 2,
};

export interface BuildAffectedTraversalOptions {
  seedFiles: string[];
  repoGraph: RepoGraph;
  codebaseMap: CodebaseMap;
  maxDistance?: number;
  maxRelatedFiles?: number;
}

interface CandidateState {
  path: string;
  relation: AffectedTraversalRelation;
  distance?: number;
  score: number;
  reasons: Set<string>;
  confidence: Confidence;
}

export function buildAffectedTraversal(
  options: BuildAffectedTraversalOptions,
): AffectedTraversalResult {
  const maxDistance = Math.max(
    1,
    Math.floor(options.maxDistance ?? DEFAULT_MAX_DISTANCE),
  );
  const maxRelatedFiles = Math.max(
    1,
    Math.floor(options.maxRelatedFiles ?? DEFAULT_MAX_RELATED_FILES),
  );
  const normalizedSeedFiles = dedupePaths(options.seedFiles);
  const diagnostics: AffectedTraversalDiagnostic[] = [];
  const candidatesByPath = new Map<string, CandidateState>();
  const seedFileSet = new Set(normalizedSeedFiles);
  const graphFileSet = new Set(
    options.repoGraph.nodes
      .filter((node) => node.kind === "file")
      .map((node) => normalizeRepoPath(node.path)),
  );
  const codebaseFileByPath = new Map(
    options.codebaseMap.files.map((file) => [normalizeRepoPath(file.path), file]),
  );
  const clusterById = new Map(
    options.codebaseMap.clusters.map((cluster) => [cluster.id, cluster]),
  );
  const adjacency = buildAdjacencyMap(options.repoGraph);
  const entrypointPaths = dedupePaths([
    ...getEntrypoints(options.repoGraph),
    ...options.codebaseMap.entrypoints.map((entrypoint) => entrypoint.path),
  ]);

  for (const seedFile of normalizedSeedFiles) {
    const seedInGraph = graphFileSet.has(seedFile);
    const seedCodebaseFile = codebaseFileByPath.get(seedFile);

    if (!seedInGraph) {
      diagnostics.push({
        code: "seed-file-not-found",
        message: `Seed file is not present in RepoGraph: ${seedFile}`,
        path: seedFile,
        severity: "warning",
      });
    }

    if (!seedCodebaseFile) {
      diagnostics.push({
        code: "seed-file-not-in-codebase-map",
        message: `Seed file is not present in CodebaseMap: ${seedFile}`,
        path: seedFile,
        severity: "warning",
      });
    }

    const dependencyDistances = seedInGraph
      ? getDistances(adjacency.dependenciesByFile, seedFile, maxDistance)
      : new Map<string, number>();
    const consumerDistances = seedInGraph
      ? getDistances(adjacency.consumersByFile, seedFile, maxDistance)
      : new Map<string, number>();

    for (const [relatedPath, distance] of dependencyDistances) {
      addCandidate({
        candidatesByPath,
        seedFileSet,
        path: relatedPath,
        relation: "dependency",
        distance,
        score: 90 - getDistancePenalty(distance),
        reason: "Seed file imports this file through RepoGraph import edges.",
        confidence: "observed",
      });
    }

    for (const [relatedPath, distance] of consumerDistances) {
      const consumerFile = codebaseFileByPath.get(relatedPath);

      if (
        consumerFile?.isTest ||
        entrypointPaths.includes(relatedPath)
      ) {
        continue;
      }

      addCandidate({
        candidatesByPath,
        seedFileSet,
        path: relatedPath,
        relation: "consumer",
        distance,
        score: 85 - getDistancePenalty(distance),
        reason: "This file imports the seed file through RepoGraph import edges.",
        confidence: "observed",
      });
    }

    addSameClusterCandidates({
      seedFile,
      seedCodebaseFile,
      clusterById,
      codebaseFileByPath,
      candidatesByPath,
      seedFileSet,
    });

    addRelatedTests({
      seedFile,
      seedCodebaseFile,
      consumerDistances,
      clusterById,
      codebaseFileByPath,
      candidatesByPath,
      seedFileSet,
    });

    for (const entrypointPath of entrypointPaths) {
      const distance = consumerDistances.get(entrypointPath);

      if (distance === undefined) {
        continue;
      }

      addCandidate({
        candidatesByPath,
        seedFileSet,
        path: entrypointPath,
        relation: "entrypoint-consumer",
        distance,
        score: 75 - getDistancePenalty(distance),
        reason:
          distance === 1
            ? "Entrypoint imports the seed file through a direct RepoGraph edge."
            : "Entrypoint reaches the seed file through RepoGraph dependency traversal.",
        confidence: distance === 1 ? "observed" : "inferred",
      });
    }
  }

  let relatedFiles = [...candidatesByPath.values()]
    .map(toAffectedFileCandidate)
    .sort(compareCandidates);

  if (relatedFiles.length === 0) {
    diagnostics.push({
      code: "no-related-files-found",
      message: "No related files were found for the provided seed files.",
      severity: "info",
    });
  }

  if (relatedFiles.length > maxRelatedFiles) {
    diagnostics.push({
      code: "max-related-files-reached",
      message: `Affected traversal was limited to ${maxRelatedFiles} related files.`,
      severity: "info",
    });
    relatedFiles = relatedFiles.slice(0, maxRelatedFiles);
  }

  return AffectedTraversalResultSchema.parse({
    seedFiles: normalizedSeedFiles,
    relatedFiles,
    diagnostics: sortDiagnostics(diagnostics),
  });
}

function addSameClusterCandidates(input: {
  seedFile: string;
  seedCodebaseFile: CodebaseMapFile | undefined;
  clusterById: Map<string, CodebaseCluster>;
  codebaseFileByPath: Map<string, CodebaseMapFile>;
  candidatesByPath: Map<string, CandidateState>;
  seedFileSet: Set<string>;
}): void {
  const clusterId = input.seedCodebaseFile?.clusterId;

  if (!clusterId) {
    return;
  }

  const cluster = input.clusterById.get(clusterId);
  if (!cluster) {
    return;
  }

  const centralFileSet = new Set(cluster.centralFiles.map((file) => file.path));

  for (const clusterPath of cluster.files) {
    const file = input.codebaseFileByPath.get(clusterPath);
    if (!file) {
      continue;
    }

    const sameClusterScore = getSameClusterScore(file, centralFileSet);
    addCandidate({
      candidatesByPath: input.candidatesByPath,
      seedFileSet: input.seedFileSet,
      path: clusterPath,
      relation: "same-cluster",
      score: sameClusterScore,
      reason: `Same CodebaseMap cluster as seed file (${cluster.id}).`,
      confidence: "inferred",
    });
  }
}

function addRelatedTests(input: {
  seedFile: string;
  seedCodebaseFile: CodebaseMapFile | undefined;
  consumerDistances: Map<string, number>;
  clusterById: Map<string, CodebaseCluster>;
  codebaseFileByPath: Map<string, CodebaseMapFile>;
  candidatesByPath: Map<string, CandidateState>;
  seedFileSet: Set<string>;
}): void {
  for (const [consumerPath, distance] of input.consumerDistances) {
    const consumerFile = input.codebaseFileByPath.get(consumerPath);
    if (!consumerFile?.isTest) {
      continue;
    }

    addCandidate({
      candidatesByPath: input.candidatesByPath,
      seedFileSet: input.seedFileSet,
      path: consumerPath,
      relation: "test",
      distance,
      score: 80 - getDistancePenalty(distance),
      reason: "Test imports the seed file through RepoGraph import edges.",
      confidence: "observed",
    });
  }

  const clusterId = input.seedCodebaseFile?.clusterId;
  if (!clusterId) {
    return;
  }

  const cluster = input.clusterById.get(clusterId);
  if (!cluster) {
    return;
  }

  for (const testPath of cluster.tests) {
    addCandidate({
      candidatesByPath: input.candidatesByPath,
      seedFileSet: input.seedFileSet,
      path: testPath,
      relation: "test",
      score: 80,
      reason: "Test is listed in the same CodebaseMap cluster tests.",
      confidence: "inferred",
    });
  }
}

function addCandidate(input: {
  candidatesByPath: Map<string, CandidateState>;
  seedFileSet: Set<string>;
  path: string;
  relation: AffectedTraversalRelation;
  distance?: number;
  score: number;
  reason: string;
  confidence: Confidence;
}): void {
  const normalizedPath = normalizeRepoPath(input.path);

  if (input.seedFileSet.has(normalizedPath)) {
    return;
  }

  const existing = input.candidatesByPath.get(normalizedPath);
  if (!existing) {
    input.candidatesByPath.set(normalizedPath, {
      path: normalizedPath,
      relation: input.relation,
      distance: input.distance,
      score: input.score,
      reasons: new Set([input.reason]),
      confidence: input.confidence,
    });
    return;
  }

  existing.reasons.add(input.reason);

  if (isStrongerCandidate(input, existing)) {
    existing.relation = input.relation;
    existing.distance = input.distance;
    existing.score = input.score;
  } else if (
    input.distance !== undefined &&
    (existing.distance === undefined || input.distance < existing.distance)
  ) {
    existing.distance = input.distance;
  }

  if (CONFIDENCE_ORDER[input.confidence] < CONFIDENCE_ORDER[existing.confidence]) {
    existing.confidence = input.confidence;
  }
}

function isStrongerCandidate(
  incoming: Pick<CandidateState, "relation" | "distance" | "score">,
  existing: Pick<CandidateState, "relation" | "distance" | "score">,
): boolean {
  return (
    incoming.score > existing.score ||
    (incoming.score === existing.score &&
      compareDistance(incoming.distance, existing.distance) < 0) ||
    (incoming.score === existing.score &&
      compareDistance(incoming.distance, existing.distance) === 0 &&
      RELATION_ORDER[incoming.relation] < RELATION_ORDER[existing.relation])
  );
}

function getDistances(
  adjacencyMap: Map<string, string[]>,
  startPath: string,
  maxDistance: number,
): Map<string, number> {
  const normalizedStartPath = normalizeRepoPath(startPath);
  const distances = new Map<string, number>();
  const visited = new Set<string>([normalizedStartPath]);
  const queue: Array<{ path: string; distance: number }> = [
    { path: normalizedStartPath, distance: 0 },
  ];

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || current.distance >= maxDistance) {
      continue;
    }

    const nextPaths = adjacencyMap.get(current.path) ?? [];
    for (const nextPath of nextPaths) {
      if (visited.has(nextPath)) {
        continue;
      }

      visited.add(nextPath);
      const distance = current.distance + 1;
      distances.set(nextPath, distance);
      queue.push({ path: nextPath, distance });
    }
  }

  return distances;
}

function getDistancePenalty(distance: number): number {
  return Math.max(0, distance - 1) * 5;
}

function getSameClusterScore(
  file: CodebaseMapFile,
  centralFileSet: Set<string>,
): number {
  if (centralFileSet.has(file.path) || file.isCentral) {
    return 65;
  }

  if (file.isEntrypoint) {
    return 55;
  }

  if (
    file.roles.some((role) =>
      ["route", "api-route", "service", "schema", "model"].includes(role),
    )
  ) {
    return 50;
  }

  return 45;
}

function toAffectedFileCandidate(state: CandidateState): AffectedFileCandidate {
  return {
    path: state.path,
    relation: state.relation,
    ...(state.distance !== undefined ? { distance: state.distance } : {}),
    score: state.score,
    reasons: [...state.reasons].sort((left, right) => left.localeCompare(right)),
    confidence: state.confidence,
  };
}

function compareCandidates(
  left: AffectedFileCandidate,
  right: AffectedFileCandidate,
): number {
  return (
    right.score - left.score ||
    compareDistance(left.distance, right.distance) ||
    RELATION_ORDER[left.relation] - RELATION_ORDER[right.relation] ||
    left.path.localeCompare(right.path)
  );
}

function compareDistance(left?: number, right?: number): number {
  const leftValue = left ?? Number.MAX_SAFE_INTEGER;
  const rightValue = right ?? Number.MAX_SAFE_INTEGER;

  return leftValue - rightValue;
}

function sortDiagnostics(
  diagnostics: AffectedTraversalDiagnostic[],
): AffectedTraversalDiagnostic[] {
  return [...diagnostics].sort(
    (left, right) =>
      left.code.localeCompare(right.code) ||
      (left.path ?? "").localeCompare(right.path ?? "") ||
      left.message.localeCompare(right.message),
  );
}

function dedupePaths(paths: string[]): string[] {
  return [...new Set(paths.map((filePath) => normalizeRepoPath(filePath)))]
    .sort((left, right) => left.localeCompare(right));
}
