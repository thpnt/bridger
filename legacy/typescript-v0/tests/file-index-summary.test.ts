import { describe, expect, it } from "vitest";

import { summarizeFileIndexForPrompt } from "../src/core/context-builder/file-index-summary";
import type { FileIndex } from "../src/core/models/file-index";
import { RepoRelativePathSchema } from "../src/core/models/path";

const fileIndex: FileIndex = {
  generatedAt: "2026-05-01T00:00:00.000Z",
  files: [
    {
      path: RepoRelativePathSchema.parse("README.md"),
      extension: ".md",
      sizeBytes: 100,
      tags: ["readme", "documentation", "important"],
      reason: "Project README",
    },
    {
      path: RepoRelativePathSchema.parse("src/app/page.tsx"),
      extension: ".tsx",
      sizeBytes: 200,
      tags: ["src", "app", "route", "typescript", "react"],
      reason: "Application route file",
    },
    {
      path: RepoRelativePathSchema.parse("src/domains/billing/schema.ts"),
      extension: ".ts",
      sizeBytes: 300,
      tags: ["src", "domain", "typescript"],
      reason: "Domain file",
    },
    {
      path: RepoRelativePathSchema.parse("src/components/ui/button.tsx"),
      extension: ".tsx",
      sizeBytes: 150,
      tags: ["src", "components", "ui", "typescript", "react"],
      reason: "UI component file",
    },
  ],
};

describe("summarizeFileIndexForPrompt", () => {
  it("produces a deterministic compact summary", () => {
    const summary = summarizeFileIndexForPrompt(fileIndex);
    const repeatedSummary = summarizeFileIndexForPrompt(fileIndex);

    expect(summary).toContain("Total indexed files: 4");
    expect(summary).toContain("Top-level folders:");
    expect(summary).toContain(". — 1 files");
    expect(summary).toContain("src/ — 3 files");
    expect(summary).toContain("Detected tagged areas:");
    expect(summary).toContain("Representative paths:");
    expect(summary).toContain("README.md");
    expect(summary).toContain("src/app/page.tsx");
    expect(summary).toContain("Representative paths by tag:");
    expect(summary).toContain("app:");
    expect(summary).toContain("components:");
    expect(summary).toBe(repeatedSummary);
  });
});
