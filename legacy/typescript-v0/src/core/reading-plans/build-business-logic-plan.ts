import {
  buildPlan,
  combineFiles,
  getCentralFiles,
  getEntrypointFiles,
  getFilesByRole,
  getFilesBySignalKind,
  getTestFiles,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";

export function buildBusinessLogicPlan(context: ReadingPlanBuildContext): ReadingPlan {
  const workflowRoles = ["service", "builder", "writer", "reader", "generator"] as const;
  return buildPlan(context, {
    kind: "business-logic",
    targetMemoryFile: ".bridger/memory/business-logic.md",
    title: "Business logic reading plan",
    purpose: "Extract visible product workflows, user-facing behavior, and durable artifact contracts.",
    agentFocus: "Understand commands, workflow implementation, artifacts, and behavior demonstrated by tests.",
    shouldAnswer: ["What workflows and commands exist?", "What artifacts are produced?", "How does repository evidence become context?"],
    shouldAvoid: ["Invented domain concepts.", "Generic low-signal utilities.", "Behavior not visible in selected files."],
    batches: [
      {
        id: "user-facing-workflow-entrypoints",
        title: "User-facing workflow entrypoints",
        purpose: "Read files that expose user-visible workflows.",
        selectionRule: "Entrypoints, command and route roles, and implemented CLI signals.",
        candidates: combineFiles(getEntrypointFiles(context), getFilesByRole(context, ["command", "route", "api-route"]), getFilesBySignalKind(context, ["cli"])),
        roleInBatch: (file) => file.isEntrypoint ? "entrypoint" : file.roles.includes("route") || file.roles.includes("api-route") ? "route" : "supporting-context",
        reason: "Exposes a deterministic user-facing workflow surface.",
        ranking: { roles: ["command", "route", "api-route"], signalKinds: ["cli"], preferEntrypoints: true },
      },
      {
        id: "workflow-implementation-files",
        title: "Workflow implementation files",
        purpose: "Read central implementation files for product workflows.",
        selectionRule: "Implemented service, builder, writer, reader, and generator roles, prioritized by centrality.",
        candidates: combineFiles(getFilesByRole(context, [...workflowRoles]), getCentralFiles(context).filter((file) => file.roles.some((role) => workflowRoles.includes(role as typeof workflowRoles[number])))).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.roles.includes("service") ? "service" : "supporting-context",
        reason: "Has an implemented workflow role in the current artifacts.",
        ranking: { roles: [...workflowRoles], preferCentral: true },
      },
      {
        id: "artifacts-and-contracts",
        title: "Artifacts, schemas, and contracts",
        purpose: "Understand durable objects and output contracts.",
        selectionRule: "Implemented schema, model, type, config, writer, or generator roles and contract signals.",
        candidates: combineFiles(getFilesByRole(context, ["schema", "model", "type", "config", "project-config", "writer", "generator"]), getFilesBySignalKind(context, ["schema", "validation", "database"])).filter((file) => !file.isTest && !file.isFixture),
        roleInBatch: (file) => file.roles.includes("schema") ? "schema" : file.roles.includes("model") ? "model" : file.roles.includes("config") || file.roles.includes("project-config") ? "config" : "contract",
        reason: "Defines or writes a durable artifact or contract using implemented metadata.",
        ranking: { roles: ["schema", "model", "type", "writer", "generator", "project-config", "config"], signalKinds: ["schema", "validation", "database"] },
      },
      {
        id: "behavior-tests",
        title: "Representative behavior tests",
        purpose: "Include tests that clarify product behavior.",
        selectionRule: "CodebaseMap isTest files ranked by centrality and graph degree.",
        candidates: getTestFiles(context),
        roleInBatch: "representative-test",
        reason: "Demonstrates behavior using an existing test classification.",
        ranking: { signalKinds: ["testing"], preferCentral: true },
      },
    ],
  });
}
