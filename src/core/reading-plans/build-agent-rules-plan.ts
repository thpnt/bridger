import {
  buildPlan,
  combineFiles,
  getCentralFiles,
  getConfigFiles,
  getEntrypointFiles,
  getFilesByRole,
  getFilesBySignalKind,
  getFilesWithWarningsOrUnresolvedImports,
  getTestFiles,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";

export function buildAgentRulesPlan(context: ReadingPlanBuildContext): ReadingPlan {
  const conventionRoles = ["service", "utility", "builder", "reader", "writer", "schema", "type"] as const;
  return buildPlan(context, {
    kind: "agent-rules",
    targetMemoryFile: ".bridger/memory/agent-rules.md",
    title: "Agent rules reading plan",
    purpose: "Prepare evidence for future operational coding-agent rules without synthesizing those rules now.",
    agentFocus: "Identify orientation, risky files, representative conventions, verification evidence, and explicit unknowns.",
    shouldAnswer: ["What should agents understand before editing?", "Which files are central or risky?", "What testing and convention evidence exists?"],
    shouldAvoid: ["Replacing generated memory synthesis.", "Overclaiming rules.", "Exhaustive feature detail."],
    batches: [
      {
        id: "project-orientation",
        title: "Project orientation for coding agents",
        purpose: "Provide high-level files and entrypoints agents should know.",
        selectionRule: "Project metadata, deterministic entrypoints, and central source files.",
        candidates: combineFiles(getConfigFiles(context), getEntrypointFiles(context), getCentralFiles(context).filter((file) => !file.isTest && !file.isFixture)),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : file.roles.includes("config") || file.roles.includes("project-config") ? "config" : "cluster-central-file",
        reason: "Provides high-signal project orientation for coding work.",
        ranking: { roles: ["project-config", "config"], preferEntrypoints: true, preferCentral: true },
      },
      {
        id: "central-and-risky-files",
        title: "Central and risky files",
        purpose: "Identify high-centrality and warning-related files.",
        selectionRule: "CodebaseMap central files, cluster central files, unresolved imports, and path-specific warnings.",
        candidates: combineFiles(getCentralFiles(context), getFilesWithWarningsOrUnresolvedImports(context)),
        roleInBatch: (file) => context.codebaseMap.unresolvedImports.byFile.some((item) => item.path === file.path) ? "risk-signal" : "cluster-central-file",
        reason: "Is central or tied to an existing deterministic diagnostic.",
        ranking: { preferCentral: true },
      },
      {
        id: "convention-examples",
        title: "Convention examples",
        purpose: "Provide representative implementations coding agents can inspect.",
        selectionRule: "Implemented service, utility, builder, reader, writer, schema, and type roles.",
        candidates: getFilesByRole(context, [...conventionRoles]),
        roleInBatch: (file) => file.roles.includes("service") ? "service" : file.roles.includes("utility") ? "utility" : file.roles.includes("schema") ? "schema" : "convention-example",
        reason: "Carries an implemented role suitable as a convention example.",
        ranking: { roles: [...conventionRoles], preferCentral: true },
      },
      {
        id: "testing-expectations",
        title: "Testing expectations",
        purpose: "Provide evidence for future verification rules.",
        selectionRule: "Representative tests, test config/project config, and testing signals.",
        candidates: combineFiles(
          getTestFiles(context),
          getConfigFiles(context),
          getFilesBySignalKind(context, ["testing"]).filter((file) =>
            file.isTest || file.roles.includes("config") || file.roles.includes("project-config"),
          ),
        ),
        roleInBatch: (file) => file.isTest ? "representative-test" : "config",
        reason: "Provides file-backed evidence for testing expectations.",
        ranking: { roles: ["test", "project-config", "config"], signalKinds: ["testing"] },
      },
      {
        id: "diagnostics-and-unknowns",
        title: "Diagnostics and unknowns",
        purpose: "Surface caveats that future coding agents must not ignore.",
        selectionRule: "Unresolved-import paths and path-specific FileIndex warning paths.",
        candidates: getFilesWithWarningsOrUnresolvedImports(context),
        roleInBatch: "risk-signal",
        reason: "Has an existing deterministic caveat or diagnostic.",
      },
    ],
  });
}
