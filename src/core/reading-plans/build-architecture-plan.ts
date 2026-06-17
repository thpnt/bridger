import {
  buildPlan,
  combineFiles,
  getCentralFiles,
  getEntrypointFiles,
  getFilesByRole,
  getFilesBySignalKind,
  getFilesWithWarningsOrUnresolvedImports,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";

export function buildArchitecturePlan(context: ReadingPlanBuildContext): ReadingPlan {
  const sourceCentral = getCentralFiles(context).filter((file) => !file.isTest && !file.isFixture);
  const relatedClusterPaths = new Set(
    context.codebaseMap.clusters
      .filter((cluster) => cluster.dependencies.length > 0 || cluster.consumers.length > 0)
      .flatMap((cluster) => cluster.centralFiles.map((file) => file.path)),
  );
  const crossCluster = context.codebaseMap.files.filter(
    (file) =>
      relatedClusterPaths.has(file.path) && !file.isTest && !file.isFixture,
  );
  const architectureContracts = combineFiles(
    getFilesByRole(context, ["schema", "type", "model"]),
    getFilesBySignalKind(context, ["schema", "validation", "database"]),
  ).filter((file) => !file.isTest && !file.isFixture);
  return buildPlan(context, {
    kind: "architecture",
    targetMemoryFile: ".bridger/memory/architecture.md",
    title: "Architecture reading plan",
    purpose: "Explain entrypoints, subsystems, dependency flow, central files, and contract boundaries.",
    agentFocus: "Trace execution starts, subsystem boundaries, existing cluster relations, and shared contracts.",
    shouldAnswer: ["Where does execution start?", "What are the main subsystems and dependency directions?", "Which files define central contracts or schemas?"],
    shouldAvoid: ["Test-heavy context.", "Affected-file traversal.", "Invented architectural layers."],
    batches: [
      {
        id: "entrypoints-and-command-surfaces",
        title: "Entrypoints and command surfaces",
        purpose: "Understand how execution starts.",
        selectionRule: "Entrypoints plus implemented command, route, API route, and CLI metadata.",
        candidates: combineFiles(getEntrypointFiles(context), getFilesByRole(context, ["command", "route", "api-route"]), getFilesBySignalKind(context, ["cli"])).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : file.roles.includes("route") || file.roles.includes("api-route") ? "route" : "supporting-context",
        reason: "Defines an existing entry or command surface.",
        ranking: { roles: ["command", "route", "api-route"], signalKinds: ["cli"], preferEntrypoints: true },
      },
      {
        id: "source-clusters",
        title: "Source clusters and central files",
        purpose: "Understand the main source subsystems and their central files.",
        selectionRule: "Non-test central files from source and mixed CodebaseMap clusters.",
        candidates: sourceCentral.filter((file) => {
          const cluster = context.codebaseMap.clusters.find((item) => item.id === file.clusterId);
          return cluster?.kind === "source" || cluster?.kind === "mixed";
        }),
        roleInBatch: "cluster-central-file",
        reason: "Is central to a source or mixed cluster.",
        ranking: { preferCentral: true },
      },
      {
        id: "cross-cluster-dependencies",
        title: "Cross-cluster dependency flow",
        purpose: "Read central files in clusters with existing dependency or consumer relations.",
        selectionRule: "Cluster central files where CodebaseMap dependencies or consumers are non-empty.",
        candidates: crossCluster,
        roleInBatch: "cluster-central-file",
        reason: "Belongs to a cluster with an existing cross-cluster relation.",
        ranking: { preferCentral: true },
      },
      {
        id: "contracts-and-schemas",
        title: "Contracts, schemas, and types",
        purpose: "Identify shared contracts and validation boundaries.",
        selectionRule: "Implemented schema, type, and model roles plus schema, validation, and database signals.",
        candidates: architectureContracts,
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : "contract",
        reason: "Carries an implemented contract role or contract-related signal.",
        ranking: { roles: ["schema", "type", "model"], signalKinds: ["schema", "validation", "database"], preferCentral: true },
      },
      {
        id: "architecture-warnings",
        title: "Architecture warnings and unresolved imports",
        purpose: "Highlight deterministic structural uncertainty.",
        selectionRule: "Unresolved-import paths and path-specific FileIndex warnings.",
        candidates: getFilesWithWarningsOrUnresolvedImports(context),
        roleInBatch: "risk-signal",
        reason: "Has a deterministic structural diagnostic.",
      },
    ],
  });
}
