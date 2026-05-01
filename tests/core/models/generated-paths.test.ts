import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  buildGeneratedDocPaths,
  getGeneratedKnowledgeDocRelativePath,
  getTicketTemplateRelativePath,
} from "../../../src/core/models/generated-paths";

describe("generated paths", () => {
  it("builds stable relative generated doc paths", () => {
    expect(buildGeneratedDocPaths()).toEqual({
      repoAnalysisPath: ".bridger/generated/repo-analysis.md",
      architecturePath: ".bridger/generated/architecture.md",
      businessLogicPath: ".bridger/generated/business-logic.md",
      conventionsPath: ".bridger/generated/conventions.md",
      testingPath: ".bridger/generated/testing.md",
      agentRulesPath: ".bridger/generated/agent-rules.md",
    });
  });

  it("builds stable relative paths from the doc key", () => {
    expect(getGeneratedKnowledgeDocRelativePath("architecture")).toBe(
      path.posix.join(".bridger", "generated", "architecture.md"),
    );
    expect(getTicketTemplateRelativePath()).toBe(
      path.posix.join(".bridger", "generated", "ticket-template.md"),
    );
  });
});
