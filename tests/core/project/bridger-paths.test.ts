import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildGeneratedDocPaths,
  getGeneratedKnowledgeDocRelativePath,
  getTicketTemplateRelativePath,
} from "../../../src/core/project/bridger-paths";

describe("generated paths", () => {
  it("builds stable relative generated doc paths", () => {
    expect(buildGeneratedDocPaths()).toEqual({
      repoAnalysisPath: ".bridger/memory/repo-analysis.md",
      architecturePath: ".bridger/memory/architecture.md",
      businessLogicPath: ".bridger/memory/business-logic.md",
      conventionsPath: ".bridger/memory/conventions.md",
      testingPath: ".bridger/memory/testing.md",
    });
  });

  it("builds stable relative paths from the doc key", () => {
    expect(getGeneratedKnowledgeDocRelativePath("architecture")).toBe(
      path.posix.join(".bridger", "memory", "architecture.md"),
    );
    expect(getTicketTemplateRelativePath()).toBe(
      path.posix.join(".bridger", "templates", "ticket-template.md"),
    );
  });
});
