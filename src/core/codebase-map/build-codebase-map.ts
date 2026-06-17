import path from "node:path";

import type {
  FileIndex,
  FileIndexEntry,
  FileRole,
  FileSignal,
} from "../models/file-index";
import type { RepoContext } from "../models/repo-context";
import { getGraphFileRanks } from "../repo-graph/traversal/get-graph-file-ranks";
import type { RepoGraph } from "../repo-graph/models/repo-graph";
import type { GraphSummary } from "../repo-graph/models/graph-summary";
import { buildClusters, getPathClusterIdentity } from "./build-clusters";
import {
  CodebaseMapSchema,
  type CodebaseMap,
  type CodebaseMapFile,
  type CodebaseSignalSummary,
  type EntrypointCandidate,
  type UnresolvedImportSummary,
} from "./models/codebase-map";

export function buildCodebaseMap(input: {
  repoRoot: string;
  fileIndex: FileIndex;
  repoContext: RepoContext;
  repoGraph: RepoGraph;
  graphSummary: GraphSummary;
}): CodebaseMap {
  const entrypoints = buildEntrypoints(input.fileIndex, input.graphSummary);
  const entrypointPaths = new Set(
    entrypoints.map((entrypoint) => entrypoint.path),
  );
  const ranks = new Map(
    getGraphFileRanks(input.repoGraph).map((rank) => [rank.path, rank]),
  );
  const summaryCentralPaths = new Set([
    ...input.graphSummary.highFanInFiles.map((file) => file.path),
    ...input.graphSummary.highFanOutFiles.map((file) => file.path),
  ]);

  const files: CodebaseMapFile[] = input.fileIndex.files
    .map((file) => {
      const roles = [...(file.roles ?? [])].sort((left, right) =>
        left.localeCompare(right),
      );
      const rank = ranks.get(file.path);
      const record: CodebaseMapFile = {
        path: file.path,
        language: file.language ?? "unknown",
        roles,
        signals: sortSignals(file.signals ?? []),
        fanIn: rank?.fanIn ?? 0,
        fanOut: rank?.fanOut ?? 0,
        isCentral: summaryCentralPaths.has(file.path),
        isEntrypoint: entrypointPaths.has(file.path),
        isTest: roles.includes("test"),
        isFixture: roles.includes("fixture"),
      };

      return { ...record, clusterId: getPathClusterIdentity(record).id };
    })
    .sort((left, right) => left.path.localeCompare(right.path));

  const clusters = buildClusters({
    files,
    entrypoints,
    repoGraph: input.repoGraph,
    graphSummary: input.graphSummary,
  });
  const unresolvedImports = summarizeUnresolvedImports(input.repoGraph);
  const warnings = buildWarnings({
    files,
    entrypoints,
    unresolvedImportCount: unresolvedImports.count,
  });
  const detectedStack = getDetectedStack(input.repoContext);

  return CodebaseMapSchema.parse({
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    repo: {
      name: path.basename(input.repoRoot),
      packageManager: valueOrUndefined(input.repoContext.stack.packageManager),
      detectedStack,
    },
    stats: {
      fileCount: files.length,
      sourceFileCount: files.filter(
        (file) =>
          file.roles.includes("source") && !file.isTest && !file.isFixture,
      ).length,
      testFileCount: countFilesWithRole(files, "test"),
      fixtureFileCount: countFilesWithRole(files, "fixture"),
      docsFileCount: countFilesWithRole(files, "docs"),
      configFileCount: files.filter(
        (file) =>
          file.roles.includes("config") ||
          file.roles.includes("project-config"),
      ).length,
      clusterCount: clusters.length,
      entrypointCount: entrypoints.length,
      centralFileCount: files.filter((file) => file.isCentral).length,
      unresolvedImportCount: unresolvedImports.count,
    },
    entrypoints,
    clusters,
    files,
    signals: summarizeSignals(files),
    unresolvedImports,
    warnings,
  });
}

function buildEntrypoints(
  fileIndex: FileIndex,
  graphSummary: GraphSummary,
): EntrypointCandidate[] {
  const fileByPath = new Map<string, FileIndexEntry>(
    fileIndex.files.map((file) => [file.path, file]),
  );
  const candidatePaths = new Set<string>(graphSummary.entrypoints);

  for (const file of fileIndex.files) {
    if (
      file.roles?.includes("entrypoint-candidate") ||
      file.signals?.some((signal) => signal.kind === "entrypoint")
    ) {
      candidatePaths.add(file.path);
    }
  }

  return [...candidatePaths]
    .sort((left, right) => left.localeCompare(right))
    .map((candidatePath) =>
      toEntrypointCandidate(candidatePath, fileByPath.get(candidatePath)),
    );
}

function toEntrypointCandidate(
  candidatePath: string,
  file: FileIndexEntry | undefined,
): EntrypointCandidate {
  const lowerPath = candidatePath.toLowerCase();
  const signals = file?.signals ?? [];
  const packageBin = signals.find(
    (signal) =>
      signal.kind === "entrypoint" && signal.value === "package-bin",
  );
  const frameworkSignals = new Set(
    signals
      .filter((signal) => signal.kind === "framework")
      .map((signal) => signal.value),
  );
  const hasCliSignal = signals.some((signal) => signal.kind === "cli");
  let kind: EntrypointCandidate["kind"] = "unknown";
  let framework: string | undefined;

  if (packageBin) {
    kind = "package-bin";
  } else if (/\/page\.[jt]sx?$/.test(lowerPath)) {
    kind = "next-page";
    framework = "next";
  } else if (/\/route\.[jt]s$/.test(lowerPath)) {
    kind = "next-route";
    framework = "next";
  } else if (frameworkSignals.has("fastapi")) {
    kind = "fastapi-app";
    framework = "fastapi";
  } else if (frameworkSignals.has("django")) {
    kind = "django-app";
    framework = "django";
  } else if (lowerPath.includes("/cli/") || lowerPath.startsWith("cli/")) {
    kind = "cli-command";
  } else if (hasCliSignal) {
    kind = "node-cli";
  } else if (
    lowerPath.includes("/jobs/") ||
    lowerPath.startsWith("jobs/")
  ) {
    kind = "job";
  } else if (lowerPath.startsWith("scripts/")) {
    kind = "script";
  } else if (
    lowerPath.endsWith("manage.py") ||
    lowerPath.endsWith("asgi.py") ||
    lowerPath.endsWith("wsgi.py")
  ) {
    kind = "django-app";
    framework = "django";
  } else if (lowerPath.endsWith(".py")) {
    kind = "python-script";
  } else if (
    frameworkSignals.has("react") &&
    /\/(main|index)\.[jt]sx?$/.test(`/${lowerPath}`)
  ) {
    kind = "vite-react";
    framework = "react";
  }

  const entrypointSignals = signals.filter(
    (signal) => signal.kind === "entrypoint",
  );
  const reasons =
    entrypointSignals.length > 0
      ? [...new Set(entrypointSignals.map((signal) => signal.reason))].sort()
      : ["Listed in graph summary entrypoint candidates."];

  return {
    path: candidatePath,
    kind,
    ...(framework ? { framework } : {}),
    confidence: packageBin
      ? "observed"
      : (entrypointSignals[0]?.confidence ?? "inferred"),
    reasons,
  };
}

function summarizeSignals(files: CodebaseMapFile[]): CodebaseSignalSummary {
  const categories = {
    framework: new Map<string, number>(),
    schema: new Map<string, number>(),
    validation: new Map<string, number>(),
    cli: new Map<string, number>(),
    testing: new Map<string, number>(),
    database: new Map<string, number>(),
  };

  for (const signal of files.flatMap((file) => file.signals)) {
    if (!(signal.kind in categories)) continue;
    const counts = categories[signal.kind as keyof typeof categories];
    counts.set(signal.value, (counts.get(signal.value) ?? 0) + 1);
  }

  return {
    frameworks: sortedRecord(categories.framework),
    schemas: sortedRecord(categories.schema),
    validation: sortedRecord(categories.validation),
    cli: sortedRecord(categories.cli),
    testing: sortedRecord(categories.testing),
    database: sortedRecord(categories.database),
  };
}

function summarizeUnresolvedImports(graph: RepoGraph): UnresolvedImportSummary {
  const counts = new Map<string, number>();

  for (const diagnostic of graph.diagnostics) {
    if (diagnostic.code === "unresolved-import" && diagnostic.file) {
      counts.set(diagnostic.file, (counts.get(diagnostic.file) ?? 0) + 1);
    }
  }

  return {
    count: [...counts.values()].reduce((total, count) => total + count, 0),
    byFile: [...counts.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([filePath, count]) => ({ path: filePath, count })),
  };
}

function buildWarnings(input: {
  files: CodebaseMapFile[];
  entrypoints: EntrypointCandidate[];
  unresolvedImportCount: number;
}): string[] {
  const warnings: string[] = [];
  if (input.entrypoints.length === 0) warnings.push("No entrypoints detected.");
  if (!input.files.some((file) => file.roles.includes("source"))) {
    warnings.push("No source files detected.");
  }
  if (!input.files.some((file) => file.isTest)) {
    warnings.push("No tests detected.");
  }
  if (input.unresolvedImportCount > 0) {
    const importLabel = input.unresolvedImportCount === 1 ? "import" : "imports";
    warnings.push(
      `${input.unresolvedImportCount} unresolved ${importLabel} detected.`,
    );
  }

  const unassignedCount = input.files.filter(
    (file) => file.clusterId === "unassigned",
  ).length;
  if (input.files.length > 0 && unassignedCount / input.files.length > 0.25) {
    warnings.push(
      `${unassignedCount} files could not be assigned to a specific cluster.`,
    );
  }
  return warnings;
}

function getDetectedStack(repoContext: RepoContext): string[] {
  const stack = repoContext.stack;
  return [
    ...new Set(
      [
        stack.framework,
        stack.language,
        ...stack.styling,
        ...stack.validation,
        ...stack.database,
        ...stack.testFramework,
      ].filter((value) => value.length > 0 && value !== "unknown"),
    ),
  ].sort();
}

function countFilesWithRole(
  files: CodebaseMapFile[],
  role: FileRole,
): number {
  return files.filter((file) => file.roles.includes(role)).length;
}

function sortedRecord(counts: Map<string, number>): Record<string, number> {
  return Object.fromEntries(
    [...counts.entries()].sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
}

function sortSignals(signals: FileSignal[]): FileSignal[] {
  return [...signals].sort(
    (left, right) =>
      left.kind.localeCompare(right.kind) ||
      left.value.localeCompare(right.value) ||
      left.source.localeCompare(right.source),
  );
}

function valueOrUndefined(value: string): string | undefined {
  return value && value !== "unknown" ? value : undefined;
}
