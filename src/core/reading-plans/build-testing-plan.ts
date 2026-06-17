import {
  buildPlan,
  combineFiles,
  getConfigFiles,
  getFilesBySignalKind,
  getFilesWithWarningsOrUnresolvedImports,
  getFixtureFiles,
  getTestFiles,
  estimateBytesForPath,
  rankCandidates,
  sortWarnings,
  type ReadingPlanBuildContext,
} from "./build-plan-common";
import type { ReadingPlan } from "./models/reading-plans";
import { READING_PLAN_BATCH_BUDGET } from "./reading-plan-budgets";

export function buildTestingPlan(context: ReadingPlanBuildContext): ReadingPlan {
  const tests = getTestFiles(context);
  const rankedTests = rankCandidates(context, tests, {
    signalKinds: ["testing"],
    preferCentral: true,
  });
  const selectedTestPaths = new Set<string>();
  let selectedTestBytes = 0;
  for (const test of rankedTests) {
    const estimatedBytes = estimateBytesForPath(context, test.path);
    if (selectedTestPaths.size >= READING_PLAN_BATCH_BUDGET.maxFiles) break;
    if (selectedTestBytes + estimatedBytes > READING_PLAN_BATCH_BUDGET.maxBytes) break;
    selectedTestPaths.add(test.path);
    selectedTestBytes += estimatedBytes;
  }
  const sourceUnderTestPaths = new Set(
    context.repoGraph.edges
      .filter((edge) => edge.type === "imports" && selectedTestPaths.has(edge.from))
      .map((edge) => edge.to),
  );
  const sourceUnderTest = context.codebaseMap.files.filter(
    (file) => sourceUnderTestPaths.has(file.path) && !file.isTest && !file.isFixture,
  );
  const testWarnings = getFilesWithWarningsOrUnresolvedImports(context).filter((file) => file.isTest);
  const plan = buildPlan(context, {
    kind: "testing",
    targetMemoryFile: ".bridger/memory/testing.md",
    title: "Testing reading plan",
    purpose: "Explain test tooling, test patterns, fixtures, source relationships, and verification behavior.",
    agentFocus: "Identify real test commands and configuration, representative tests, fixtures, and directly imported source files.",
    shouldAnswer: ["What framework and commands are used?", "What patterns do tests and fixtures follow?", "Which source areas have direct test import evidence?"],
    shouldAvoid: ["Every test file.", "Speculative source-under-test matching.", "Architecture-only entrypoints."],
    batches: [
      {
        id: "test-setup-and-commands",
        title: "Test setup and commands",
        purpose: "Identify test tooling and verification commands from real files.",
        selectionRule: "Project metadata/config files and files carrying implemented testing signals.",
        candidates: combineFiles(
          getConfigFiles(context),
          getFilesBySignalKind(context, ["testing"]).filter((file) =>
            file.roles.includes("config") || file.roles.includes("project-config"),
          ),
        ),
        roleInBatch: "config",
        reason: "Provides file-backed evidence for test setup or commands.",
        evidence: (file) => [
          {
            source: "codebase-map",
            detail: `Selected from implemented config roles [${file.roles.join(", ")}].`,
          },
          {
            source: "repo-context",
            detail: `Repository context reports test frameworks [${[...context.repoContext.stack.testFramework].sort().join(", ") || "none"}] and test command ${context.repoContext.commands.test ?? "none"}.`,
          },
        ],
        ranking: { roles: ["project-config", "config"], signalKinds: ["testing"] },
      },
      {
        id: "representative-tests",
        title: "Representative tests",
        purpose: "Read tests that demonstrate test style across available clusters.",
        selectionRule: "CodebaseMap isTest files ranked by testing signals, centrality, graph degree, and path.",
        candidates: tests,
        roleInBatch: "representative-test",
        reason: "Is classified as a test by CodebaseMap.",
        ranking: { signalKinds: ["testing"], preferCentral: true },
      },
      {
        id: "fixtures-and-test-data",
        title: "Fixtures and test data",
        purpose: "Understand existing fixture patterns.",
        selectionRule: "CodebaseMap isFixture files and cluster fixture lists.",
        candidates: getFixtureFiles(context),
        roleInBatch: "fixture",
        reason: "Is classified as fixture data by CodebaseMap.",
      },
      {
        id: "source-under-test",
        title: "Source files under test",
        purpose: "Read source files directly imported by selected tests.",
        selectionRule: "Targets of existing RepoGraph import edges whose source is a CodebaseMap test file.",
        candidates: sourceUnderTest,
        roleInBatch: "supporting-context",
        reason: "Is the target of an existing graph import edge from a classified test file.",
        evidence: () => [{ source: "repo-graph", detail: "Direct target of an existing import edge from a CodebaseMap test file." }],
        ranking: { preferCentral: true },
      },
      {
        id: "test-warnings",
        title: "Test coverage warnings",
        purpose: "Surface files tied to deterministic test diagnostics.",
        selectionRule: "Test files with unresolved imports or path-specific FileIndex warnings.",
        candidates: testWarnings,
        roleInBatch: "risk-signal",
        reason: "Has an existing test-related diagnostic.",
      },
    ],
  });
  if (tests.length === 0 && context.repoContext.stack.testFramework.length > 0) {
    plan.warnings = sortWarnings([
      ...plan.warnings,
      {
        code: "test-framework-without-tests",
        message: "RepoContext reports a test framework, but CodebaseMap contains no test files.",
        planKind: "testing",
        severity: "warning",
      },
    ]);
  }
  return plan;
}
