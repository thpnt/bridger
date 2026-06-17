import { describe, expect, it } from "vitest";

import { renderReadingPlanContext } from "../src/core/reading-plans/render-reading-plan-context";
import type { ReadReadingPlanFilesResult } from "../src/core/reading-plans/read-reading-plan-files";

describe("renderReadingPlanContext", () => {
  it("renders stable plan, batch, metadata, and content structure", () => {
    const result = createResult();

    expect(renderReadingPlanContext({ result })).toBe(
      [
        "# Reading Plan Context: architecture",
        "Title: Architecture plan",
        "Target memory file: .bridger/memory/architecture.md",
        "Purpose: Explain architecture.",
        "Plan budget: maxFiles=8, estimatedBytes=123, truncated=no",
        "Agent focus: Understand structure.",
        "Should answer:",
        "- What starts execution?",
        "Should avoid:",
        "- Unsupported claims.",
        "Plan warnings:",
        "- [info] plan-warning: Existing warning.",
        "## Batch 1: Entrypoints",
        "Batch ID: batch-1",
        "Purpose: Understand startup.",
        "Selection rule: Use existing entrypoints.",
        "Budget: maxFiles=4, estimatedBytes=60, truncated=no",
        "### File: src/cli/cli.ts",
        "Role in batch: entrypoint",
        "Reason: Selected from CodebaseMap entrypoints.",
        "Confidence: observed",
        "Estimated bytes: 60",
        "Bytes read: 18",
        "Truncated: no",
        "Evidence:",
        "- codebase-map: entrypoint candidate",
        "Content:",
        "<<<FILE_CONTENT_START src/cli/cli.ts>>>",
        "console.log('hi');",
        "<<<FILE_CONTENT_END src/cli/cli.ts>>>",
        "End of file: src/cli/cli.ts",
        "## Batch 2: Supporting Context",
        "Batch ID: batch-2",
        "Purpose: Read support modules.",
        "Selection rule: Keep nearby utilities.",
        "Budget: maxFiles=4, estimatedBytes=63, truncated=yes",
        "### File: src/core/service.ts",
        "Role in batch: service",
        "Reason: High fan-in service.",
        "Confidence: inferred",
        "Estimated bytes: 63",
        "Bytes read: 11",
        "Truncated: yes",
        "Evidence:",
        "- graph-summary: high fan-in file",
        "Content:",
        "<<<FILE_CONTENT_START src/core/service.ts>>>",
        "export {};\n",
        "<<<FILE_CONTENT_END src/core/service.ts>>>",
        "End of file: src/core/service.ts",
        "",
      ].join("\n"),
    );
  });

  it("includes diagnostics when requested", () => {
    const result = createResult();

    expect(
      renderReadingPlanContext({ result, includeDiagnostics: true }),
    ).toContain(
      [
        "## Diagnostics",
        "- [warning] file-not-found: Missing file. | batch=batch-2 | path=src/missing.ts",
      ].join("\n"),
    );
  });

  it("omits diagnostics when not requested", () => {
    const result = createResult();

    expect(renderReadingPlanContext({ result })).not.toContain(
      "## Diagnostics",
    );
    expect(renderReadingPlanContext({ result })).not.toContain("Missing file.");
  });
});

function createResult(): ReadReadingPlanFilesResult {
  return {
    planKind: "architecture",
    targetMemoryFile: ".bridger/memory/architecture.md",
    title: "Architecture plan",
    purpose: "Explain architecture.",
    inputStrategy: {
      agentFocus: "Understand structure.",
      shouldAnswer: ["What starts execution?"],
      shouldAvoid: ["Unsupported claims."],
    },
    budget: { maxFiles: 8, estimatedBytes: 123, truncated: false },
    warnings: [
      {
        code: "plan-warning",
        message: "Existing warning.",
        severity: "info",
      },
    ],
    batches: [
      {
        id: "batch-1",
        title: "Entrypoints",
        purpose: "Understand startup.",
        order: 1,
        selectionRule: "Use existing entrypoints.",
        budget: { maxFiles: 4, estimatedBytes: 60, truncated: false },
        files: [
          {
            path: "src/cli/cli.ts",
            roleInBatch: "entrypoint",
            reason: "Selected from CodebaseMap entrypoints.",
            evidence: [{ source: "codebase-map", detail: "entrypoint candidate" }],
            confidence: "observed",
            estimatedBytes: 60,
            content: "console.log('hi');",
            bytesRead: 18,
            truncated: false,
          },
        ],
      },
      {
        id: "batch-2",
        title: "Supporting Context",
        purpose: "Read support modules.",
        order: 2,
        selectionRule: "Keep nearby utilities.",
        budget: { maxFiles: 4, estimatedBytes: 63, truncated: true },
        files: [
          {
            path: "src/core/service.ts",
            roleInBatch: "service",
            reason: "High fan-in service.",
            evidence: [{ source: "graph-summary", detail: "high fan-in file" }],
            confidence: "inferred",
            estimatedBytes: 63,
            content: "export {};\n",
            bytesRead: 11,
            truncated: true,
          },
        ],
      },
    ],
    diagnostics: [
      {
        code: "file-not-found",
        message: "Missing file.",
        path: "src/missing.ts",
        batchId: "batch-2",
        severity: "warning",
      },
    ],
  };
}
