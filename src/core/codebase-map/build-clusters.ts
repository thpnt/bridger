import type { RepoGraph } from "../repo-graph/models/repo-graph";
import type { GraphSummary } from "../repo-graph/models/graph-summary";
import type {
  CodebaseCluster,
  CodebaseMapFile,
  ClusterCentralFile,
  ClusterRelation,
  EntrypointCandidate,
} from "./models/codebase-map";

const MAX_CENTRAL_FILES = 5;
const AREA_DIRECTORIES = new Set([
  "core",
  "domains",
  "features",
  "modules",
  "packages",
]);
const SOURCE_DIRECTORIES = new Set([
  "api",
  "app",
  "cli",
  "components",
  "db",
  "lib",
  "pages",
  "routes",
  "server",
  "shared",
]);

interface ClusterIdentity {
  id: string;
  rootPath: string;
  kind: CodebaseCluster["kind"];
}

interface RelationCounts {
  edges: Set<string>;
  sourceFiles: Set<string>;
}

export function getPathClusterIdentity(
  file: Pick<CodebaseMapFile, "path" | "roles">,
): ClusterIdentity {
  const segments = file.path.split("/");
  const roles = new Set(file.roles);

  if (roles.has("test")) {
    return identityForSpecialPath(file.path, "tests", "test");
  }

  if (roles.has("fixture")) {
    return identityForSpecialPath(file.path, "fixtures", "test");
  }

  if (roles.has("docs")) {
    return { id: "docs", rootPath: "docs", kind: "docs" };
  }

  if (
    roles.has("script") ||
    segments[0] === "scripts" ||
    segments[0] === "jobs"
  ) {
    const rootPath = segments[0] === "jobs" ? "jobs" : "scripts";
    return { id: slugPath(rootPath), rootPath, kind: "scripts" };
  }

  if (
    roles.has("config") ||
    roles.has("project-config") ||
    roles.has("lockfile")
  ) {
    return { id: "config", rootPath: "config/root", kind: "config" };
  }

  if (segments[0] === "src") {
    const second = segments[1];
    let depth = 2;

    if (second && AREA_DIRECTORIES.has(second) && segments[2]) {
      depth = 3;
    } else if (
      !second ||
      (!SOURCE_DIRECTORIES.has(second) && segments.length < 3)
    ) {
      depth = 1;
    }

    const rootPath = segments.slice(0, depth).join("/");
    return { id: slugPath(rootPath), rootPath, kind: "source" };
  }

  if (segments[0] && SOURCE_DIRECTORIES.has(segments[0])) {
    const rootPath = segments[0];
    return { id: slugPath(rootPath), rootPath, kind: "source" };
  }

  if (roles.has("source")) {
    return { id: "root", rootPath: "root", kind: "source" };
  }

  return { id: "unassigned", rootPath: "unassigned", kind: "unknown" };
}

export function buildClusters(input: {
  files: CodebaseMapFile[];
  entrypoints: EntrypointCandidate[];
  repoGraph: RepoGraph;
  graphSummary: GraphSummary;
}): CodebaseCluster[] {
  const identityByFile = new Map<string, ClusterIdentity>();
  const filesByCluster = new Map<string, CodebaseMapFile[]>();

  for (const file of input.files) {
    const identity = getPathClusterIdentity(file);
    identityByFile.set(file.path, identity);
    const clusterFiles = filesByCluster.get(identity.id) ?? [];
    clusterFiles.push(file);
    filesByCluster.set(identity.id, clusterFiles);
  }

  const dependencyCounts = buildRelationCounts(input.repoGraph, identityByFile);
  const consumerCounts = reverseRelationCounts(dependencyCounts);
  const entrypointPaths = new Set(
    input.entrypoints.map((entrypoint) => entrypoint.path),
  );
  const highFanInPaths = new Set(
    input.graphSummary.highFanInFiles.map((file) => file.path),
  );
  const highFanOutPaths = new Set(
    input.graphSummary.highFanOutFiles.map((file) => file.path),
  );
  const unresolvedByCluster = getUnresolvedCounts(
    input.repoGraph,
    identityByFile,
  );

  return [...filesByCluster.entries()]
    .map(([clusterId, files]) => {
      const sortedFiles = files.sort((left, right) =>
        left.path.localeCompare(right.path),
      );
      const identity = identityByFile.get(sortedFiles[0]!.path)!;
      const centralFiles = getCentralFiles({
        files: sortedFiles,
        entrypointPaths,
        highFanInPaths,
        highFanOutPaths,
      });
      const roles = countRoles(sortedFiles);
      const warnings: string[] = [];

      if (
        identity.kind === "source" &&
        !sortedFiles.some((file) => file.roles.includes("source"))
      ) {
        warnings.push("Source cluster contains no source-role files.");
      }

      const unresolvedCount = unresolvedByCluster.get(clusterId) ?? 0;
      if (unresolvedCount > 0) {
        warnings.push(
          `Cluster has ${unresolvedCount} unresolved import${unresolvedCount === 1 ? "" : "s"}.`,
        );
      }

      return {
        id: clusterId,
        title: titleForPath(identity.rootPath),
        rootPath: identity.rootPath,
        kind: identity.kind,
        files: sortedFiles.map((file) => file.path),
        roles,
        entrypoints: sortedFiles
          .filter((file) => entrypointPaths.has(file.path))
          .map((file) => file.path),
        centralFiles,
        tests: sortedFiles
          .filter((file) => file.isTest)
          .map((file) => file.path),
        fixtures: sortedFiles
          .filter((file) => file.isFixture)
          .map((file) => file.path),
        dependencies: formatRelations(dependencyCounts.get(clusterId)),
        consumers: formatRelations(consumerCounts.get(clusterId)),
        confidence: "inferred" as const,
        reasons: [`Grouped by path prefix ${identity.rootPath}.`],
        warnings,
      };
    })
    .sort((left, right) => left.id.localeCompare(right.id));
}

function identityForSpecialPath(
  filePath: string,
  fallbackRoot: string,
  kind: "test",
): ClusterIdentity {
  const segments = filePath.split("/");
  const markerIndex = segments.findIndex((segment) =>
    ["test", "tests", "__tests__", "fixture", "fixtures"].includes(
      segment.toLowerCase(),
    ),
  );
  const rootPath =
    markerIndex >= 0
      ? segments.slice(0, markerIndex + 1).join("/")
      : fallbackRoot;

  return { id: slugPath(rootPath), rootPath, kind };
}

function buildRelationCounts(
  graph: RepoGraph,
  identityByFile: Map<string, ClusterIdentity>,
): Map<string, Map<string, RelationCounts>> {
  const result = new Map<string, Map<string, RelationCounts>>();

  for (const edge of graph.edges) {
    if (edge.type !== "imports") {
      continue;
    }

    const from = identityByFile.get(edge.from);
    const to = identityByFile.get(edge.to);

    if (!from || !to || from.id === to.id) {
      continue;
    }

    const byTarget = result.get(from.id) ?? new Map<string, RelationCounts>();
    const counts = byTarget.get(to.id) ?? {
      edges: new Set<string>(),
      sourceFiles: new Set<string>(),
    };
    counts.edges.add(`${edge.from}\0${edge.to}`);
    counts.sourceFiles.add(edge.from);
    byTarget.set(to.id, counts);
    result.set(from.id, byTarget);
  }

  return result;
}

function reverseRelationCounts(
  relations: Map<string, Map<string, RelationCounts>>,
): Map<string, Map<string, RelationCounts>> {
  const reversed = new Map<string, Map<string, RelationCounts>>();

  for (const [fromCluster, targets] of relations) {
    for (const [toCluster, counts] of targets) {
      const consumers =
        reversed.get(toCluster) ?? new Map<string, RelationCounts>();
      consumers.set(fromCluster, counts);
      reversed.set(toCluster, consumers);
    }
  }

  return reversed;
}

function formatRelations(
  relations: Map<string, RelationCounts> | undefined,
): ClusterRelation[] {
  if (!relations) {
    return [];
  }

  return [...relations.entries()]
    .map(([clusterId, counts]) => ({
      clusterId,
      fileCount: counts.edges.size,
      reasons: [
        formatRelationReason(counts),
      ],
    }))
    .sort((left, right) => left.clusterId.localeCompare(right.clusterId));
}

function formatRelationReason(counts: RelationCounts): string {
  const fileLabel = counts.sourceFiles.size === 1 ? "file creates" : "files create";
  const importLabel = counts.edges.size === 1 ? "import" : "imports";

  return `${counts.sourceFiles.size} ${fileLabel} ${counts.edges.size} cross-cluster ${importLabel}.`;
}

function getCentralFiles(input: {
  files: CodebaseMapFile[];
  entrypointPaths: Set<string>;
  highFanInPaths: Set<string>;
  highFanOutPaths: Set<string>;
}): ClusterCentralFile[] {
  return input.files
    .filter((file) => file.isCentral || input.entrypointPaths.has(file.path))
    .sort(
      (left, right) =>
        right.fanIn - left.fanIn ||
        right.fanOut - left.fanOut ||
        left.path.localeCompare(right.path),
    )
    .slice(0, MAX_CENTRAL_FILES)
    .map((file) => {
      const reasons: string[] = [];

      if (file.fanIn > 0) reasons.push("High fan-in within repo.");
      if (file.fanOut > 0) reasons.push("High fan-out within repo.");
      if (input.highFanInPaths.has(file.path)) {
        reasons.push("Listed in graph summary high fan-in files.");
      }
      if (input.highFanOutPaths.has(file.path)) {
        reasons.push("Listed in graph summary high fan-out files.");
      }
      if (input.entrypointPaths.has(file.path)) {
        reasons.push("Entrypoint candidate.");
      }

      return { path: file.path, fanIn: file.fanIn, fanOut: file.fanOut, reasons };
    });
}

function countRoles(files: CodebaseMapFile[]): Record<string, number> {
  const counts = new Map<string, number>();

  for (const role of files.flatMap((file) => file.roles)) {
    counts.set(role, (counts.get(role) ?? 0) + 1);
  }

  return Object.fromEntries(
    [...counts.entries()].sort(([left], [right]) =>
      left.localeCompare(right),
    ),
  );
}

function getUnresolvedCounts(
  graph: RepoGraph,
  identityByFile: Map<string, ClusterIdentity>,
): Map<string, number> {
  const counts = new Map<string, number>();

  for (const diagnostic of graph.diagnostics) {
    if (diagnostic.code !== "unresolved-import" || !diagnostic.file) {
      continue;
    }
    const identity = identityByFile.get(diagnostic.file);
    if (identity) {
      counts.set(identity.id, (counts.get(identity.id) ?? 0) + 1);
    }
  }

  return counts;
}

function slugPath(value: string): string {
  return (
    value
      .toLowerCase()
      .replaceAll("/", "-")
      .replace(/[^a-z0-9-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "") || "unassigned"
  );
}

function titleForPath(value: string): string {
  return value === "root"
    ? "Root"
    : value
        .split("/")
        .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
        .join(" / ");
}
