import { describe, expect, it } from "vitest";

import { GENERATED_DOC_FILENAMES } from "../src/core/doc-generator/doc-filenames";
import { buildKnowledgeDocGenerationInput } from "../src/core/doc-generator/knowledge-doc-input";
import { buildAgentRulesPrompt } from "../src/core/llm/prompts/docs/agent-rules-prompt";
import { buildArchitecturePrompt } from "../src/core/llm/prompts/docs/architecture-prompt";
import { buildBusinessLogicPrompt } from "../src/core/llm/prompts/docs/business-logic-prompt";
import { buildConventionsPrompt } from "../src/core/llm/prompts/docs/conventions-prompt";
import { buildRepoAnalysisPrompt } from "../src/core/llm/prompts/docs/repo-analysis-prompt";
import { buildTestingPrompt } from "../src/core/llm/prompts/docs/testing-prompt";
import {
  GenerateAgentRulesDocInputSchema,
  type GenerateAgentRulesDocInput,
} from "../src/core/models/agent-rules-doc";
import {
  buildGeneratedDocPaths,
  getTicketTemplateRelativePath,
  RepoRelativePathSchema,
} from "../src/core/models/generated-paths";

const input = buildKnowledgeDocGenerationInput({
  repoContext: {
    repoRoot: "/repo",
    generatedAt: "2026-05-01T00:00:00.000Z",
    stack: {
      framework: "Next.js",
      language: "TypeScript",
      packageManager: "pnpm",
      styling: ["Tailwind CSS"],
      validation: ["zod"],
      database: [],
      testFramework: ["vitest"],
    },
    commands: {
      dev: "pnpm dev",
      test: "pnpm test",
    },
    importantFiles: [
      {
        path: "README.md",
        reason: "Project overview",
      },
    ],
    generatedDocs: {
      ...buildGeneratedDocPaths(),
      ticketTemplatePath: RepoRelativePathSchema.parse(
        getTicketTemplateRelativePath(),
      ),
    },
  },
  fileIndex: {
    generatedAt: "2026-05-01T00:00:00.000Z",
    files: [
      {
        path: RepoRelativePathSchema.parse("README.md"),
        extension: ".md",
        sizeBytes: 100,
        tags: ["documentation", "readme"],
        reason: "Project README",
      },
      {
        path: RepoRelativePathSchema.parse("src/app/page.tsx"),
        extension: ".tsx",
        sizeBytes: 200,
        tags: ["app", "route"],
        reason: "Route entry",
      },
    ],
  },
  importantFiles: [
    {
      path: "README.md",
      reason: "Project overview",
      content: "# Bridger",
    },
  ],
});

const agentRulesInput: GenerateAgentRulesDocInput = {
  repoContext: input.repoContext,
  generatedDocs: {
    repoAnalysis: "## Project overview\n\nRepo analysis content.",
    architecture: "## Project overview\n\nArchitecture content.",
    conventions: "## TypeScript conventions\n\nConventions content.",
    businessLogic: "## Product/domain overview\n\nBusiness logic content.",
    testing: "## Testing philosophy\n\nTesting content.",
  },
};

describe("prompt builders", () => {
  it("validates the agent rules input schema", () => {
    expect(() => GenerateAgentRulesDocInputSchema.parse(agentRulesInput)).not.toThrow();
    expect(() =>
      GenerateAgentRulesDocInputSchema.parse({
        ...agentRulesInput,
        generatedDocs: {
          ...agentRulesInput.generatedDocs,
          testing: undefined,
        },
      }),
    ).toThrow();
  });

  it("builds the repo analysis prompt scaffold", () => {
    const result = buildRepoAnalysisPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `repo-analysis.md` for this repository.");
    expect(result.prompt).toContain("## High-signal context");
    expect(result.prompt).toContain("## Visible structure and likely boundaries");
    expect(result.prompt).toContain("## What needs more context");
  });

  it("builds the architecture prompt scaffold", () => {
    const result = buildArchitecturePrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `architecture.md` for this repository.");
    expect(result.prompt).toContain("## Architectural overview");
    expect(result.prompt).toContain("## Main entry points and execution paths");
    expect(result.prompt).toContain("## Central and risky areas");
    expect(result.prompt).toContain("## Architectural unknowns");
  });

  it("builds the conventions prompt scaffold", () => {
    const result = buildConventionsPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `conventions.md` for this repository.");
    expect(result.prompt).toContain("## Patterns to copy");
    expect(result.prompt).toContain("## What agents should avoid");
    expect(result.prompt).toContain("## Unknowns and weak signals");
  });

  it("builds the business logic prompt scaffold", () => {
    const result = buildBusinessLogicPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `business-logic.md` for this repository.");
    expect(result.prompt).toContain("## Product and domain model");
    expect(result.prompt).toContain("## Business rules and invariants");
    expect(result.prompt).toContain("## Unknowns and risks");
  });

  it("builds the testing prompt scaffold", () => {
    const result = buildTestingPrompt(input);

    assertPromptScaffold(result);
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `testing.md` for this repository.");
    expect(result.prompt).toContain("## Verification overview");
    expect(result.prompt).toContain("## Commands agents can run");
    expect(result.prompt).toContain("## Existing testing patterns to copy");
    expect(result.prompt).toContain("## Testing gaps and unsafe assumptions");
    expect(result.prompt).toContain("## Testing mistakes to avoid");
    expect(result.prompt).toContain("test: pnpm test");
    expect(result.prompt).toContain("Testing: vitest");
  });

  it("builds the testing prompt without inventing test frameworks or commands", () => {
    const result = buildTestingPrompt({
      ...input,
      repoContext: {
        ...input.repoContext,
        commands: {},
        stack: {
          ...input.repoContext.stack,
          testFramework: [],
        },
      },
    });

    expect(result.prompt).toContain("## Verification overview");
    expect(result.prompt).toContain("- Unknown");
    expect(result.prompt).toContain("Testing: unknown");
    expect(result.prompt).not.toContain("pnpm test");
  });

  it("builds the agent rules prompt scaffold", () => {
    const result = buildAgentRulesPrompt(agentRulesInput);

    expect(result.system).toEqual(expect.any(String));
    expect(result.prompt).toEqual(expect.any(String));
    expect(result.system).not.toContain("TODO");
    expect(result.prompt).not.toContain("TODO");
    expect(result.prompt).toContain("Generate `agent-rules.md` for this repository.");
    expect(result.prompt).toContain("# Repo context");
    expect(result.prompt).toContain("# Generated docs");
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.repoAnalysis);
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.architecture);
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.conventions);
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.businessLogic);
    expect(result.prompt).toContain(GENERATED_DOC_FILENAMES.testing);
    expect(result.prompt).toContain("## Agent operating principles");
    expect(result.prompt).toContain("## Repo-specific change boundaries");
    expect(result.prompt).toContain("## Business logic and side-effect rules");
    expect(result.prompt).toContain("## Risky changes and avoid-rules");
    expect(result.prompt).toContain("## Unknowns agents must preserve");
  });
});

function assertPromptScaffold(result: { system: string; prompt: string }): void {
  expect(result.system).toEqual(expect.any(String));
  expect(result.prompt).toEqual(expect.any(String));
  expect(result.prompt).toContain("# Output shape");
  expect(result.prompt).toContain("# Grounding rules");
  expect(result.prompt).toContain("# Output rules");
  expect(result.prompt).toContain("# Repo context");
  expect(result.prompt).toContain("## Detected stack");
  expect(result.prompt).toContain("## Commands");
  expect(result.prompt).toContain("## File index summary");
  expect(result.prompt).toContain("## Important files");
}
