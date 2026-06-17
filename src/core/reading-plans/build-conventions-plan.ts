import type { FileRole } from "../models/file-index";
import {
  buildPlan,
  combineFiles,
  getConfigFiles,
  getEntrypointFiles,
  getFilesByRole,
  getFilesBySignalKind,
  getTestFiles,
  rankCandidates,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";

const REPRESENTATIVE_ROLES: FileRole[] = [
  "service", "utility", "component", "command", "route", "api-route",
  "builder", "generator", "resolver", "extractor", "reader", "writer",
];

export function buildConventionsPlan(context: ReadingPlanBuildContext): ReadingPlan {
  const representatives = REPRESENTATIVE_ROLES.flatMap((role) =>
    rankCandidates(context, getFilesByRole(context, [role]), { roles: [role], preferCentral: true }).slice(0, 3),
  );
  return buildPlan(context, {
    kind: "conventions",
    targetMemoryFile: ".bridger/memory/conventions.md",
    title: "Conventions reading plan",
    purpose: "Explain implementation style, organization, naming, typing, and recurring code patterns.",
    agentFocus: "Compare representative implementations across only the roles already classified by deterministic artifacts.",
    shouldAnswer: ["How is code organized?", "How are contracts and workflows implemented?", "How are commands and tests written?"],
    shouldAvoid: ["Exhaustive implementation coverage.", "Conventions inferred only from filenames.", "Random files without role evidence."],
    batches: [
      {
        id: "representative-source-by-role",
        title: "Representative source files by role",
        purpose: "Show implementation style across existing role categories.",
        selectionRule: "Up to three ranked files for each implemented representative source role.",
        candidates: representatives,
        roleInBatch: (file) => file.roles.includes("service") ? "service" : file.roles.includes("utility") ? "utility" : "convention-example",
        reason: (file) => `Represents implemented role metadata: ${file.roles.filter((role) => REPRESENTATIVE_ROLES.includes(role)).join(", ")}.`,
        ranking: { roles: REPRESENTATIVE_ROLES, preferCentral: true },
      },
      {
        id: "models-schemas-types",
        title: "Models, schemas, and types",
        purpose: "Show data-contract and typing style.",
        selectionRule: "Implemented schema, model, and type roles plus schema and validation signals.",
        candidates: combineFiles(getFilesByRole(context, ["schema", "model", "type"]), getFilesBySignalKind(context, ["schema", "validation"])),
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : "contract",
        reason: "Demonstrates an existing data-contract pattern.",
        ranking: { roles: ["schema", "model", "type"], signalKinds: ["schema", "validation"] },
      },
      {
        id: "cli-and-workflow-style",
        title: "CLI and workflow style",
        purpose: "Show user-facing command implementation patterns.",
        selectionRule: "Command roles, CLI signals, and relevant deterministic entrypoints.",
        candidates: combineFiles(getFilesByRole(context, ["command"]), getFilesBySignalKind(context, ["cli"]), getEntrypointFiles(context)),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : "convention-example",
        reason: "Demonstrates an implemented command or workflow entry pattern.",
        ranking: { roles: ["command"], signalKinds: ["cli"], preferEntrypoints: true },
      },
      {
        id: "representative-tests",
        title: "Representative test style",
        purpose: "Show testing conventions and expectations.",
        selectionRule: "Files classified as tests by CodebaseMap.",
        candidates: getTestFiles(context),
        roleInBatch: "representative-test",
        reason: "Provides an existing example of test style.",
        ranking: { signalKinds: ["testing"] },
      },
      {
        id: "config-and-tooling",
        title: "Config and tooling conventions",
        purpose: "Show build, test, lint, and tooling configuration.",
        selectionRule: "Config and project-config roles, prioritizing testing signals.",
        candidates: combineFiles(
          getConfigFiles(context),
          getFilesBySignalKind(context, ["testing"]).filter((file) =>
            file.roles.includes("config") || file.roles.includes("project-config"),
          ),
        ),
        roleInBatch: "config",
        reason: "Defines an existing tooling or project convention.",
        ranking: { roles: ["project-config", "config"], signalKinds: ["testing"] },
      },
    ],
  });
}
