import type { CodebaseMapFile } from "../codebase-map/models/codebase-map";
import {
  buildPlan,
  combineFiles,
  getConfigFiles,
  getEntrypointFiles,
  getFilesByRole,
  getFilesWithWarningsOrUnresolvedImports,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";

export function buildRepoAnalysisPlan(context: ReadingPlanBuildContext): ReadingPlan {
  const clusterRepresentatives: CodebaseMapFile[] = [];
  for (const cluster of context.codebaseMap.clusters) {
    if (!new Set(["source", "mixed", "scripts"]).has(cluster.kind)) continue;
    const centralPath = cluster.centralFiles[0]?.path;
    const fallbackPath = [...cluster.files].sort()[0];
    const file = context.codebaseFileByPath.get(centralPath ?? fallbackPath ?? "");
    if (file && !file.isTest && !file.isFixture) clusterRepresentatives.push(file);
  }
  return buildPlan(context, {
    kind: "repo-analysis",
    targetMemoryFile: ".bridger/memory/repo-analysis.md",
    title: "Repository analysis reading plan",
    purpose: "Provide broad repository orientation from deterministic project metadata and codebase structure.",
    agentFocus: "Identify the project, stack, major areas, executable surfaces, and deterministic unknowns.",
    shouldAnswer: [
      "What kind of project is this and what stack does it use?",
      "What are the main directories, clusters, and executable surfaces?",
      "What is known and what remains uncertain?",
    ],
    shouldAvoid: ["Exhaustive source coverage.", "Deep implementation summaries.", "Claims unsupported by selected evidence."],
    batches: [
      {
        id: "project-metadata",
        title: "Project metadata and root orientation",
        purpose: "Read project-level files that explain repository identity, stack, scripts, and documentation.",
        selectionRule: "Project config, package metadata, and documentation roles from CodebaseMap.",
        candidates: combineFiles(getConfigFiles(context), getFilesByRole(context, ["docs"])),
        roleInBatch: (file) => file.roles.includes("docs") ? "orientation" : "config",
        reason: "Provides deterministic project-level orientation.",
        evidence: (file) => [
          {
            source: "codebase-map",
            detail: `Selected from implemented roles [${file.roles.join(", ")}].`,
          },
          ...(file.roles.includes("project-config")
            ? [{
                source: "repo-context" as const,
                detail: `Repository context reports package manager ${context.repoContext.stack.packageManager || "unknown"} and ${Object.values(context.repoContext.commands).filter(Boolean).length} detected commands.`,
              }]
            : []),
        ],
        ranking: { roles: ["project-config", "config", "docs"] },
      },
      {
        id: "main-entrypoints",
        title: "Main entrypoints",
        purpose: "Identify how the project is entered or executed.",
        selectionRule: "CodebaseMap entrypoints and isEntrypoint files; GraphSummary only when the map has none.",
        candidates: getEntrypointFiles(context),
        roleInBatch: "entrypoint",
        reason: "Marks an existing deterministic executable surface.",
        ranking: { preferEntrypoints: true },
      },
      {
        id: "major-clusters",
        title: "Major codebase areas",
        purpose: "Provide one representative central file for each major source cluster.",
        selectionRule: "Central file, or first stable file, from source, mixed, and scripts clusters.",
        candidates: clusterRepresentatives,
        roleInBatch: "cluster-central-file",
        reason: "Represents a major non-test codebase cluster.",
        ranking: { preferCentral: true },
      },
      {
        id: "warnings-and-unknowns",
        title: "Warnings and uncertain areas",
        purpose: "Surface files tied to deterministic warnings and unresolved imports.",
        selectionRule: "CodebaseMap unresolved-import paths and FileIndex path-specific warning files.",
        candidates: getFilesWithWarningsOrUnresolvedImports(context),
        roleInBatch: "risk-signal",
        reason: "Has an existing unresolved import or path-specific scan warning.",
      },
    ],
  });
}
