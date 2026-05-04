import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/core/llm/client", () => ({
  generateText: vi.fn(),
}));

import { generateText } from "../src/core/llm/client";
import { generateKnowledgeDoc } from "../src/core/doc-generator/generators/generate-knowledge-doc";
import type { KnowledgeDocSpec } from "../src/core/doc-generator/doc-types";

const mockedGenerateText = vi.mocked(generateText);

const spec: KnowledgeDocSpec = {
  key: "architecture",
  filename: "architecture.md",
  displayName: "Architecture",
  requiredSections: ["## Overview", "## Unknowns"],
};

const generationInput = {
  repoContext: {
    repoRoot: "/repo",
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: [],
      validation: [],
      database: [],
      testFramework: [],
    },
    commands: {},
    importantFiles: [],
    generatedDocs: {
      repoAnalysisPath: "generated/repo-analysis.md",
      architecturePath: "generated/architecture.md",
      conventionsPath: "generated/conventions.md",
      businessLogicPath: "generated/business-logic.md",
      testingPath: "generated/testing.md",
      agentRulesPath: "generated/agent-rules.md",
      ticketTemplatePath: "generated/ticket-template.md",
    },
  },
  fileIndex: {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [],
  },
  fileIndexSummary: "Total indexed files: 0",
  importantFiles: [],
};

describe("generateKnowledgeDoc", () => {
  beforeEach(() => {
    mockedGenerateText.mockReset();
  });

  it("throws when the LLM returns empty markdown", async () => {
    mockedGenerateText.mockResolvedValueOnce("   ");

    await expect(
      generateKnowledgeDoc({
        spec,
        generationInput,
        buildPrompt: () => ({ system: "system", prompt: "prompt" }),
      }),
    ).rejects.toThrow("Architecture generation returned empty Markdown.");
  });

  it("returns trimmed markdown even when required sections are absent", async () => {
    mockedGenerateText.mockResolvedValueOnce("# Doc\n\n## Overview\n");

    await expect(
      generateKnowledgeDoc({
        spec,
        generationInput,
        buildPrompt: () => ({ system: "system", prompt: "prompt" }),
      }),
    ).resolves.toBe("# Doc\n\n## Overview");
  });
});
